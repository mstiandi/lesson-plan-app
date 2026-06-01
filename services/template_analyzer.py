"""Template analyzer: document scan → GLM writing area detection.

Pipeline:
  1. Document scan: detect page corners → perspective warp → flat document
  2. GLM-4V: identify writing area boundaries and printed text labels
  3. The flat photo IS the template background — no synthetic re-drawing.
"""

import os
import json
import time
import numpy as np
from pathlib import Path
from PIL import Image

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Load .env early
_ENV_FILE = Path(__file__).parent.parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

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

    The scanned photo becomes the template background. GLM identifies
    the writing area so handright can position text correctly.
    """

    def __init__(self, photo_path: str):
        self.photo_path = photo_path
        self.warnings: list[str] = []
        self._flat_photo: bytes | None = None  # JPEG bytes of scanned image

    def analyze(self) -> dict:
        """Scan document, save flat photo, run GLM, return template config."""
        # 1. Document scan (perspective warp)
        image = cv2.imread(self.photo_path) if CV2_AVAILABLE else None
        if image is None:
            return self._glm_only_mode()

        flat = self._scan_document(image)
        if flat is None:
            self.warnings.append("未能检测文档边界，使用原始图像")
            flat = image
        else:
            self.warnings.append("已完成文档透视校正")
            image = flat

        # 2. Save flat image as JPEG bytes (the template background photo)
        success, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if success:
            self._flat_photo = buf.tobytes()

        # 3. Save temp image for GLM-4V
        flat_dir = Path(self.photo_path).parent
        temp_path = str(flat_dir / f"_flat_{int(time.time())}.jpg")
        cv2.imwrite(temp_path, image)

        # 4. GLM analysis (writing area + printed text only)
        glm_result = self._run_glm(temp_path)

        # 5. Cleanup
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except Exception: pass

        # 6. Build result
        result = self._build_config(glm_result)
        result["warnings"] = self.warnings
        result["_photo_bytes"] = self._flat_photo
        return result

    def get_photo_bytes(self) -> bytes | None:
        """Return JPEG bytes of the scanned flat image for saving."""
        return self._flat_photo

    # ══════════════════════════════════════════════════
    # Document scanner
    # ══════════════════════════════════════════════════

    def _scan_document(self, image: np.ndarray) -> np.ndarray | None:
        """Detect page corners, apply perspective warp → flat image."""
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (11, 11), 0)
        edges = cv2.Canny(blurred, 20, 60)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        dilated = cv2.dilate(edges, kernel, iterations=3)
        closed = cv2.erode(dilated, kernel, iterations=1)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_quad, best_area, img_area = None, 0, w * h

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < img_area * 0.20 or area > img_area * 0.98:
                continue
            peri = cv2.arcLength(cnt, True)
            corners = None
            for eps in [0.02, 0.03, 0.04, 0.05, 0.07]:
                approx = cv2.approxPolyDP(cnt, eps * peri, True)
                if len(approx) == 4:
                    corners = approx; break
            if corners is None:
                rect = cv2.minAreaRect(cnt)
                corners = cv2.boxPoints(rect)
                corners = np.intp(corners)
            quad = corners.reshape(-1, 2)
            if len(quad) != 4: continue
            rw = np.linalg.norm(quad[0] - quad[1])
            rh = np.linalg.norm(quad[1] - quad[2])
            if min(rw, rh) < 50: continue
            aspect = max(rw, rh) / min(rw, rh)
            if 0.5 < aspect < 2.5 and area > best_area:
                best_area, best_quad = area, quad

        if best_quad is None: return None

        pts = self._order_corners(best_quad)
        qw = int((np.linalg.norm(pts[0]-pts[1]) + np.linalg.norm(pts[2]-pts[3])) / 2)
        qh = int((np.linalg.norm(pts[1]-pts[2]) + np.linalg.norm(pts[3]-pts[0])) / 2)

        # Double-page spread → take left half
        if qw / max(1, qh) > 1.3:
            self.warnings.append("检测到双页展开，已提取左半页")
            mid = (pts[1][0] + pts[2][0]) / 2
            pts[1][0], pts[2][0] = mid, mid
            qw //= 2

        target_w = 2480
        target_h = int(target_w * qh / max(1, qw))
        dst = np.float32([[0, 0], [target_w-1, 0], [target_w-1, target_h-1], [0, target_h-1]])
        M = cv2.getPerspectiveTransform(np.float32(pts), dst)
        warped = cv2.warpPerspective(image, M, (target_w, target_h),
                                      borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        return warped

    @staticmethod
    def _order_corners(pts):
        pts = pts.reshape(4, 2)
        ordered = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        ordered[0] = pts[np.argmin(s)]
        ordered[2] = pts[np.argmax(s)]
        remaining = np.array([p for i, p in enumerate(pts) if i != np.argmin(s) and i != np.argmax(s)])
        if len(remaining) >= 2:
            ordered[1] = remaining[0] if remaining[0][1]-remaining[0][0] > remaining[1][1]-remaining[1][0] else remaining[1]
            ordered[3] = remaining[1] if remaining[0][1]-remaining[0][0] > remaining[1][1]-remaining[1][0] else remaining[0]
        return ordered

    # ══════════════════════════════════════════════════
    # GLM-4V: writing area + printed text only
    # ══════════════════════════════════════════════════

    def _run_glm(self, photo_path: str) -> dict:
        ask_glm = _get_glm()
        if ask_glm is None:
            return {"source": "glm_unavailable"}

        prompt = """这是透视校正拉平后的教案本照片(A4: 210×297mm)。

请找出**印刷好的**文字和写作区边界，JSON格式：

