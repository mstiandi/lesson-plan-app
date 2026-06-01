import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

API_KEY = (
    os.environ.get("ANTHROPIC_API_KEY")
    or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    or ""
)
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
MODEL = "deepseek-chat"

FONTS_DIR = BASE_DIR / "fonts"
UPLOADS_DIR = BASE_DIR / "uploads"
HANDWRITING_BANKS_DIR = BASE_DIR / "handwriting_banks"
STATIC_DIR = BASE_DIR / "static"

FONT_DISPLAY_NAMES = {
    "ZhiMangXing-Regular": "钟齐志莽行书（行书·推荐）",
    "LXGWWenKai-Regular": "霞鹜文楷（楷书）",
    "Xiaolai-Regular": "小赖手写体",
    "LXGWZhenKaiGB-Regular": "霞鹜臻楷",
    "YShiWrittenSC-Regular": "写意体（手写简体）",
    "Yozai-Regular": "悠哉手写体",
    "MaokenYingBiKaiShuJ": "猫啃硬笔楷书",
    "ZCOOLKuaiLe": "站酷快乐体",
}


def scan_fonts() -> list[dict]:
    """Return all .ttf/.otf files in fonts/ directory with display names."""
    fonts = []
    for f in sorted(FONTS_DIR.glob("*.ttf")) + sorted(FONTS_DIR.glob("*.otf")):
        display_name = FONT_DISPLAY_NAMES.get(f.stem, f.stem)
        fonts.append({
            "name": f.stem,
            "display": display_name,
            "path": str(f),
            "preview_url": f"/api/font-preview/{f.stem}",
        })
    return fonts


DEFAULT_FONT = None
_fonts = scan_fonts()
if _fonts:
    DEFAULT_FONT = _fonts[0]["path"]
else:
    for candidate in ["C:/Windows/Fonts/STKAITI.TTF"]:
        if os.path.exists(candidate):
            DEFAULT_FONT = candidate
            break

THREAD_POOL_SIZE = 3
OCR_CONFIDENCE_THRESHOLD = 0.7
CHAR_SIZE = 64
SESSION_TTL_DAYS = 7
MAX_UPLOAD_PHOTOS = 10
MIN_UPLOAD_PHOTOS = 3
PORT = 8877

# ── Template system ──
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATE_PHOTOS_DIR = TEMPLATES_DIR / "photos"
TEMPLATE_MAX_PHOTO_SIZE_MB = 20
TEMPLATE_PREVIEW_WIDTH = 600
