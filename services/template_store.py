"""Template store: JSON persistence for custom templates + background rendering.

Custom templates are stored as JSON files in templates/*.json.
Background images are generated on-demand from template config.
Builtin templates (blank_a4, standard_a, standard_b) cannot be deleted.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from config import TEMPLATES_DIR, TEMPLATE_PHOTOS_DIR

# ── CRUD ──────────────────────────────────────────────────────────────


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
    """Load full template config from JSON file. Returns None for builtins."""
    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_template(config: dict, photo_bytes: bytes | None = None) -> str:
    """Save a template config as JSON. Returns the template_id."""
    _ensure_dirs()

    tid = uuid.uuid4().hex[:12]
    config["id"] = tid
    config["type"] = "custom"
    config["created_at"] = datetime.now().isoformat()

    path = TEMPLATES_DIR / f"{tid}.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    if photo_bytes:
        photo_path = TEMPLATE_PHOTOS_DIR / f"{tid}.jpg"
        photo_path.write_bytes(photo_bytes)

    return tid


def delete_template(template_id: str) -> bool:
    """Delete a custom template. Returns False if not found or is builtin."""
    BUILTINS = {"blank_a4", "standard_a", "standard_b"}
    if template_id in BUILTINS:
        return False

    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        return False

    path.unlink()

    # Delete photo if exists
    for ext in (".jpg", ".png", ".jpeg"):
        photo = TEMPLATE_PHOTOS_DIR / f"{template_id}{ext}"
        if photo.exists():
            photo.unlink()
            break

    return True


# ── Background image generation ──────────────────────────────────────

def generate_background_image(config: dict) -> "Image.Image":
    """Generate an A4@300DPI background image from template config.

    Renders a realistic lesson plan notebook page:
    - Pure white paper (for printing)
    - Top header: notebook title + info fields with fill-in blanks
    - Horizontal ruling lines in the main writing area
    - Vertical divider for the reflection zone
    - Reflection zone label
    """
    from PIL import Image, ImageDraw, ImageFont

    W, H = 2480, 3508  # A4 @ 300 DPI
    DPI = 300

    def mm_to_px(mm_val):
        return int(mm_val * DPI / 25.4)

    # ── Paper: always pure white for printing ──
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # ── Fonts ──
    font_header = _load_font(48)       # title
    font_label = _load_font(28)        # field labels
    font_reflection = _load_font(26)   # reflection zone label

    # ── Geometry ──
    margins = config.get("margins", {})
    rulings = config.get("ruling", {})
    divider = config.get("vertical_divider", {})
    header_cfg = config.get("header", {})
    preprinted = config.get("preprinted_text", [])

    ml = mm_to_px(margins.get("left_mm", 20))
    mr = mm_to_px(margins.get("right_mm", 15))
    mt = mm_to_px(margins.get("top_mm", 18))

    line_count = rulings.get("line_count", 22)
    line_spacing_mm = rulings.get("line_spacing_mm", 8)
    line_spacing_px = mm_to_px(line_spacing_mm or 8)

    LINE_COLOR = (100, 95, 85)  # Dark gray — visible when printed
    TEXT_COLOR = (60, 55, 45)
    DIVIDER_COLOR = (100, 95, 85)

    # Writing area right edge (before the divider, if present)
    if divider.get("exists") and divider.get("x_mm"):
        right_edge_x = mm_to_px(divider["x_mm"])
    else:
        right_edge_x = W - mr

    # ── Page border (thin, like a printed form) ──
    border_margin = mm_to_px(12)
    draw.rectangle(
        [(border_margin, border_margin), (W - border_margin, H - border_margin)],
        outline=(80, 75, 65), width=2,
    )

    # ── TOP SECTION: Header area ──
    header_top = mt
    header_height = 0

    # 1. Title line: "教师备课笔记" centered
    title = "教 师 备 课 笔 记"
    if font_header and header_cfg.get("exists"):
        hdr_fields = header_cfg.get("fields", [])
        if hdr_fields:
            title = hdr_fields[0]  # Use first field as title

    if font_header:
        bbox = font_header.getbbox(title)
        tw = bbox[2] - bbox[0]
        title_x = (W - tw) // 2
        title_y = header_top
        draw.text((title_x, title_y), title, font=font_header, fill=TEXT_COLOR)
        header_height += 60

    # Decorative line under title
    deco_y = title_y + 58
    draw.line(
        [(ml, deco_y), (right_edge_x, deco_y)],
        fill=(60, 55, 45), width=2,
    )
    draw.line(
        [(ml, deco_y + 3), (right_edge_x, deco_y + 3)],
        fill=(60, 55, 45), width=1,
    )
    header_height += 15

    # 2. Info fields row
    info_y = deco_y + 20

    # Build info fields from config or defaults
    if header_cfg.get("exists") and len(header_cfg.get("fields", [])) > 1:
        info_fields = header_cfg["fields"][1:]  # Skip title
    else:
        info_fields = ["第____周", "星期____", "____年____月____日", "课题：______________"]

    if info_fields:
        total_fields = len(info_fields)
        # Split into two rows if many fields
        for row_idx in range(0, total_fields, 3):
            row_fields = info_fields[row_idx:row_idx + 3]
            field_w = (right_edge_x - ml) // max(1, len(row_fields))
            for i, ftext in enumerate(row_fields):
                fx = ml + i * field_w
                if font_label:
                    draw.text((fx + 8, info_y + row_idx * 36), ftext,
                              font=font_label, fill=TEXT_COLOR)

    header_height += 80  # Info fields area
    header_bottom = info_y + header_height

    # ── Ruling lines ──
    line_start_y = header_bottom + mm_to_px(5)  # Small gap after header
    line_y1 = line_start_y
    line_y2 = H - mm_to_px(margins.get("bottom_mm", 18))

    # Recalculate line_count to fill available space
    available_h = line_y2 - line_y1
    actual_line_count = available_h // line_spacing_px

    for i in range(actual_line_count):
        y = line_y1 + i * line_spacing_px
        if y >= line_y2:
            break
        draw.line([(ml, y), (right_edge_x, y)], fill=LINE_COLOR, width=1)

    # ── Vertical divider ──
    if divider.get("exists") and divider.get("x_mm"):
        vx = mm_to_px(divider["x_mm"])
        vy1 = line_y1
        vy2 = line_y2
        draw.line([(vx, vy1), (vx, vy2)], fill=DIVIDER_COLOR, width=2)

        # ── Reflection zone label (vertical, on the right side) ──
        refl = config.get("reflection_zone", {})
        if refl.get("exists"):
            refl_label = refl.get("label", "教学反思")
            if font_reflection:
                refl_x = vx + mm_to_px(3)
                refl_y = vy1 + mm_to_px(5)

                # Draw label at top of reflection zone
                draw.text((refl_x, refl_y), refl_label,
                          font=font_reflection, fill=TEXT_COLOR)

                # Light dotted line under reflection label
                label_h = 30
                dash_x1 = vx + mm_to_px(1)
                dash_x2 = W - mr - mm_to_px(2)
                dash_y = refl_y + label_h
                seg = 30
                for sx in range(dash_x1, dash_x2, seg + 15):
                    draw.line(
                        [(sx, dash_y), (min(sx + seg, dash_x2), dash_y)],
                        fill=(180, 175, 165), width=1,
                    )

    # ── Preprinted text labels (from config, e.g. 课题 mark) ──
    if preprinted and font_label:
        for item in preprinted:
            text = item.get("text", "")
            pos = item.get("position", "top-left")
            x_mm = item.get("x_mm")
            y_mm = item.get("y_mm")
            if x_mm is not None and y_mm is not None:
                draw.text(
                    (mm_to_px(x_mm), mm_to_px(y_mm)),
                    text, font=font_label, fill=TEXT_COLOR,
                )

    return img


def _load_font(size: int):
    """Load a Chinese-capable font for label rendering."""
    from PIL import ImageFont
    candidates = [
        "C:/Windows/Fonts/STKAITI.TTF",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return None
