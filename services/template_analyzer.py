"""Hybrid template analyzer: document scan → OpenCV measures → GLM-4V describes.

Pipeline:
  1. Document scan: detect page corners → perspective warp → flat document
  2. OpenCV: measure ruling lines, margins, divider on the flat image
  3. GLM-4V: semantic analysis (labels, colors, text) on the flat image
"""

import os
import json
import time
import numpy as np
from pathlib import Path
from PIL import Image

# Load .env early so GLM_API_KEY is available
_ENV_FILE = Path(__file__).parent.parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

_glm_available = None


def _get_glm():
    global _glm_available
    if _glm_available is None:
        if not os.environ.get("GLM_API_KEY"):
            _glm_available = False
        else:
            try:
                from tools.glm_vision import ask_glm
                _glm_available = ask_glm
            except (SystemExit, ImportError):
                _glm_available = False
    return _glm_available if callable(_glm_available) else None


class TemplateAnalyzer:
    """Scan a photo of a lesson plan notebook and extract its layout.

    The photo goes through document scanning first (like 扫描全能王):
    perspective correction → flat document image → then all measurements.
    """

    def __init__(self, photo_path: str):
        self.photo_path = photo_path
        self.warnings: list[str] = []
        self._flat_path: str | None = None  # path to warped/flat image

    def analyze(self) -> dict:
        if not CV2_AVAILABLE:
            return self._glm_only_mode()

        image = cv2.imread(self.photo_path)
        if image is None:
            raise ValueError(f"Cannot read image: {self.photo_path}")

        # ── Step 1: Document scan (perspective warp) ──
        flat = self._scan_document(image)
        if flat is not None:
            image = flat
            self.warnings.append("已完成文档透视校正")
        else:
            self.warnings.append("未能检测文档边界，使用原始图像")

        # Save flat image for GLM-4V
        flat_dir = Path(self.photo_path).parent
        self._flat_path = str(flat_dir / f"_flat_{int(time.time())}.jpg")
        cv2.imwrite(self._flat_path, image)

        # ── Step 2: OpenCV line detection on ORIGINAL photo ──
        # (before warp, lines are sharper)
        original = cv2.imread(self.photo_path)
        opencv_result = self._run_opencv(original)

        # ── Step 3: GLM-4V measures on the flat image ──
        glm_result = self._run_glm4v(self._flat_path)

        # ── Step 4: Fuse — GLM measurements take precedence ──
        # GLM on flat image is more reliable for line count, spacing,
        # divider position, and all text labels.
        fused = self._fuse(opencv_result, glm_result)
        issues = self._validate(fused)
        self.warnings.extend(issues)
        fused["warnings"] = self.warnings

        # Cleanup temp
        if self._flat_path and os.path.exists(self._flat_path):
            try:
                os.remove(self._flat_path)
            except Exception:
                pass

        return fused

    # ═══════════════════════════════════════════════════════════
    # Step 1: Document scanner (perspective warp)
    # ═══════════════════════════════════════════════════════════

    def _scan_document(self, image: np.ndarray) -> np.ndarray | None:
        """Detect document corners, apply perspective warp → flat image.

        Handles double-page spreads by detecting and extracting just the page half.
        """
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (11, 11), 0)
        edges = cv2.Canny(blurred, 20, 60)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        dilated = cv2.dilate(edges, kernel, iterations=3)
        closed = cv2.erode(dilated, kernel, iterations=1)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_quad = None
        best_area = 0
        img_area = w * h

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < img_area * 0.20 or area > img_area * 0.98:
                continue

            peri = cv2.arcLength(cnt, True)
            corners = None
            for eps_factor in [0.02, 0.03, 0.04, 0.05, 0.07]:
                approx = cv2.approxPolyDP(cnt, eps_factor * peri, True)
                if len(approx) == 4:
                    corners = approx
                    break
            if corners is None:
                rect = cv2.minAreaRect(cnt)
                corners = cv2.boxPoints(rect)
                corners = np.intp(corners)

            corners = corners.reshape(-1, 2)
            if len(corners) != 4:
                continue

            rect_w1 = np.linalg.norm(corners[0] - corners[1])
            rect_h1 = np.linalg.norm(corners[1] - corners[2])
            if min(rect_w1, rect_h1) < 50:
                continue
            aspect = max(rect_w1, rect_h1) / min(rect_w1, rect_h1)
            if 0.5 < aspect < 2.5 and area > best_area:
                best_area = area
                best_quad = corners

        if best_quad is None:
            return None

        pts = self._order_corners(best_quad)

        quad_w = int((np.linalg.norm(pts[0] - pts[1]) + np.linalg.norm(pts[2] - pts[3])) / 2)
        quad_h = int((np.linalg.norm(pts[1] - pts[2]) + np.linalg.norm(pts[3] - pts[0])) / 2)
        aspect_ratio = quad_w / max(1, quad_h)

        # Check for double-page spread (aspect > 1.3 = wider than A4 portrait)
        if aspect_ratio > 1.3:
            self.warnings.append("检测到双页展开，已提取左半页")
            mid_x = (pts[1][0] + pts[2][0]) / 2
            pts[1][0] = mid_x
            pts[2][0] = mid_x
            quad_w = int(quad_w / 2)

        target_w = 2480
        target_h = int(target_w * quad_h / max(1, quad_w))

        dst = np.float32([
            [0, 0], [target_w - 1, 0],
            [target_w - 1, target_h - 1], [0, target_h - 1],
        ])

        M = cv2.getPerspectiveTransform(np.float32(pts), dst)
        warped = cv2.warpPerspective(image, M, (target_w, target_h),
                                      borderMode=cv2.BORDER_CONSTANT,
                                      borderValue=(255, 255, 255))
        return warped

    @staticmethod
    def _order_corners(pts: np.ndarray) -> np.ndarray:
        """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
        pts = pts.reshape(4, 2)
        # Sort by sum of coordinates (top-left has smallest sum)
        ordered = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        ordered[0] = pts[np.argmin(s)]  # TL
        ordered[2] = pts[np.argmax(s)]  # BR

        # The other two — sort by difference (y-x)
        diff = np.diff(pts, axis=1).flatten()
        remaining = pts[(s != s.min()) & (s != s.max())] if len(pts) == 4 else pts
        # Recalculate for remaining
        remaining = np.array([p for i, p in enumerate(pts) if i != np.argmin(s) and i != np.argmax(s)])
        if len(remaining) >= 2:
            d0 = remaining[0][1] - remaining[0][0]
            d1 = remaining[1][1] - remaining[1][0]
            ordered[1] = remaining[0] if d0 > d1 else remaining[1]  # TR (larger y-x)
            ordered[3] = remaining[1] if d0 > d1 else remaining[0]  # BL

        return ordered

    # ═══════════════════════════════════════════════════════════
    # Step 2: OpenCV measurements on FLAT image
    # ═══════════════════════════════════════════════════════════

    def _run_opencv(self, image: np.ndarray) -> dict:
        """Measure ruling lines, margins, divider on a flat document image."""
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # px/mm ratio — assume A4 width (210mm) for scale
        ppm = w / 210.0

        # Detect horizontal ruling lines
        lines_info = self._detect_horizontal_lines(gray, w, h)
        line_count = len(lines_info)

        line_spacing_mm = None
        if line_count >= 2:
            spacings = [lines_info[i]["y"] - lines_info[i - 1]["y"] for i in range(1, len(lines_info))]
            # Filter outliers
            median_s = float(np.median(spacings))
            valid = [s for s in spacings if 0.5 * median_s < s < 1.5 * median_s]
            if valid:
                line_spacing_mm = round(float(np.mean(valid)) / ppm, 1)
            else:
                line_spacing_mm = round(median_s / ppm, 1)

        # Vertical divider
        divider = self._detect_vertical_divider(gray, w, h)

        # Margins (relative to the flat page edges)
        margins = self._compute_margins(lines_info, w, h, ppm)

        # Line style
        line_style = self._detect_line_style(gray, lines_info)

        return {
            "page": {
                "width_mm": round(w / ppm, 1),
                "height_mm": round(h / ppm, 1),
                "paper_rgb": [255, 255, 255],
                "ppm": round(ppm, 2),
            },
            "margins": margins,
            "writing_area": self._compute_writing_area(margins, w / ppm, h / ppm, divider),
            "ruling": {
                "line_count": line_count,
                "line_spacing_mm": line_spacing_mm,
                "style": line_style,
            },
            "vertical_divider": divider,
            "source": "opencv",
        }

    # ═══ Horizontal lines (projection-based) ═══

    def _detect_horizontal_lines(self, gray: np.ndarray, w: int, h: int) -> list[dict]:
        """Detect ruling lines using vertical projection of horizontal gradients.

        More robust than Canny for thin, low-contrast printed lines on paper.
        """
        # Method: compute horizontal gradient (Sobel), sum across each row.
        # Ruling lines are dark pixels relative to the paper — a horizontal
        # edge detector catches the top/bottom of each line.
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_x = np.abs(grad_x)

        # Row projection: sum of horizontal gradients per row
        row_signal = np.sum(grad_x, axis=1).astype(float)

        # Smooth the signal
        kernel = np.ones(3) / 3
        row_signal = np.convolve(row_signal, kernel, mode='same')

        # Find peaks (lines = high horizontal gradient = many vertical edges)
        # Use prominence-based peak finding
        try:
            from scipy.signal import find_peaks
            # Estimate peak height — ~30% of the 90th percentile
            threshold = np.percentile(row_signal, 60)
            distance = max(3, int(h / 80))  # at least ~80 lines per page
            peaks, props = find_peaks(row_signal, height=threshold, distance=distance)
        except Exception:
            # Manual peak finding as fallback
            peaks = []
            threshold = np.percentile(row_signal, 60)
            for i in range(1, len(row_signal) - 1):
                if (row_signal[i] > threshold and
                        row_signal[i] > row_signal[i - 1] and
                        row_signal[i] >= row_signal[i + 1]):
                    peaks.append(i)

        if len(peaks) < 2:
            return []

        # For each peak, estimate line extent by scanning left-right
        # until gradient drops below threshold
        lines_info = []
        line_profile = row_signal  # reuse

        for peak_y in peaks:
            y = int(peak_y)
            if y < 2 or y >= h - 2:
                continue
            # Find left/right extent: scan from center outward until gradient drops
            cx = w // 2
            left = cx
            right = cx
            grad_thresh = np.mean(grad_x[y - 1:y + 2, :]) * 0.3
            while left > 0 and grad_x[y, left] > grad_thresh:
                left -= 1
            while right < w - 1 and grad_x[y, right] > grad_thresh:
                right += 1
            line_w = right - left
            if line_w > w * 0.2:
                lines_info.append({"y": y, "x1": left, "x2": right, "w": line_w, "h": 3})

        # Sort by Y
        lines_info.sort(key=lambda l: l["y"])

        # Cluster nearby lines (within 12px → merge)
        if lines_info:
            clustered = [lines_info[0]]
            for line in lines_info[1:]:
                if line["y"] - clustered[-1]["y"] > 12:
                    clustered.append(line)
            return clustered

        return []

    # ═══ Vertical divider ═══

    def _detect_vertical_divider(self, gray: np.ndarray, w: int, h: int) -> dict:
        """Detect the vertical divider line (right side reflection zone separator)."""
        # Search the right 50% of the page
        roi = gray[:, int(w * 0.4):]
        rh, rw = roi.shape

        edges = cv2.Canny(roi, 30, 90)
        kernel_h = max(40, int(h * 0.12))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_h))
        vertical = cv2.morphologyEx(edges, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_len = 0
        min_h = h * 0.20

        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if ch > min_h and cw < 30 and ch > best_len:
                best_len = ch
                global_x = int(w * 0.4) + x + cw // 2
                best = {"x_px": global_x, "y1": y, "y2": y + ch, "h": ch, "w": cw}

        if best is None:
            # Try lower thresholds
            edges2 = cv2.Canny(roi, 15, 50)
            vertical2 = cv2.morphologyEx(edges2, cv2.MORPH_OPEN, kernel)
            contours2, _ = cv2.findContours(vertical2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours2:
                x, y, cw, ch = cv2.boundingRect(cnt)
                if ch > min_h and cw < 30 and ch > best_len:
                    best_len = ch
                    global_x = int(w * 0.4) + x + cw // 2
                    best = {"x_px": global_x, "y1": y, "y2": y + ch, "h": ch, "w": cw}

        if best is None:
            return {"exists": False}

        # Check continuity
        x_c = min(best["x_px"], w - 1)
        samples = 30
        step = max(1, best_len // samples)
        hits = sum(1 for i in range(samples)
                   if 0 <= (sy := best["y1"] + i * step) < h and gray[sy, x_c] < 150)
        continuity = hits / samples

        return {
            "exists": True,
            "x_px": best["x_px"],
            "continuity": round(continuity, 2),
            "style": "solid" if continuity > 0.65 else "dashed",
        }

    # ═══ Margins ═══

    def _compute_margins(self, lines_info: list[dict], w: int, h: int, ppm: float) -> dict:
        def to_mm(px):
            return round(px / ppm, 1) if ppm else round(px / 11.8, 1)

        if not lines_info:
            # Heuristic: assume ~25mm margins
            return {"top_mm": 25.0, "bottom_mm": 25.0, "left_mm": 25.0, "right_mm": 20.0}

        top_px = lines_info[0]["y"]
        bottom_px = h - lines_info[-1]["y"]
        left_px = min(l["x1"] for l in lines_info)
        right_px = w - max(l["x2"] for l in lines_info)

        return {
            "top_mm": to_mm(max(0, top_px)),
            "bottom_mm": to_mm(max(0, bottom_px)),
            "left_mm": to_mm(max(0, left_px)),
            "right_mm": to_mm(max(0, right_px)),
        }

    def _detect_line_style(self, gray, lines_info):
        if not lines_info:
            return "solid"
        checked = 0
        solid = 0
        for line in lines_info[:10]:
            if line["x2"] <= line["x1"]:
                continue
            y = min(line["y"], gray.shape[0] - 1)
            row = gray[y, max(0, line["x1"]):min(gray.shape[1] - 1, line["x2"])]
            if len(row) > 0 and np.sum(row < 128) / len(row) > 0.55:
                solid += 1
            checked += 1
        return "solid" if checked > 0 and solid >= checked * 0.7 else "dashed"

    def _compute_writing_area(self, margins, page_w, page_h, divider):
        wa_x = margins.get("left_mm", 25)
        wa_y = margins.get("top_mm", 25)
        if divider.get("exists") and divider.get("x_px"):
            wa_w = page_w - wa_x - margins.get("right_mm", 20)
        else:
            wa_w = page_w - wa_x - margins.get("right_mm", 20)
        wa_h = page_h - wa_y - margins.get("bottom_mm", 25)
        return {"x_mm": wa_x, "y_mm": wa_y, "width_mm": wa_w, "height_mm": wa_h}

    # ═══════════════════════════════════════════════════════════
    # Step 3: GLM-4V semantic analysis
    # ═══════════════════════════════════════════════════════════

    def _run_glm4v(self, photo_path: str) -> dict:
        ask_glm = _get_glm()
        if ask_glm is None:
            return {"source": "glm_unavailable"}

        prompt = """这是一张已经透视校正拉平的教案本单页照片(A4: 210×297mm)。

