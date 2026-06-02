"""教案纸模板系统：预设模板定义 + 区域匹配 + 背景生成。"""

import re
from PIL import Image, ImageDraw, ImageFont

# ── Template definitions ──────────────────────────────────────────

TEMPLATES = {
    "blank_a4": {
        "id": "blank_a4",
        "name": "纯白 A4 纸",
        "type": "blank",
        "regions": [],
    },
    "standard_a": {
        "id": "standard_a",
        "name": "通用教案表格式",
        "type": "builtin",
        "regions": [
            {"label": "课题", "x": 300, "y": 155, "w": 1880, "h": 70},
            {"label": "教学目标", "x": 140, "y": 266, "w": 2200, "h": 410},
            {"label": "教学重点", "x": 140, "y": 700, "w": 2200, "h": 140},
            {"label": "教学难点", "x": 140, "y": 864, "w": 2200, "h": 140},
            {"label": "教学准备", "x": 140, "y": 1028, "w": 2200, "h": 110},
            {"label": "教学过程", "x": 140, "y": 1162, "w": 2200, "h": 1196},
            {"label": "作业布置", "x": 140, "y": 2382, "w": 2200, "h": 196},
            {"label": "板书设计", "x": 140, "y": 2602, "w": 2200, "h": 396},
            {"label": "教学反思", "x": 140, "y": 3022, "w": 2200, "h": 296},
        ],
    },
    "standard_b": {
        "id": "standard_b",
        "name": "简约式",
        "type": "builtin",
        "regions": [
            {"label": "课题", "x": 220, "y": 180, "w": 2060, "h": 56},
            {"label": "教学目标", "x": 140, "y": 300, "w": 2200, "h": 500},
            {"label": "教学重点", "x": 140, "y": 840, "w": 2200, "h": 160},
            {"label": "教学难点", "x": 140, "y": 1040, "w": 2200, "h": 160},
            {"label": "教学准备", "x": 140, "y": 1240, "w": 2200, "h": 120},
            {"label": "教学过程", "x": 140, "y": 1400, "w": 2200, "h": 1200},
            {"label": "作业布置", "x": 140, "y": 2640, "w": 2200, "h": 200},
            {"label": "板书设计", "x": 140, "y": 2880, "w": 2200, "h": 320},
            {"label": "教学反思", "x": 140, "y": 3240, "w": 2200, "h": 200},
        ],
    },
}

# Mapping from AI markdown headings to template region labels
HEADING_TO_REGION = {
    "课题": "课题",
    "教学目标": "教学目标",
    "教学重点": "教学重点",
    "教学难点": "教学难点",
    "教学准备": "教学准备",
    "教学过程": "教学过程",
    "巩固练习": "教学过程",     # merged into 教学过程
    "课堂小结": "教学过程",     # merged into 教学过程
    "作业布置": "作业布置",
    "板书设计": "板书设计",
    "教学反思提示": "教学反思",
    "教学反思": "教学反思",
}

# ── Background image generation ───────────────────────────────────

_bg_cache: dict[str, Image.Image] = {}

PAPER_COLOR = (252, 249, 240)
LINE_COLOR = (180, 175, 165)
HEADER_BG = (245, 242, 232)
FONT_COLOR = (80, 75, 65)


def _try_get_font(size: int) -> ImageFont.FreeTypeFont | None:
    """Try to load a Chinese-capable font for label rendering."""
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


def _generate_standard_a_bg() -> Image.Image:
    """Generate the standard_a background: traditional table-style lesson plan paper."""
    W, H = 2480, 3508
    img = Image.new("RGB", (W, H), PAPER_COLOR)
    draw = ImageDraw.Draw(img)
    font = _try_get_font(36)
    font_small = _try_get_font(30)
    font_label = _try_get_font(40)

    # ── Outer border ──
    draw.rectangle([(40, 40), (W - 40, H - 40)], outline=LINE_COLOR, width=3)

    # ── Header section ──
    header_y1, header_y2 = 40, 148
    draw.rectangle([(40, header_y1), (W - 40, header_y2)], fill=HEADER_BG, outline=LINE_COLOR, width=2)

    # Vertical divider in header
    mid_x = W // 2
    draw.line([(mid_x, header_y1), (mid_x, header_y2)], fill=LINE_COLOR, width=1)

    # Header text
    _draw_text(draw, "学校：______________", 80, header_y1 + 32, font_small, FONT_COLOR)
    _draw_text(draw, "班级：______________", 80, header_y1 + 80, font_small, FONT_COLOR)
    _draw_text(draw, "教师：______________", mid_x + 30, header_y1 + 32, font_small, FONT_COLOR)
    _draw_text(draw, "日期：______________", mid_x + 30, header_y1 + 80, font_small, FONT_COLOR)

    # ── 课题 row ──
    topic_y1, topic_y2 = header_y2, 230
    draw.rectangle([(40, topic_y1), (W - 40, topic_y2)], outline=LINE_COLOR, width=2)
    _draw_text(draw, "课  题", 80, topic_y1 + 22, font_label, FONT_COLOR)

    # ── Section rows ──
    sections = [
        ("教学目标", topic_y2, 690),
        ("教学重点", 690, 855),
        ("教学难点", 855, 1020),
        ("教学准备", 1020, 1150),
        ("教学过程", 1150, 2360),
        ("作业布置", 2360, 2580),
        ("板书设计", 2580, 2990),
        ("教学反思", 2990, 3340),
    ]

    for label, y1, y2 in sections:
        draw.rectangle([(40, y1), (W - 40, y2)], outline=LINE_COLOR, width=2)
        # Label column on the left
        label_x1 = 40
        label_x2 = 130
        draw.rectangle([(label_x1, y1), (label_x2, y2)], fill=HEADER_BG, outline=LINE_COLOR, width=1)
        # Vertical text for label (draw rotated)
        _draw_vertical_label(draw, label, label_x1 + 6, y1 + 14, label_x2 - label_x1 - 12, y2 - y1 - 28, font_label)

    # ── Footer ──
    draw.rectangle([(40, 3340), (W - 40, H - 40)], outline=LINE_COLOR, width=2)

    return img


