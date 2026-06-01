"""Template store: JSON persistence for custom templates.

Custom templates are stored as JSON files in templates/*.json.
The template background IS the scanned photo (templates/photos/{id}.jpg).
No synthetic background generation — the photo is the template.
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
    """Load full template config from JSON file. Returns None for builtins."""
    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_template(config: dict, photo_bytes: bytes | None = None) -> str:
    """Save a template config as JSON + background photo. Returns template_id."""
    _ensure_dirs()

    tid = uuid.uuid4().hex[:12]
    # Remove non-serializable fields before JSON dump
    clean = {k: v for k, v in config.items() if not k.startswith("_") and not isinstance(v, bytes)}
    clean["id"] = tid
    clean["type"] = "custom"
    clean["created_at"] = datetime.now().isoformat()

    path = TEMPLATES_DIR / f"{tid}.json"
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

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

    for ext in (".jpg", ".png", ".jpeg"):
        photo = TEMPLATE_PHOTOS_DIR / f"{template_id}{ext}"
        if photo.exists():
            photo.unlink()
            break

    return True


def get_template_background_image(template_id: str) -> "Image.Image | None":
    """Load the saved photo as the template background. Returns None if not found."""
    from PIL import Image

    for ext in (".jpg", ".png", ".jpeg"):
        photo_path = TEMPLATE_PHOTOS_DIR / f"{template_id}{ext}"
        if photo_path.exists():
            img = Image.open(photo_path)
            # Resize to A4@300DPI if needed
            if img.size != (2480, 3508):
                # Keep aspect ratio, fit to 2480 wide
                ratio = 2480 / img.width
                new_h = int(img.height * ratio)
                img = img.resize((2480, new_h), Image.LANCZOS)
                # Pad to 3508 if shorter
                if new_h < 3508:
                    canvas = Image.new("RGB", (2480, 3508), (255, 255, 255))
                    canvas.paste(img, (0, 0))
                    img = canvas
                elif new_h > 3508:
                    img = img.crop((0, 0, 2480, 3508))
            return img

    return None