{
  "printed_title": "顶部居中印刷的完整标题（没有就null）",
  "printed_fields": ["印刷的填空字段如:第__周、课题：____"],
  "section_labels": ["印刷的栏目标签如:教学反思"],
  "writing_area_left_mm": 数字,
  "writing_area_right_mm": 数字,
  "writing_area_top_mm": 数字,
  "writing_area_bottom_mm": 数字,
  "has_right_divider": true或false,
  "divider_x_mm": 数字
}

规则：
- 印刷文字=宋体/楷体、颜色深、位置固定。手写笔迹忽略。
- writing_area是横线覆盖的可书写区域，从第一条横线到最后一条
- 如果竖线在右边(>150mm)那是反思区分隔线，在中间(<150mm)那是书脊折痕(要忽略)
- divider_x_mm填反思区竖线的位置，has_right_divider填true

只返回JSON。"""

        try:
            result = ask_glm(photo_path, prompt)
            result = result.strip()
            if "```" in result:
                for part in result.split("```")[1:]:
                    part = part.strip()
                    if part.startswith("json"): part = part[4:].strip()
                    if part.startswith("{"):
                        result = part; break
            return json.loads(result)
        except Exception as e:
            return {"source": "glm_error", "error": str(e)}

    # ══════════════════════════════════════════════════
    # Build config from GLM result
    # ══════════════════════════════════════════════════

    def _build_config(self, glm: dict) -> dict:
        glm_ok = isinstance(glm, dict) and glm.get("source") not in ("glm_unavailable", "glm_error")

        # Writing area (GLM provides)
        wa = {
            "x_mm": 25, "y_mm": 40,
            "width_mm": 160, "height_mm": 230,
        }
        if glm_ok:
            wa = {
                "x_mm": glm.get("writing_area_left_mm", 25),
                "y_mm": glm.get("writing_area_top_mm", 40),
                "width_mm": glm.get("writing_area_right_mm", 185) - glm.get("writing_area_left_mm", 25),
                "height_mm": glm.get("writing_area_bottom_mm", 270) - glm.get("writing_area_top_mm", 40),
            }

        # Divider
        divider = {"exists": False, "x_mm": None}
        if glm_ok:
            has_div = glm.get("has_right_divider", False)
            div_x = glm.get("divider_x_mm")
            if has_div and div_x and div_x > 150:
                divider = {"exists": True, "x_mm": div_x}

        # Printed text
        title = ""
        fields: list[str] = []
        section_labels: list[str] = []
        if glm_ok:
            title = glm.get("printed_title") or ""
            fields = glm.get("printed_fields") or []
            section_labels = glm.get("section_labels") or []
        preprinted = [{"text": t, "position": "top-left"}
                      for t in fields + section_labels]

        header = {"exists": bool(title or fields), "fields": []}
        if title:
            header["fields"].append(title)
        header["fields"].extend(fields)

        # Reflection
        reflection = {"exists": False}
        if divider["exists"]:
            refl_label = "教学反思"
            for s in section_labels:
                if "反思" in s:
                    refl_label = s; break
            reflection = {"exists": True, "label": refl_label,
                          "x_mm": divider["x_mm"],
                          "width_mm": 210 - (divider["x_mm"] or 175) - 18}

        # Margins derived from writing area
        margins = {
            "top_mm": wa["y_mm"],
            "bottom_mm": 297 - wa["y_mm"] - wa["height_mm"],
            "left_mm": wa["x_mm"],
            "right_mm": 210 - wa["x_mm"] - wa["width_mm"],
        }

        return {
            "page": {"width_mm": 210, "height_mm": 297,
                     "paper_color": "white", "paper_rgb": [255, 255, 255]},
            "margins": margins,
            "writing_area": wa,
            "ruling": {"line_count": 0, "line_spacing_mm": None,
                       "style": "solid", "color": "gray",
                       "color_rgb": [100, 95, 85]},
            "vertical_divider": {
                "exists": divider["exists"],
                "x_mm": divider.get("x_mm"),
                "style": "solid", "color": "gray",
                "color_rgb": [100, 95, 85],
            },
            "reflection_zone": reflection,
            "header": header,
            "preprinted_text": preprinted,
            "source": "opencv+glm" if glm_ok else "scan_only",
        }

    # ══════════════════════════════════════════════════
    # Fallback: no OpenCV → use GLM on original photo
    # ══════════════════════════════════════════════════

    def _glm_only_mode(self) -> dict:
        self.warnings.append("OpenCV未安装，无法扫描拉平，使用原图")
        ask_glm = _get_glm()
        if ask_glm is None:
            raise RuntimeError("GLM-4V不可用：请安装opencv-python-headless或设置GLM_API_KEY")

        prompt = """这是教案本照片(A4: 210×297mm)。请找出印刷文字和写作区边界，JSON：

{
  "printed_title": "顶部印刷标题或null",
  "printed_fields": ["印刷填空字段"],
  "section_labels": ["印刷栏目标签"],
  "writing_area_left_mm": 数字,
  "writing_area_right_mm": 数字,
  "writing_area_top_mm": 数字,
  "writing_area_bottom_mm": 数字,
  "has_right_divider": true或false,
  "divider_x_mm": 数字
}

只返回JSON。"""

        try:
            result = ask_glm(self.photo_path, prompt)
            result = result.strip()
            if "```" in result:
                for part in result.split("```")[1:]:
                    part = part.strip()
                    if part.startswith("json"): part = part[4:].strip()
                    if part.startswith("{"): result = part; break
            glm = json.loads(result)
            config = self._build_config(glm)
            config["source"] = "glm_only"

            # Save original as photo (no scan available)
            with open(self.photo_path, "rb") as f:
                config["_photo_bytes"] = f.read()

            config["warnings"] = self.warnings
            return config
        except Exception as e:
            raise RuntimeError(f"GLM-4V分析失败: {e}")