def _draw_vertical_label(draw, text, x, y, label_w, label_h, font):
    """Draw text vertically in the label column, one character per line."""
    if font is None:
        return
    chars_per_line = max(1, label_w // 50)
    char_h = min(50, label_h // max(1, len(text)))
    for i, ch in enumerate(text):
        cy = y + i * char_h
        if cy + char_h <= y + label_h:
            try:
                draw.text((x + (label_w - 30) // 2, cy), ch, font=font, fill=FONT_COLOR)
            except Exception:
                pass


def _generate_standard_b_bg() -> Image.Image:
    """Generate the standard_b background: simple style with just labels and lines."""
    W, H = 2480, 3508
    img = Image.new("RGB", (W, H), PAPER_COLOR)
    draw = ImageDraw.Draw(img)
    font_label = _try_get_font(42)

    # ── Outer frame ──
    draw.rectangle([(80, 80), (W - 80, H - 80)], outline=LINE_COLOR, width=2)

    # ── Title ──
    _draw_text(draw, "教  案", W // 2 - 80, 100, _try_get_font(52), (60, 50, 35))

    # ── Section labels + separator lines ──
    sections = [
        ("课题", 180, 260),
        ("教学目标", 300, 820),
        ("教学重点", 840, 1020),
        ("教学难点", 1040, 1220),
        ("教学准备", 1240, 1380),
        ("教学过程", 1400, 2620),
        ("作业布置", 2640, 2860),
        ("板书设计", 2880, 3220),
        ("教学反思", 3240, 3460),
    ]

    for label, y1, y2 in sections:
        _draw_text(draw, f"【{label}】", 140, y1 + 10, font_label, FONT_COLOR)
        draw.line([(120, y2), (W - 120, y2)], fill=LINE_COLOR, width=1)

    return img


def _draw_text(draw, text, x, y, font, color):
    """Safe text drawing that handles missing fonts."""
    if font is None:
        draw.text((x, y), text, fill=color)
    else:
        draw.text((x, y), text, font=font, fill=color)


def get_template_background(template_id: str) -> Image.Image | None:
    """Get (cached) background image for a template."""
    if template_id == "blank_a4":
        return None
    if template_id in _bg_cache:
        return _bg_cache[template_id].copy()

    generators = {
        "standard_a": _generate_standard_a_bg,
        "standard_b": _generate_standard_b_bg,
    }
    gen = generators.get(template_id)
    if gen:
        bg = gen()
        _bg_cache[template_id] = bg
        return bg.copy()

    # Try custom template — generate clean electronic background from config
    from services.template_store import get_template_config, generate_background_image
    custom_config = get_template_config(template_id)
    if custom_config:
        bg = generate_background_image(custom_config)
        _bg_cache[template_id] = bg
        return bg.copy()

    return None


# ── Content section parsing ───────────────────────────────────────

def parse_markdown_sections(markdown: str) -> dict[str, str]:
    """Split markdown content by ## headings into {heading: content} dict.

    Subsections (###) are included under their parent ## section.
    """
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in markdown.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            # Save previous section
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = stripped[3:].strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def match_sections_to_regions(
    sections: dict[str, str], regions: list[dict]
) -> dict[str, str]:
    """Map parsed markdown sections to template region labels.

    Returns {region_label: text_content} for each region that has matching content.
    Merges related headings (e.g. 巩固练习 → 教学过程).
    """
    matched: dict[str, str] = {}

    for heading, text in sections.items():
        region_label = HEADING_TO_REGION.get(heading)
        if region_label is None:
            continue
        # Strip the heading itself from the content — template backgrounds
        # already have section labels, so we only want the body text.
        body = text.strip()
        if region_label in matched:
            matched[region_label] += "\n\n" + body
        else:
            matched[region_label] = body

    return matched


def list_templates() -> list[dict]:
    """Return list of all available templates for the frontend (builtins + custom)."""
    builtins = [
        {"id": t["id"], "name": t["name"], "type": t["type"]}
        for t in TEMPLATES.values()
    ]
    from services.template_store import list_custom_templates
    customs = list_custom_templates()
    return builtins + customs