## 任务
1. 只识别**印刷**的文字（宋体/楷体，颜色深，位置固定）。手写笔迹必须忽略。
2. 估计横线布局参数。

## 区分印刷 vs 手写
- 印刷：字体规整、颜色均匀、通常是黑色
- 手写：笔迹不规则、颜色可能较浅、字间距不一致
- 如果无法确定，就不要报告

## JSON格式（只返回JSON）

{
  "printed_title": "页面顶部居中印刷的完整标题，没有就填null",
  "printed_fields": ["印刷的填空字段，如：第__周、课题：____"],
  "section_labels": ["印刷的栏目标签，如：教学反思"],
  "line_count": 整数,
  "line_spacing_mm": 数字,
  "has_right_divider": true或false,
  "divider_position": "right或none",
  "divider_x_mm": 数字
}

只返回JSON，不要其他文字。"""

        try:
            result = ask_glm(photo_path, prompt)
            result = result.strip()
            # GLM may wrap JSON in markdown fences with preamble text
            if "```" in result:
                parts = result.split("```")
                # parts[1] or parts[2] should contain the JSON
                for part in parts[1:]:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()  # strip "json" prefix
                    if part and (part.startswith("{") or part.startswith("[")):
                        result = part
                        break
            return json.loads(result)
        except Exception as e:
            return {"source": "glm_error", "error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # Step 4: Fusion (OpenCV wins numbers, GLM wins labels)
    # ═══════════════════════════════════════════════════════════

    def _fuse(self, opencv: dict, glm: dict) -> dict:
        # Force A4 page dimensions for printing
        page = {"width_mm": 210.0, "height_mm": 297.0, "paper_color": "white",
                "paper_rgb": [255, 255, 255], "ppm": opencv["page"].get("ppm", 11.8)}
        margins = opencv["margins"]
        ruling = opencv["ruling"]
        divider = opencv.get("vertical_divider", {"exists": False})

        glm_ok = isinstance(glm, dict) and glm.get("source") not in ("glm_unavailable", "glm_error")

        # ── Ruling: GLM primary ──
        line_count = ruling.get("line_count", 0)
        line_spacing = ruling.get("line_spacing_mm")
        line_style = ruling.get("style", "solid")
        if glm_ok:
            gl_count = glm.get("line_count", 0)
            gl_spacing = glm.get("line_spacing_mm")
            # GLM sometimes overcounts; cap at ~25 lines (A4 with 8mm spacing)
            line_count = min(gl_count, 25) if gl_count > line_count else line_count
            line_spacing = gl_spacing if gl_spacing else line_spacing
            line_style = glm.get("line_style", line_style)

        # ── Margins: GLM primary ──
        if glm_ok:
            margins = {
                "top_mm": glm.get("margin_top_mm", margins.get("top_mm", 25)),
                "bottom_mm": glm.get("margin_bottom_mm", margins.get("bottom_mm", 25)),
                "left_mm": glm.get("margin_left_mm", margins.get("left_mm", 25)),
                "right_mm": glm.get("margin_right_mm", margins.get("right_mm", 18)),
            }

        # ── Header and preprinted: GLM only, conservative ──
        title = ""
        info_fields: list[str] = []
        preprinted: list[dict] = []
        section_labels: list[str] = []
        if glm_ok:
            title = glm.get("printed_title") or ""
            info_fields = glm.get("printed_fields", [])
            section_labels = glm.get("section_labels", [])
            preprinted = [{"text": t, "position": "top-left"} for t in (info_fields + section_labels)]

        header_cfg = {"exists": False, "fields": []}
        if title or info_fields:
            fields = [title] + info_fields
            header_cfg = {"exists": True, "fields": fields}

        # ── Divider: GLM, filter out center folds (< 150mm from left = spine) ──
        divider_exists = False
        divider_style = "solid"
        divider_x_mm = None
        if glm_ok:
            glm_dx = glm.get("divider_x_mm")
            glm_has = glm.get("has_right_divider", False)
            if glm_dx and glm_dx > 150:
                divider_exists, divider_x_mm = True, glm_dx
            elif glm_has:
                divider_exists, divider_x_mm = True, 175.0

        divider_result = {
            "exists": divider_exists,
            "style": divider_style,
            "color": "gray",
            "color_rgb": [100, 95, 85],
        }
        if divider_x_mm is not None:
            divider_result["x_mm"] = divider_x_mm

        # ── Reflection zone ──
        reflection = {"exists": divider_exists}
        if divider_exists:
            refl_label = "教学反思"
            if section_labels and any("反思" in t for t in section_labels):
                refl_label = next(t for t in section_labels if "反思" in t)
            reflection["label"] = refl_label
            reflection["x_mm"] = divider_x_mm
            ref_w = page["width_mm"] - divider_x_mm - min(margins.get("right_mm", 18), 10)
            reflection["width_mm"] = round(max(ref_w, 25), 1)

        return {
            "page": {
                "width_mm": page["width_mm"],
                "height_mm": page["height_mm"],
                "paper_color": "white",
                "paper_rgb": [255, 255, 255],
            },
            "margins": margins,
            "writing_area": opencv["writing_area"],
            "ruling": {
                "line_count": line_count,
                "line_spacing_mm": line_spacing,
                "style": line_style,
                "color": "gray",
                "color_rgb": [100, 95, 85],
            },
            "vertical_divider": divider_result,
            "reflection_zone": reflection,
            "header": header_cfg,
            "preprinted_text": preprinted,
            "source": "opencv+glm" if glm_ok else "opencv",
        }

    # ═══════════════════════════════════════════════════════════
    # Validation
    # ═══════════════════════════════════════════════════════════

    def _validate(self, result: dict) -> list[str]:
        issues = []
        margins = result.get("margins", {})
        for key, label in [("top_mm", "上"), ("bottom_mm", "下"), ("left_mm", "左"), ("right_mm", "右")]:
            val = margins.get(key, 0)
            if val is not None and not (3 <= val <= 100):
                issues.append(f"{label}边距{val}mm超出合理范围(3-100mm)")
        spacing = result.get("ruling", {}).get("line_spacing_mm")
        if spacing is not None and not (2 <= spacing <= 30):
            issues.append(f"行距{spacing}mm超出合理范围(2-30mm)")
        wa = result.get("writing_area", {})
        pw = result.get("page", {}).get("width_mm", 210)
        ph = result.get("page", {}).get("height_mm", 297)
        if wa and wa.get("x_mm", 0) + wa.get("width_mm", 0) > pw + 2:
            issues.append("写作区宽度超出页面范围")
        return issues

    # ═══════════════════════════════════════════════════════════
    # Fallback: GLM-only
    # ═══════════════════════════════════════════════════════════

    def _glm_only_mode(self) -> dict:
        self.warnings.append("OpenCV未安装，使用纯GLM-4V估算模式")
        ask_glm = _get_glm()
        if ask_glm is None:
            raise RuntimeError("GLM-4V不可用：请安装opencv-python-headless或设置GLM_API_KEY")

        prompt = """分析这张教案本照片的布局，以JSON返回：

