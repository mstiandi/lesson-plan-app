import random
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF
from handright import Template, handwrite
from config import DEFAULT_FONT, CHAR_SIZE, HANDWRITING_BANKS_DIR

_reader = None
_ocr_available = None  # None = not yet probed


def _get_reader():
    """Lazy-init EasyOCR reader. First call downloads model (~100MB), subsequent calls reuse."""
    global _reader, _ocr_available
    if _ocr_available is None:
        try:
            import easyocr
            _reader = easyocr.Reader(['ch_sim'], gpu=False, verbose=False)
            _ocr_available = True
        except Exception:
            _reader = None
            _ocr_available = False
    return _reader if _ocr_available else None


def make_paper_texture(w: int, h: int) -> Image.Image:
    """Create a paper-textured background image with ruling lines and noise."""
    img = Image.new("RGB", (w, h), (252, 249, 240))
    pixels = img.load()
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            noise = random.randint(-4, 4)
            pixels[x, y] = (
                max(0, min(255, r + noise)),
                max(0, min(255, g + noise)),
                max(0, min(255, b + noise)),
            )
    return img


def add_scribble_marks(page: Image.Image, font_path: str, prob: float) -> Image.Image:
    """Post-process a page to add random scribble/correction marks.

    prob: 0.0–1.0. Higher = more and denser marks.
    """
    if prob <= 0:
        return page

    draw = ImageDraw.Draw(page)
    W, H = page.width, page.height

    # Number of marks = prob * 40 (min 5)
    n_marks = max(5, int(prob * 40))

    for _ in range(n_marks):
        mode = random.choice(['strikethrough', 'strikethrough', 'strikethrough', 'blob', 'circle'])

        x1 = random.randint(80, W - 200)
        y1 = random.randint(200, H - 300)

        if mode == 'strikethrough':
            # Dark rough lines, like real pen crossing out text
            line_w = random.randint(80, 240)
            ink = random.randint(10, 30)
            roughness = random.randint(3, 6)
            for _ in range(roughness):
                y = y1 + random.randint(-5, 5)
                draw.line(
                    [(x1 + random.randint(-3, 3), y), (x1 + line_w + random.randint(-3, 3), y)],
                    fill=(ink, ink, ink),
                    width=random.randint(2, 4),
                )
        elif mode == 'blob':
            # Dark blob, like marker/pen covering text
            bw = random.randint(35, 90)
            bh = random.randint(14, 28)
            ink = random.randint(15, 40)
            draw.ellipse([(x1, y1), (x1 + bw, y1 + bh)], fill=(ink, ink, ink))
        else:  # circle
            # Circle around a word, like teacher correction
            r = random.randint(25, 60)
            ink = random.randint(10, 40)
            draw.ellipse(
                [(x1 - r, y1 - r // 2), (x1 + r, y1 + r // 2)],
                outline=(ink, ink, ink),
                width=random.randint(2, 3),
            )

    return page


def preprocess_image(img: Image.Image) -> Image.Image:
    """Grayscale + adaptive threshold binarization + denoise."""
    gray = img.convert("L")
    # Simple threshold for MVP
    pixels = gray.load()
    w, h = gray.size
    for y in range(h):
        for x in range(w):
            pixels[x, y] = 0 if pixels[x, y] < 140 else 255
    return gray


def extract_chars_from_image(image_path: str) -> list[dict]:
    """Use EasyOCR to detect and recognize characters in an image."""
    reader = _get_reader()
    if reader is None:
        return []

    results = reader.readtext(image_path)
    if not results:
        return []

    chars = []

    for bbox_corners, text, confidence in results:
        if confidence < 0.5:
            continue

        x_coords = [p[0] for p in bbox_corners]
        y_coords = [p[1] for p in bbox_corners]
        x1, y1 = int(min(x_coords)), int(min(y_coords))
        x2, y2 = int(max(x_coords)), int(max(y_coords))

        for i, char in enumerate(text):
            char_w = (x2 - x1) / len(text)
            cx1 = int(x1 + char_w * i)
            cx2 = int(cx1 + char_w)
            bbox = (cx1, y1, cx2 - cx1, y2 - y1)
            chars.append({
                "char": char,
                "bbox": bbox,
                "confidence": confidence,
                "source_photo": Path(image_path).name,
            })

    return chars


def normalize_char_image(char_img: Image.Image, size: int = CHAR_SIZE) -> Image.Image:
    """Resize char to target size, keeping aspect ratio, pad with white."""
    w, h = char_img.size
    if w <= 0 or h <= 0:
        return Image.new("L", (size, size), 255)

    ratio = min((size - 8) / w, (size - 8) / h)
    new_w, new_h = int(w * ratio), int(h * ratio)

    resized = char_img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("L", (size, size), 255)
    offset_x = (size - new_w) // 2
    offset_y = (size - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))

    return canvas


def _render_region_printed(text: str, region: dict) -> Image.Image | None:
    """Render text into a region using a clean print font (楷体).

    Used for template mode — the filled content should look typewritten,
    not handwritten, since the template simulates pre-printed school forms.
    """
    rw, rh = region["w"], region["h"]
    if rh < 20 or not text.strip():
        return None

    # Use print font (楷体), fallback to default
    print_font_path = "C:/Windows/Fonts/STKAITI.TTF"
    try:
        from pathlib import Path
        if not Path(print_font_path).exists():
            print_font_path = None
    except Exception:
        print_font_path = None

    region_bg = make_paper_texture(rw, rh)
    draw = ImageDraw.Draw(region_bg)

    # Fit font size to region
    font_size = min(36, rh // 2)
    if font_size < 12:
        return region_bg

    font = None
    if print_font_path:
        try:
            font = ImageFont.truetype(print_font_path, font_size)
        except Exception:
            pass

    # Word wrap
    lines = []
    chars_per_line = max(1, rw // (font_size + 2))
    for paragraph in text.split("\n"):
        para = paragraph.strip()
        if not para:
            lines.append("")
            continue
        while len(para) > chars_per_line:
            lines.append(para[:chars_per_line])
            para = para[chars_per_line:]
        lines.append(para)

    line_height = font_size + 8
    y = 6
    for line in lines:
        if y + line_height > rh - 4:
            break
        if line:
            if font:
                draw.text((10, y), line, font=font, fill=(50, 50, 50))
            else:
                draw.text((10, y), line, fill=(50, 50, 50))
        y += line_height

    return region_bg


def _render_region(
    text: str, region: dict, font_path: str, line_height: int, font_size: int
) -> Image.Image | None:
    """Render a section of text within a bounded region.

    Uses Handright for regions tall enough (>=110px). Falls back to PIL
    text rendering for small single-line regions.
    """
    rw, rh = region["w"], region["h"]
    if rh < 40 or not text.strip():
        return None

    # For very short regions, use PIL directly — Handright needs ~110px minimum
    if rh < 110:
        return _render_region_pil(text, rw, rh, font_path, font_size)

    from handright import Template, handwrite

    region_bg = make_paper_texture(rw, rh)
    params = _handright_params(font_path, font_size, line_height)
    font = ImageFont.truetype(font_path, params["font_size"])

    template = Template(
        background=region_bg,
        font=font,
        line_spacing=params["line_height"],
        fill=params["fill"],
        left_margin=8,
        top_margin=6,
        right_margin=8,
        bottom_margin=6,
        word_spacing=0,
        line_spacing_sigma=params["line_spacing_sigma"],
        font_size_sigma=params["font_size_sigma"],
        word_spacing_sigma=params["word_spacing_sigma"],
        start_chars='"「（《『',
        perturb_x_sigma=params["perturb_x_sigma"],
        perturb_y_sigma=params["perturb_y_sigma"],
        perturb_theta_sigma=params["perturb_theta_sigma"],
    )

    try:
        pages = list(handwrite(text, template))
        if pages:
            return pages[0]
    except Exception:
        pass
    return None


def _render_region_pil(
    text: str, rw: int, rh: int, font_path: str, font_size: int
) -> Image.Image | None:
    """Render text into a small region using PIL (no handwriting perturbation).

    Used as fallback for regions too small for Handright (< 110px tall).
    """
    import random
    region_bg = make_paper_texture(rw, rh)
    draw = ImageDraw.Draw(region_bg)

    # Scale font down to fit region height
    fit_size = min(font_size, rh - 16)
    if fit_size < 12:
        return region_bg

    try:
        font = ImageFont.truetype(font_path, fit_size)
    except Exception:
        return region_bg

    # Add slight randomness to simulate handwriting
    ink = (random.randint(38, 48), random.randint(28, 38), random.randint(18, 30))
    dx = int(random.gauss(0, 1.5))
    dy = int(random.gauss(0, 1.0))

    draw.text((10 + dx, 6 + dy), text, font=font, fill=ink)
    return region_bg


def render_handwritten_pages(
    content: str,
    font_path: str = None,
    session_id: str = None,
    scribble_prob: float = 0.0,
    template_id: str = "blank_a4",
) -> list[Image.Image]:
    """Render text as handwritten pages.

    Supports two modes:
    - blank_a4: Full A4 free-form rendering (existing Handright flow)
    - builtin templates: Sectioned rendering into template regions
    """
    W, H = 2480, 3508  # A4 @ 300 DPI
    MARGIN_LEFT, MARGIN_RIGHT = 280, 200
    MARGIN_TOP, MARGIN_BOTTOM = 260, 240
    LINE_HEIGHT = 76
    FONT_SIZE = 58
    CHAR_SPACING = 60

    font_path = font_path or DEFAULT_FONT
    if not font_path:
        raise ValueError("No font available")

    from services.ai import strip_markdown
    plain = strip_markdown(content)

    # ── Template mode (non-blank) ──
    if template_id and template_id != "blank_a4":
        from services.templates import (
            get_template_background,
            parse_markdown_sections,
            match_sections_to_regions,
        )
        bg = get_template_background(template_id)
        if bg is None:
            # Fallback to blank A4
            return render_handwritten_pages(content, font_path, session_id, scribble_prob, "blank_a4")

        sections = parse_markdown_sections(content)
        template = __import__("services.templates", fromlist=["TEMPLATES"]).TEMPLATES.get(template_id, {})
        regions = template.get("regions", [])
        matched = match_sections_to_regions(sections, regions)

        for region in regions:
            text = matched.get(region["label"], "")
            if text:
                text = strip_markdown(text)
                if text.strip():
                    region_img = _render_region_printed(text, region)
                    if region_img:
                        bg.paste(region_img, (region["x"], region["y"]))

        if scribble_prob > 0:
            bg = add_scribble_marks(bg, font_path, scribble_prob)

        return [bg]

    # ── Blank A4 mode (existing flow) ──
    # Check if we have char bank data
    char_cache = {}
    if session_id:
        try:
            from db import get_chars_db, get_chars_for
            conn = get_chars_db(session_id)
            for ch in plain:
                if ch not in char_cache and ch.strip():
                    variants = get_chars_for(conn, ch)
                    if variants:
                        char_cache[ch] = variants
        except Exception:
            pass

    has_bank = len(char_cache) > 0

    if has_bank:
        pages = _render_with_char_bank(
            plain, font_path, session_id, char_cache,
            W, H, MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM,
            LINE_HEIGHT, CHAR_SPACING, FONT_SIZE,
        )
    else:
        pages = _render_with_handright(
            plain, font_path, W, H,
            MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM,
            LINE_HEIGHT, FONT_SIZE,
        )

    # Apply scribble marks
    if scribble_prob > 0:
        pages = [add_scribble_marks(p, font_path, scribble_prob) for p in pages]

    return pages


def _handright_params(font_path: str, base_font_size: int, base_line_height: int) -> dict:
    """Return per-font Handright parameters.

    Thin running-script fonts (ZhiMangXing, YShiWritten) need larger size, darker ink,
    and gentler perturbation — their strokes are naturally finer.
    Regular/楷书 fonts can use standard params.
    """
    import os
    name = os.path.basename(font_path).lower()

    # Thin / running-script fonts: bigger, darker, less shake
    if any(k in name for k in ('zhimang', 'yshiwritten', 'xiaolai')):
        return {
            "font_size": base_font_size + 10,   # 68 for thin fonts
            "line_height": base_line_height + 6,
            "fill": (22, 14, 6),                # dark sepia
            "line_spacing_sigma": 0.8,
            "font_size_sigma": 0.6,
            "word_spacing_sigma": 0.8,
            "perturb_x_sigma": 1.0,
            "perturb_y_sigma": 1.0,
            "perturb_theta_sigma": 0.025,
        }
    # Regular fonts: standard params
    return {
        "font_size": base_font_size,
        "line_height": base_line_height,
        "fill": (40, 30, 20),
        "line_spacing_sigma": 1.0,
        "font_size_sigma": 1.0,
        "word_spacing_sigma": 1.2,
        "perturb_x_sigma": 2.0,
        "perturb_y_sigma": 2.0,
        "perturb_theta_sigma": 0.06,
    }


def _render_with_handright(
    plain: str, font_path: str,
    W: int, H: int,
    MARGIN_LEFT: int, MARGIN_RIGHT: int,
    MARGIN_TOP: int, MARGIN_BOTTOM: int,
    LINE_HEIGHT: int, FONT_SIZE: int,
) -> list[Image.Image]:
    """Render using Handright stroke-level perturbation engine."""
    paper_bg = make_paper_texture(W, H)

    params = _handright_params(font_path, FONT_SIZE, LINE_HEIGHT)
    font = ImageFont.truetype(font_path, params["font_size"])

    template = Template(
        background=paper_bg,
        font=font,
        line_spacing=params["line_height"],
        fill=params["fill"],
        left_margin=MARGIN_LEFT,
        top_margin=MARGIN_TOP,
        right_margin=MARGIN_RIGHT,
        bottom_margin=MARGIN_BOTTOM,
        word_spacing=0,
        line_spacing_sigma=params["line_spacing_sigma"],
        font_size_sigma=params["font_size_sigma"],
        word_spacing_sigma=params["word_spacing_sigma"],
        start_chars='"「（《『',
        perturb_x_sigma=params["perturb_x_sigma"],
        perturb_y_sigma=params["perturb_y_sigma"],
        perturb_theta_sigma=params["perturb_theta_sigma"],
    )

    try:
        pages = list(handwrite(plain, template))
    except Exception:
        pages = list(handwrite(plain, template))

    return pages


def _render_with_char_bank(
    plain: str, font_path: str, session_id: str, char_cache: dict,
    W: int, H: int,
    MARGIN_LEFT: int, MARGIN_RIGHT: int,
    MARGIN_TOP: int, MARGIN_BOTTOM: int,
    LINE_HEIGHT: int, CHAR_SPACING: int, FONT_SIZE: int,
) -> list[Image.Image]:
    """Per-character rendering with bank image lookup + font fallback."""
    usable_w = W - MARGIN_LEFT - MARGIN_RIGHT
    chars_per_line = usable_w // CHAR_SPACING
    lines_per_page = (H - MARGIN_TOP - MARGIN_BOTTOM) // LINE_HEIGHT

    paragraphs = plain.split("\n")
    raw_lines = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            raw_lines.append("")
            continue
        while len(para) > chars_per_line:
            raw_lines.append(para[:chars_per_line])
            para = para[chars_per_line:]
        raw_lines.append(para)

    all_page_lines = []
    i = 0
    while i < len(raw_lines):
        all_page_lines.append(raw_lines[i:i + lines_per_page])
        i += lines_per_page

    font = None
    try:
        font = ImageFont.truetype(font_path, FONT_SIZE)
    except Exception:
        pass

    pages = []
    for page_lines in all_page_lines:
        img = make_paper_texture(W, H)

        for line_idx, line in enumerate(page_lines):
            y_base = MARGIN_TOP + line_idx * LINE_HEIGHT
            x = MARGIN_LEFT

            for char in line:
                if char in (" ", "\t"):
                    x += CHAR_SPACING
                    continue

                char_img = None
                if char in char_cache:
                    variants = char_cache[char]
                    if variants:
                        variant = random.choice(variants)
                        img_path = HANDWRITING_BANKS_DIR / session_id / variant["image_path"]
                        if img_path.exists():
                            char_img = Image.open(img_path).convert("RGBA")

                if char_img is not None:
                    angle = random.gauss(0, 1.5)
                    scale = random.gauss(1.0, 0.03)
                    dx = int(random.gauss(0, 2))
                    dy = int(random.gauss(0, 2))
                    cw = int(char_img.width * scale)
                    ch = int(char_img.height * scale)
                    if cw > 2 and ch > 2:
                        char_img = char_img.resize((cw, ch), Image.LANCZOS)
                        if abs(angle) > 0.4:
                            char_img = char_img.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
                        img.paste(char_img, (int(x + dx), int(y_base + dy - 5)), char_img)
                elif font is not None:
                    dx = int(random.gauss(0, 0.8))
                    dy = int(random.gauss(0, 1.0))
                    angle = random.gauss(0, 1.2)
                    scale = random.gauss(1.0, 0.02)
                    char_size = max(12, int(FONT_SIZE * scale))
                    try:
                        char_font = ImageFont.truetype(font_path, char_size) if char_size != FONT_SIZE else font
                    except Exception:
                        char_font = font
                    bbox = char_font.getbbox(char)
                    cw, ch = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    if cw <= 0 or ch <= 0:
                        x += CHAR_SPACING
                        continue
                    pad = 8
                    tmp = Image.new("RGBA", (cw + pad * 2, ch + pad * 2), (0, 0, 0, 0))
                    tmp_draw = ImageDraw.Draw(tmp)
                    ink = random.randint(38, 55)
                    tmp_draw.text((pad - bbox[0], pad - bbox[1]), char, font=char_font, fill=(ink, random.randint(28, 45), random.randint(20, 38)))
                    if abs(angle) > 0.4:
                        tmp = tmp.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
                    img.paste(tmp, (int(x + dx), int(y_base + dy - 5)), tmp)

                x += CHAR_SPACING + int(random.gauss(0, 0.6))

        pages.append(img)

    return pages


def pages_to_pdf(pages: list[Image.Image]) -> bytes:
    if not pages:
        raise ValueError("No pages to render")

    pdf = FPDF(unit="pt", format="A4")
    for page in pages:
        buf = io.BytesIO()
        page.save(buf, format="JPEG", quality=92)
        buf.seek(0)
        pdf.add_page()
        pdf.image(buf, x=0, y=0, w=595.28, h=841.89)

    return bytes(pdf.output())


def render_font_preview(font_path: str, text: str = "教案设计 教学目标 重难点") -> bytes:
    """Render a short text line with the given font, return PNG bytes."""
    font_size = 28
    font = ImageFont.truetype(font_path, font_size)

    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pad = 16
    w, h = tw + pad * 2, th + pad * 2

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=(50, 50, 50))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
