#!/usr/bin/env python
"""GLM-4V template analyzer — analyze lesson plan notebook layout from a photo.

Image requirements:
  - Place the notebook open flat on a desk, showing a double-page spread
  - Place a ruler alongside for scale (cm side visible)
  - Good lighting, no shadows over the notebook

Usage:
  python tools/glm_vision.py D:\path\to\photo.jpg    # print text report
  python tools/glm_vision.py D:\path\to\photo.jpg --json  # print JSON to stdout
"""

import sys
import os
import json
import base64
from pathlib import Path
from openai import OpenAI

ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
if not GLM_API_KEY:
    print("ERROR: GLM_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)

GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
MODEL = "glm-4v"


def encode_image(path: str) -> str:
    fpath = Path(path)
    ext = fpath.suffix.lower()
    mime = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".bmp": "image/bmp",
    }.get(ext, "image/png")
    with open(fpath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


SYSTEM_PROMPT = """你是一个教案本模板分析器。你的任务是对照片中的教案本进行结构分析。

## 重要规则

1. **只看印刷的线和字** — 忽略任何手写内容。手写笔迹不是模板的一部分。
2. **只描述你实际看到的** — 如果你不确定某个元素是否存在，说"未检测到"。
3. **用尺子读数** — 照片中应该有尺子。用cm和mm报告测量值。
4. **区分左页和右页** — 本子展开后有左右两页，可能布局不同。
5. **输出严格JSON** — 不要JSON之外的内容。

## 输出格式

{
  "page_size": {
    "name": "A4 或 B5 或自定义",
    "width_mm": 数字,
    "height_mm": 数字,
    "note": "基于尺子测量的估算值"
  },
  "paper_color": "white 或 cream 或 yellowish",
  "left_page": { ...页面布局... },
  "right_page": { ...页面布局... },
  "global_notes": "任何通用说明"
}

## 页面布局对象格式

{
  "horizontal_lines": {
    "count": 整数,
    "color": "black 或 gray 或 dark_gray",
    "spacing_mm": 数字,
    "total_height_mm": 数字,
    "start_from_top_mm": 数字,
    "style": "solid 或 dotted"
  },
  "vertical_divider": {
    "exists": true 或 false,
    "position_from_left_mm": 数字,
    "reflection_zone_width_mm": 数字,
    "style": "solid 或 dotted",
    "color": "black 或 gray"
  },
  "margins": {
    "top_mm": 数字,
    "bottom_mm": 数字,
    "left_mm": 数字,
    "right_mm": 数字
  },
  "preprinted_text": [
    {
      "text": "印好的文字原文",
      "position": "top-left 或 top-right 或 top-center 或 header",
      "font_style": "regular 或 bold",
      "has_fill_in_blank": true 或 false,
      "approximate_location": "如：距顶部15mm，距左边20mm"
    }
  ],
  "info_header": {
    "exists": true 或 false,
    "height_mm": 数字,
    "fields": ["字段1", "字段2"],
    "description": "描述顶部信息栏的布局"
  }
}

## 测量方法

1. 用尺子校准：先在尺子上找到0cm的位置，然后读取页面边缘对应的刻度。
2. 横线间距 = 从第一根到最后一根横线的总距离 ÷ (行数 - 1)
3. 如果照片是双页展开，报告每一页的布局（左页和右页可能不同）。
4. 所有测量值四舍五入到0.1mm精度。"""


def analyze_template(image_path: str) -> dict:
    """Analyze a lesson plan notebook photo and return structured layout data."""
    data_url = encode_image(image_path)
    client = OpenAI(api_key=GLM_API_KEY, base_url=GLM_BASE_URL)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": SYSTEM_PROMPT + "\n\n请分析这张教案本照片的模板布局。旁边有尺子，用尺子刻度进行测量。输出严格JSON格式，不要JSON之外的内容。"},
                ],
            },
        ],
        max_tokens=4096,
        temperature=0.1,
    )

    text = response.choices[0].message.content

    # Try to extract JSON from the response
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code fences
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    if text.startswith("```json"):
        text = text[7:].strip()
        if text.endswith("```"):
            text = text[:-3]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "JSON解析失败", "raw_response": text}


# ─── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser("template_analyze", description="Analyze lesson plan notebook template from photo")
    ap.add_argument("image", help="Path to the notebook photo")
    ap.add_argument("--json", dest="as_json", action="store_true", help="Output raw JSON")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print the JSON result")
    args = ap.parse_args()

    result = analyze_template(args.image)

    if args.as_json:
        dump = json.dumps(result, ensure_ascii=False, indent=2)
        print(dump)
    else:
        # Pretty text report
        if "error" in result:
            print("=" * 60)
            print("ERROR:", result.get("error"))
            print("=" * 60)
            print(result.get("raw_response", "")[:3000])
        else:
            _ = result  # will use proper formatting
            print(json.dumps(result, ensure_ascii=False, indent=2))