{
  "page": {"width_mm": 210, "height_mm": 297},
  "margins": {"top_mm": 24, "bottom_mm": 24, "left_mm": 24, "right_mm": 18},
  "ruling": {"line_count": 18, "line_spacing_mm": 8},
  "vertical_divider": {"exists": true, "x_mm": 175},
  "title_full_text": "标题完整文字",
  "info_fields": ["字段1", "字段2"],
  "preprinted_labels": ["标签文字"],
  "has_reflection_zone": true,
  "reflection_label": "反思标签",
  "line_style": "solid"
}

根据图片实际内容填写数字和文字。只返回JSON。"""

        try:
            result = ask_glm(self.photo_path, prompt)
            result = result.strip()
            if "```" in result:
                parts = result.split("```")
                for part in parts[1:]:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part and (part.startswith("{") or part.startswith("[")):
                        result = part
                        break
            config = json.loads(result)

            page = config.get("page", {})
            margins = config.get("margins", {})
            rulings = config.get("ruling", {})
            divider = config.get("vertical_divider", {})
            title = config.get("title_full_text", "教师备课笔记")
            info_fields = config.get("info_fields", [])
            preprinted = config.get("preprinted_labels", [])
            if preprinted and isinstance(preprinted[0], str):
                preprinted = [{"text": t, "position": "top-left"} for t in preprinted]
            has_refl = config.get("has_reflection_zone", False)
            refl_label = config.get("reflection_label", "教学反思")

            header_fields = [title] + info_fields

            return {
                "page": {
                    "width_mm": page.get("width_mm", 210),
                    "height_mm": page.get("height_mm", 297),
                    "paper_color": "white",
                    "paper_rgb": [255, 255, 255],
                },
                "margins": {
                    "top_mm": margins.get("top_mm", 25),
                    "bottom_mm": margins.get("bottom_mm", 25),
                    "left_mm": margins.get("left_mm", 25),
                    "right_mm": margins.get("right_mm", 18),
                },
                "ruling": {
                    "line_count": rulings.get("line_count", 18),
                    "line_spacing_mm": rulings.get("line_spacing_mm", 8),
                    "style": config.get("line_style", "solid"),
                    "color": "gray",
                    "color_rgb": [100, 95, 85],
                },
                "vertical_divider": {
                    "exists": divider.get("exists", True),
                    "x_mm": divider.get("x_mm", 175),
                    "style": "solid",
                    "color": "gray",
                    "color_rgb": [100, 95, 85],
                },
                "reflection_zone": {
                    "exists": has_refl,
                    "label": refl_label,
                },
                "header": {"exists": True, "fields": header_fields},
                "preprinted_text": preprinted,
                "writing_area": {
                    "x_mm": margins.get("left_mm", 25),
                    "y_mm": margins.get("top_mm", 25),
                    "width_mm": page.get("width_mm", 210) - margins.get("left_mm", 25) - margins.get("right_mm", 18),
                    "height_mm": page.get("height_mm", 297) - margins.get("top_mm", 25) - margins.get("bottom_mm", 25),
                },
                "source": "glm_only",
                "warnings": self.warnings,
            }
        except Exception as e:
            raise RuntimeError(f"GLM-4V分析失败: {e}")
