# SPEC: v2.1 字体选择器

## 目标

将 Section 4（手写版PDF）的"默认字体 / 训练笔迹"二选一，改为**字体下拉选择器**。用户从预设的教师手写字体中选取风格，一键生成手写 PDF。笔迹训练降级为折叠的"高级"入口。

---

## 1. 新增字体

下载以下 3 个免费商用字体到 `fonts/` 目录：

| 字体 | 文件名 | 风格 | 来源 |
|------|--------|------|------|
| 鸿雷板书简体 | `HongLeiBanShu.ttf` | 板书手写，笔画有棱角顿挫 | 站酷/100font |
| 演示夏行楷 | `YanShiXiaXingKai.ttf` | 行楷，灵动连贯有流动感 | Keynote研究所 |
| 演示秋鸿楷 | `YanShiQiuHongKai.ttf` | 楷书端正，教师手写气质 | Keynote研究所 |

保留 `ZCOOLKuaiLe.ttf`（已有，卡通手写）。

---

## 2. 后端改动

### 2.1 `config.py` — 字体扫描

```python
def scan_fonts() -> list[dict]:
    fonts = []
    for f in sorted(FONTS_DIR.glob("*.ttf")) + sorted(FONTS_DIR.glob("*.otf")):
        fonts.append({"name": f.stem, "path": str(f)})
    return fonts
```

`f.stem` 输出不含扩展名的文件名，用作标识符（如 `HongLeiBanShu`）。

### 2.2 `main.py` — `/api/config` 返回字体列表

在现有返回体增加 `fonts` 字段：

```python
@app.get("/api/config")
async def get_config():
    from config import scan_fonts
    return {
        "model": MODEL,
        "api_ok": bool(API_KEY),
        "fonts": scan_fonts(),          # 新增
    }
```

注意：删掉原来的 `default_font` 和 `font_path` 字段（前端不再需要）。

### 2.3 `models.py` — `RenderRequest` 新增字段

```python
class RenderRequest(BaseModel):
    content: str
    session_id: str | None = None
    use_default: bool = True
    font_name: str | None = None     # 新增：指定字体文件名（不含扩展名）
```

### 2.4 `routes/lesson.py` — render 端点支持字体选择

```python
@router.post("/handwriting/render")
async def render_handwritten(req: RenderRequest):
    # 字体选择优先级：font_name > session_id > DEFAULT_FONT
    font_path = DEFAULT_FONT
    if req.font_name:
        from config import scan_fonts
        for f in scan_fonts():
            if f["name"] == req.font_name:
                font_path = f["path"]
                break
    elif req.use_default:
        font_path = DEFAULT_FONT

    # 后面不变...
```

---

## 3. 前端改动 `static/index.html`

### 3.1 替换 Section 4 HTML

**删掉：** 两个 radio（`hwMode`）、`hwDefaultMode` div、`hwTrainMode` 整个训练 UI（上传区、进度条、训练按钮）。

**换成：**

```html
<div class="section hidden" id="section4">
  <div class="section-title"><span class="section-number">4</span> 手写版PDF</div>

  <div class="form-row">
    <div>
      <label for="fontSelect">手写字体风格</label>
      <select id="fontSelect">
        <option value="">加载中…</option>
      </select>
    </div>
  </div>

  <button class="btn-primary btn-full" id="downloadBtn" onclick="downloadWithFont()">
    下载手写版PDF
  </button>

  <details style="margin-top:16px;">
    <summary style="font-size:13px;color:#888;cursor:pointer;">自定义笔迹（高级，上传手写照片训练）</summary>
    <!-- 这里保留原来的训练 UI：上传区、训练按钮、状态、渲染按钮 -->
    <!-- 全部折叠在 details 里面，默认不展开 -->
  </details>

  <div class="spinner" id="hwSpinner">正在渲染手写版PDF…</div>

  <div id="pdfPreview" class="hidden" style="margin-top:16px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span style="font-weight:600;">PDF 预览</span>
      <button class="btn-outline btn-sm" onclick="downloadPDF()">下载此PDF</button>
    </div>
    <iframe id="pdfFrame"></iframe>
  </div>
</div>
```

### 3.2 JS 改动

**初始化时填充字体列表：**
```js
async function loadFonts() {
  try {
    const r = await fetch('/api/config');
    const cfg = await r.json();
    const sel = document.getElementById('fontSelect');
    sel.innerHTML = '';
    cfg.fonts.forEach(f => {
      sel.innerHTML += `<option value="${f.name}">${f.name}</option>`;
    });
  } catch(e) {}
}
// 在 checkAPI 成功回调里调用 loadFonts()
```

**渲染函数简化：**
```js
async function downloadWithFont() {
  const content = document.getElementById('editor').innerText.trim();
  if (!content) return showError('请先生成教案内容');

  const fontName = document.getElementById('fontSelect').value;
  await renderAndDownload(content, null, true, fontName);
}

async function renderAndDownload(content, sid, useDefault, fontName) {
  // ... 现有逻辑 ...
  const r = await fetch('/api/handwriting/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content: content,
      session_id: sid,
      use_default: useDefault,
      font_name: fontName || null     // 新增
    })
  });
  // ... 后面不变 ...
}
```

### 3.3 样式

`details summary` 已有浏览器默认样式，只需微调：
```css
details summary { font-size: 13px; color: #888; cursor: pointer; margin-top: 16px; }
details summary:hover { color: #555; }
```

---

## 4. 交互流程（新）

```
填写课程信息 → 生成电子教案 → Section 4 展开
  → 下拉框选字体（已自动加载 fonts/ 下所有字体）
  → 点击「下载手写版PDF」
  → 用选中字体渲染 → 预览 → 下载
  → （可选）展开"自定义笔迹" → 上传照片训练 → 用训练字库渲染
```

## 5. 验收标准

- [ ] `/api/config` 返回 `fonts` 数组，包含所有 `fonts/` 下 .ttf/.otf
- [ ] 前端下拉框自动填充字体列表
- [ ] 选择不同字体，生成的 PDF 使用不同字体（肉眼可辨风格差异）
- [ ] 不选字体时，渲染用现有默认字体（向后兼容）
- [ ] 笔迹训练功能完整保留在 `<details>` 折叠区，功能不受影响
- [ ] `fonts/` 下至少有 4 个字体可用
