# SPEC: v2.5 教案纸模板系统

## 目标

在现有"纯 A4 白纸"基础上，**增**加教案纸模板选择。用户可选择预设通用模板，或上传自己学校的空白教案纸照片/扫描件，系统自动识别表格布局，将手写内容填入对应区域。

## 用户流程

```
Section 4（手写版PDF）
  → 纸张样式选择：
    ○ 纯白 A4 纸（现有）
    ○ 通用教案表格式（预设 3 种）
    ○ 上传我的教案纸（自定义）
```

---

## 1. 预设模板（3 种）

内置 3 种常见教案纸模板，覆盖大多数学校格式：

| 模板 | 名称 | 说明 |
|------|------|------|
| 通用 A | 传统表格式 | 表头（学校/班级/教师/日期/课题）+ 7 个栏目横排 |
| 通用 B | 简约式 | 无表头，仅栏目名称 + 分隔线 |
| 通用 C | 空白 A4 | 米黄纸 + 淡外框，纯自由书写（即现在这个） |

### 模板数据结构

```python
# services/templates.py（新文件）
TEMPLATES = {
    "blank_a4": {
        "name": "纯白 A4 纸",
        "type": "blank",
        "background": None,           # 用 make_paper_texture 生成
        "regions": [],                # 无固定区域，全文自由流
    },
    "standard_a": {
        "name": "通用教案表格式",
        "type": "builtin",
        "background": "templates/standard_a_bg.png",  # 预制的表头 + 栏目框架
        "regions": [
            {"label": "课题", "x": 300, "y": 180, "w": 1800, "h": 60},
            {"label": "教学目标", "x": 140, "y": 280, "w": 2200, "h": 400},
            {"label": "教学重点", "x": 140, "y": 700, "w": 2200, "h": 150},
            {"label": "教学难点", "x": 140, "y": 870, "w": 2200, "h": 150},
            {"label": "教学准备", "x": 140, "y": 1040, "w": 2200, "h": 120},
            {"label": "教学过程", "x": 140, "y": 1180, "w": 2200, "h": 1200},
            {"label": "作业布置", "x": 140, "y": 2400, "w": 2200, "h": 200},
            {"label": "板书设计", "x": 140, "y": 2620, "w": 2200, "h": 400},
            {"label": "教学反思", "x": 140, "y": 3040, "w": 2200, "h": 300},
        ],
    },
    # standard_b: 简约版，类似但无表头
}
```

### 区域渲染逻辑

```python
def render_with_template(content: str, template: dict, font_path: str) -> Image.Image:
    """
    1. 按 AI 生成的 markdown 标题（## 课题, ## 教学目标, ...）拆分内容
    2. 匹配到模板的 regions
    3. 每个 region 内用 Handright 渲染对应文字
    4. 粘贴到背景图的对应坐标区域
    """
```

> 关键：AI 输出是 markdown 结构（`## 课题`, `## 教学目标`...），
> 天然可以按标题拆分成段落，匹配到模板区域。

---

## 2. 自定义模板：上传空白教案纸照片

### 2.1 上传

用户用手机拍一张**空白教案纸**（没写字的），上传。支持 JPG/PNG。

### 2.2 自动识别布局

```
上传图片 → 预处理（透视矫正/二值化）
  → 检测水平/垂直线（霍夫变换）→ 找表格边界
  → 切分成矩形区域
  → EasyOCR 识别每个区域的标签文字
  → 匹配到我们的内容段落（"教学目标" → 教学目标文字）
  → 保存模板：背景图 + region 坐标 + label 映射
```

### 2.3 技术细节

```python
def detect_form_layout(image: Image.Image) -> list[dict]:
    """
    返回检测到的区域列表，每个区域包含：
    - label: OCR 识别的标签文字（如 "教学目标"）
    - x, y, w, h: 区域坐标
    - matched_section: 匹配到的内容段落名
    """
    # 1. 转灰度 + 自适应阈值
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, ...)

    # 2. 霍夫线检测找横线和竖线
    lines = cv2.HoughLinesP(binary, ...)
    h_lines, v_lines = separate_horizontal_vertical(lines)

    # 3. 找线交点 → 确定单元格边界
    cells = find_cells(h_lines, v_lines)

    # 4. 对每个单元格跑 EasyOCR 识别标签
    for cell in cells:
        label_text = easyocr_read(cell_image)
        section = match_to_sections(label_text)

    return regions
```

