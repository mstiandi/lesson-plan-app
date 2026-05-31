# SPEC: v2.2 字体预览示例

## 目标

字体下拉选择器旁边显示一行该字体的短示例文字（如"教案设计 教学目标"），让教师直观看到每种字体的实际效果，不用每次下载 PDF 才能对比。

## 方案

服务端渲染字体预览图（PNG），前端在 `<select>` 下方以卡片列表展示。

选服务端而非客户端 @font-face 的原因：字体文件 1.5-25MB，浏览器加载太慢。

## 后端改动

### 1. `config.py` — 字体预览 API 路由

新增 `font_preview` 函数和路由：

```python
# config.py 或 services/handwriting.py
def render_font_preview(font_path: str, text: str = "教案设计 教学目标 重难点") -> bytes:
    """用指定字体渲染一行文字的小图，返回 PNG bytes。"""
    from PIL import Image, ImageDraw, ImageFont

    font_size = 28
    font = ImageFont.truetype(font_path, font_size)

    # 测量文字尺寸
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
```

### 2. `routes/lesson.py` — 字体预览接口

```python
@router.get("/font-preview/{font_name}")
async def font_preview(font_name: str, text: str = "教案设计 教学目标 重难点"):
    from config import scan_fonts
    for f in scan_fonts():
        if f["name"] == font_name:
            png = render_font_preview(f["path"], text)
            return Response(content=png, media_type="image/png")
    raise HTTPException(status_code=404, detail="Font not found")
```

### 3. `/api/config` — 字体列表附带预览 URL

`scan_fonts()` 返回的 dict 新增 `preview_url` 字段：

```python
def scan_fonts() -> list[dict]:
    fonts = []
    for f in sorted(...):
        fonts.append({
            "name": f.stem,
            "display": FONT_DISPLAY_NAMES.get(f.stem, f.stem),
            "path": str(f),
            "preview_url": f"/api/font-preview/{f.stem}",   # 新增
        })
    return fonts
```

## 前端改动 `static/index.html`

### 1. 字体选择 UI 改为卡片列表

原来：纯 `<select>` 下拉框。  
换成：卡片式字体选择器，每张卡片显示字体名 + 预览图。

```html
<!-- Section 4，替换现有 <select id="fontSelect"> -->
<label>手写字体风格</label>
<div class="font-cards" id="fontCards">
  <!-- JS 动态填充 -->
</div>
```

```css
.font-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}
@media (max-width: 600px) {
  .font-cards { grid-template-columns: 1fr; }
}
.font-card {
  border: 2px solid #ddd;
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.15s;
  background: #fff;
}
.font-card:hover { border-color: #4a7c59; }
.font-card.selected { border-color: #4a7c59; background: #f0f7f1; }
.font-card .font-preview-img {
  width: 100%;
  height: 36px;
  object-fit: contain;
  object-position: left center;
  margin-bottom: 4px;
}
.font-card .font-name {
  font-size: 13px;
  color: #555;
  text-align: center;
}
```

### 2. JS 逻辑

```js
let selectedFont = null;

async function loadFonts() {
  const r = await fetch('/api/config');
  const cfg = await r.json();
  const container = document.getElementById('fontCards');
  container.innerHTML = '';

  cfg.fonts.forEach((f, i) => {
    const card = document.createElement('div');
    card.className = 'font-card';
    card.innerHTML = `
      <img class="font-preview-img" src="${f.preview_url}" alt="${f.display}" loading="lazy">
      <div class="font-name">${f.display}</div>
    `;
    card.onclick = () => {
      document.querySelectorAll('.font-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      selectedFont = f.name;
    };
    container.appendChild(card);

    if (i === 0) {   // 默认选中第一个
      card.classList.add('selected');
      selectedFont = f.name;
    }
  });
}
```

## 交互流程

```
Section 4 展开 → 字体卡片网格显示 5 张预览图
  → 点击某张卡片 → 高亮选中
  → 点击「下载手写版PDF」→ 用选中字体渲染
```

## 示例文字

默认预览文字：`教案设计 教学目标 重难点`（10 个字，最能代表教案书写效果）。

可选：在卡片下方加一个输入框让教师自定义预览文字（非 MVP）。

## 范围外（不做）

- 预览图缓存（PIL 渲染很快，无需缓存）
- 自定义预览文字（MVP 用固定文字）
- 预览图支持训练笔迹模式（训练笔迹是字符图库，无法生成连续预览）

## 改动量

- `config.py`：`scan_fonts()` 加 `preview_url` 字段
- `routes/lesson.py`：加 `/api/font-preview/{font_name}` 接口
- `services/handwriting.py`：加 `render_font_preview()` 函数
- `static/index.html`：`<select>` 换卡片列表 + 样式 + JS 逻辑

4 个文件，30 分钟。
