"""Template store: JSON persistence for custom templates.

Custom templates are stored as JSON files in templates/*.json.
The background is generated from config as a clean electronic replica.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from config import TEMPLATES_DIR, TEMPLATE_PHOTOS_DIR


def _ensure_dirs():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


def list_custom_templates() -> list[dict]:
    """Scan templates/*.json and return summary list."""
    _ensure_dirs()
    templates = []
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
            templates.append({
                "id": cfg.get("id", f.stem),
                "name": cfg.get("name", f.stem),
                "type": cfg.get("type", "custom"),
                "created_at": cfg.get("created_at", ""),
            })
        except Exception:
            continue
    return templates


def get_template_config(template_id: str) -> dict | None:
    """Load full template config from JSON file."""
    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_template(config: dict, photo_bytes: bytes | None = None) -> str:
    """Save config as JSON. Returns template_id."""
    _ensure_dirs()
    tid = uuid.uuid4().hex[:12]
    clean = {k: v for k, v in config.items()
             if not k.startswith("_") and not isinstance(v, bytes)}
    clean["id"] = tid
    clean["type"] = "custom"
    clean["created_at"] = datetime.now().isoformat()
    (TEMPLATES_DIR / f"{tid}.json").write_text(
        json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    if photo_bytes:
        (TEMPLATE_PHOTOS_DIR / f"{tid}.jpg").write_bytes(photo_bytes)
    return tid


def delete_template(template_id: str) -> bool:
    """Delete a custom template. False if not found or is builtin."""
    if template_id in {"blank_a4", "standard_a", "standard_b"}:
        return False
    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        return False
    path.unlink()
    for ext in (".jpg", ".png", ".jpeg"):
        p = TEMPLATE_PHOTOS_DIR / f"{template_id}{ext}"
        if p.exists():
            p.unlink()
            break
    return True


# ── Background generation: clean electronic template ──────────────

def generate_background_image(config: dict) -> "Image.Image":
    """Generate a clean A4@300DPI electronic template from config.

    Replicates the original notebook structure from measured parameters:
    pure white paper, border, title, info fields, ruling lines,
    vertical divider, reflection zone label.
    """
    from PIL import Image, ImageDraw, ImageFont

    W, H = 2480, 3508  # A4 @ 300 DPI
    DPI = 300

    def mm_to_px(mm_val):
        return int(mm_val * DPI / 25.4)

    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # ── Fonts ──
    font_title = _load_font(52)       # main title
    font_field = _load_font(28)       # info fields
    font_small = _load_font(24)       # reflection label

    # ── Colors ──
    LINE_CLR = (90, 85, 75)        # ruling lines — visible when printed
    BORDER_CLR = (70, 65, 55)      # outer border
    TEXT_CLR = (60, 55, 45)        # printed labels
    DECO_CLR = (60, 55, 45)        # decorative elements

    # ── Read config ──
    margins = config.get("margins", {})
    rulings = config.get("ruling", {})
    divider = config.get("vertical_divider", {})
    header_cfg = config.get("header", {})
    preprinted = config.get("preprinted_text", [])
    refl = config.get("reflection_zone", {})

    ml = mm_to_px(margins.get("left_mm", 24))
    mr = mm_to_px(margins.get("right_mm", 18))
    mt = mm_to_px(margins.get("top_mm", 24))
    mb = mm_to_px(margins.get("bottom_mm", 24))

    line_count = rulings.get("line_count", 18)
    line_spacing_mm = rulings.get("line_spacing_mm", 8)
    line_spacing_px = mm_to_px(line_spacing_mm if line_spacing_mm else 8)

    # Divider
    divider_x_mm = divider.get("x_mm", 175) if divider else 175
    has_divider = divider.get("exists", False) if divider else False
    if not has_divider:
        # Default: assume divider exists for custom templates
        has_divider = bool(divider_x_mm)

    # ── Outer border ──
    bm = mm_to_px(10)
    draw.rectangle([(bm, bm), (W - bm, H - bm)], outline=BORDER_CLR, width=2)

    # ── Header area ──
    header_y = mt
    header_fields = header_cfg.get("fields", []) if header_cfg else []
    title_text = header_fields[0] if header_fields and header_fields[0] else ""

    if title_text:
        if font_title:
            bbox = font_title.getbbox(title_text)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, header_y), title_text,
                      font=font_title, fill=TEXT_CLR)
        header_y += 68

        # Decorative double line under title
        deco_y = header_y - 10
        right_edge = mm_to_px(divider_x_mm) if has_divider else W - mr
        draw.line([(ml, deco_y), (right_edge, deco_y)], fill=DECO_CLR, width=2)
        draw.line([(ml, deco_y + 3), (right_edge, deco_y + 3)], fill=DECO_CLR, width=1)
        header_y += 18

    # ── Info fields ──
    info_fields = header_fields[1:] if len(header_fields) > 1 else []
    if info_fields:
        right_edge = mm_to_px(divider_x_mm) if has_divider else W - mr
        avail_w = right_edge - ml
        cols = min(3, len(info_fields))
        col_w = avail_w // cols

        for i, ftext in enumerate(info_fields):
            col = i % cols
            row = i // cols
            fx = ml + col * col_w
            fy = header_y + row * 38
            if font_field:
                draw.text((fx + 10, fy + 4), ftext,
                          font=font_field, fill=TEXT_CLR)
        header_y += ((len(info_fields) - 1) // cols + 1) * 38 + 12

    # ── Ruling lines ──
    if has_divider:
        line_right = mm_to_px(divider_x_mm) - mm_to_px(2)
    else:
        line_right = W - mr

    line_top = header_y + mm_to_px(4)
    line_bottom = H - mb

    # Recalculate line count to fill available space
    actual_lines = (line_bottom - line_top) // max(1, line_spacing_px)

    for i in range(actual_lines):
        y = line_top + i * line_spacing_px
        if y >= line_bottom:
            break
        draw.line([(ml, y), (line_right, y)], fill=LINE_CLR, width=1)

    # ── Vertical divider ──
    if has_divider:
        vx = mm_to_px(divider_x_mm)
        vy1 = line_top
        vy2 = line_bottom - line_spacing_px
        draw.line([(vx, vy1), (vx, vy2)], fill=LINE_CLR, width=2)

        # ── Reflection zone label ──
        if refl.get("exists", True) and font_small:
            refl_label = refl.get("label", "教学反思")
            refl_x = vx + mm_to_px(2)
            draw.text((refl_x, vy1 + mm_to_px(3)), refl_label,
                      font=font_small, fill=TEXT_CLR)

            # Light separator under label
            label_h = 28
            dash_y = vy1 + mm_to_px(3) + label_h
            for sx in range(vx + 2, W - mm_to_px(12), 28):
                draw.line([(sx, dash_y), (min(sx + 18, W - mm_to_px(12)), dash_y)],
                          fill=(180, 175, 165), width=1)

    # ── Preprinted text labels ──
    if preprinted and font_field:
        for item in preprinted:
            text = item.get("text", "")
            pos = item.get("position", "top-left")
            x_mm = item.get("x_mm")
            y_mm = item.get("y_mm")
            if x_mm is not None and y_mm is not None:
                draw.text((mm_to_px(x_mm), mm_to_px(y_mm)), text,
                          font=font_field, fill=TEXT_CLR)

    return img


def _load_font(size: int):
    from PIL import ImageFont
    for path in [
        "C:/Windows/Fonts/STKAITI.TTF",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return None