### 2.4 用户确认

识别完成后，前端展示预览图，标注检测到的区域。用户可：
- 确认（"看起来对，直接用"）
- 手动微调某个区域的边界
- 手动输入某区域的标签名（OCR 识别错时）

### 2.5 存储

自定义模板保存在 `templates/{template_id}/`：
- `background.png` — 预处理后的空白表格背景图
- `layout.json` — 区域坐标 + 标签映射
- `meta.json` — 模板名称、创建时间

### 2.6 前端 UI

```html
<!-- Section 4 新增纸张样式选择 -->
<div class="form-row col-1" style="margin-bottom:12px;">
  <label>教案纸样式</label>
  <select id="paperTemplate" onchange="onTemplateChange()">
    <option value="blank_a4">纯白 A4 纸</option>
    <option value="standard_a">通用教案表格式</option>
    <option value="standard_b">简约式</option>
    <option value="custom">上传我的教案纸…</option>
  </select>
</div>

<!-- 自定义模板区域（默认隐藏） -->
<div id="customTemplateArea" class="hidden" style="margin-bottom:12px;">
  <div class="upload-zone" id="templateUploadZone"
       onclick="document.getElementById('templateFileInput').click()">
    <p>📷 上传空白教案纸照片（未填写内容的）</p>
    <p style="font-size:12px;color:#bbb;">手机平拍，光线均匀，JPG/PNG</p>
    <input type="file" id="templateFileInput" accept="image/*"
           onchange="uploadTemplate(event)">
  </div>
  <div id="templatePreview" class="hidden" style="margin-top:8px;">
    <p style="font-size:13px;color:#888;">检测到以下区域：</p>
    <img id="templatePreviewImg" style="max-width:100%;border:1px solid #ddd;border-radius:4px;">
    <button class="btn-outline btn-sm" onclick="confirmTemplate()">确认使用此模板</button>
  </div>
</div>
```

### 2.7 新增 API

| Method | Path | 说明 |
|--------|------|------|
| `POST` | `/api/template/upload` | 上传空白教案纸照片，返回检测结果 |
| `POST` | `/api/template/confirm` | 确认检测结果，保存为模板 |
| `GET` | `/api/templates` | 列出所有可用模板（预设 + 用户自定义）|
| `POST` | `/api/handwriting/render` | 现有接口，新增 `template_id` 参数 |

### 2.8 `RenderRequest` 新增字段

```python
class RenderRequest(BaseModel):
    content: str
    font_name: str | None = None
    session_id: str | None = None
    use_default: bool = True
    scribble_prob: float = 0.0
    template_id: str = "blank_a4"    # 新增
```

---

## 3. 电子版表格上传

如果用户有 Word/PDF 格式的空白教案模板（很多学校教务处会发），支持直接上传：

- `.docx`：用 `python-docx` 读取，解析表格结构
- `.pdf`：用 `pdf2image` 渲染为图片，然后走图片检测流程

> 此功能为 Phase 2，MVP 先做图片上传。

---

## 4. 文件改动

| 文件 | 改动 |
|------|------|
| `services/templates.py` | **新建** — 模板定义、上传处理、布局检测 |
| `services/handwriting.py` | `render_handwritten_pages` 支持 `template_id` |
| `models.py` | `RenderRequest` + `template_id` |
| `routes/lesson.py` | 新增 `/api/template/*` 路由 |
| `static/index.html` | Section 4 新增纸张样式选择 + 上传 UI |
| `requirements.txt` | + `opencv-python-headless`（霍夫线检测）|

---

## 5. 实现阶段

### Phase A: 预设模板（先做）
- 3 个预设模板（blank_a4, standard_a, standard_b）
- 区域自动匹配渲染
- `template_id` 参数透传

### Phase B: 自定义上传（后做）
- 图片上传 + 布局检测 + 用户确认
- 保存/加载自定义模板

---

## 6. 验收标准

- [ ] 选择"通用教案表格式"→ 下载 PDF 内容填在对应栏目框内
- [ ] 选择"纯白 A4 纸"→ 和现在效果一致
- [ ] 上传一张空白教案纸照片 → 返回检测到的区域列表
- [ ] 确认区域 → 保存模板 → 下次可选
- [ ] 不同学校的表格布局不同 → 各能正确识别
