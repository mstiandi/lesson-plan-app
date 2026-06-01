#!/usr/bin/env python
"""GLM-4V vision tool — callable from command line or as Python module.
Usage:
  python tools/glm_vision.py <image_path> [prompt]
  python tools/glm_vision.py <image_path> --json   (structured output)
Provides: ask_glm(image_path: str, prompt: str) -> str
"""

import sys
import os
import base64
import json
from pathlib import Path

# Load env from parent .env if present
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
DEFAULT_MODEL = "glm-4v"  # GLM-4V for vision
SMALL_MODEL = "glm-4v-flash"  # faster/cheaper variant

if not GLM_API_KEY:
    print("ERROR: GLM_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)


def _encode_image(path: str) -> str:
    """Encode image to base64 data URL."""
    fpath = Path(path)
    if not fpath.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    ext = fpath.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")

    with open(fpath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def ask_glm(image_path: str, prompt: str = "请详细描述这张图片的内容。", model: str = None) -> str:
    """Send an image to GLM-4V and get a description back.

    Args:
        image_path: path to image file
        prompt: what to ask about the image
        model: glm-4v (default, full) or glm-4v-flash (faster/cheaper)

    Returns:
        GLM's text response
    """
    from openai import OpenAI

    model = model or DEFAULT_MODEL
    client = OpenAI(api_key=GLM_API_KEY, base_url=GLM_BASE_URL)
    data_url = _encode_image(image_path)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        max_tokens=2048,
        temperature=0.1,
    )
    return response.choices[0].message.content


# ─── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser("glm_vision", description="Ask GLM-4V about an image")
    ap.add_argument("image", help="Path to image file")
    ap.add_argument("prompt", nargs="?", default="请详细描述这张图片的内容。", help="Question about the image")
    ap.add_argument("--fast", action="store_true", help="Use glm-4v-flash for faster/cheaper response")
    ap.add_argument("--json", action="store_true", help="Request structured JSON output")
    args = ap.parse_args()

    prompt = args.prompt
    if args.json:
        prompt += "\n请以JSON格式回答。"

    model = SMALL_MODEL if args.fast else DEFAULT_MODEL
    result = ask_glm(args.image, prompt, model=model)
    print(result)
