# SPEC: v2.3 Handright 手写渲染引擎

## 目标

将手写 PDF 渲染从当前的"字体渲染 + 整字随机扰动"替换为 **Handright 笔画级扰动引擎**，输出效果从"像打印的字体"升级为"像真人写的字"。同时新增可选的**涂改痕迹模拟**。

## 现状 vs 目标

| | 当前（v2.1） | 目标（v2.3） |
|---|---|---|
| 扰动粒度 | 整字级（旋转±1.5°, 缩放±3%） | **笔画级**（每笔独立偏移/旋转） |
| 同一字多次出现 | 完全一样 | **每次不同**（笔画随机扰动） |
| 墨水变化 | 单色 | **深浅微变**（模拟笔压） |
| 涂改痕迹 | 无 | **可选**（划掉+重写，概率可调） |
| 笔迹训练字库 | 有字库时贴图 | 不变（保留原逻辑） |
| 字体选择 | 5 种 | 不变（Handright 用任意 TTF） |

## 技术方案

### 1. 安装依赖

```bash
pip install handright
```

`requirements.txt` 新增一行：`handright>=10.0.0`

### 2. 替换渲染引擎 `services/handwriting.py`

**删掉：** 当前的 `make_paper_texture` + `render_handwritten_pages`（约 160 行逐字符渲染逻辑）。

**新增：** 基于 Handright 的 `render_handwritten_pages_v3()`。

```python
from handright import Template, handwrite

def render_handwritten_pages_v3(
    content: str,
    font_path: str,
    session_id: str = None,
    scribble_prob: float = 0.0,   # 涂改概率 0.0–1.0
) -> list[Image.Image]:
    """
    用 Handright 笔画级引擎渲染手写教案。
    
    Args:
        content: 纯文本内容（已 strip markdown）
        font_path: 字体文件路径
        session_id: 笔迹训练 session（有则优先用字库贴图）
        scribble_prob: 涂改概率（0=无涂改, 0.05=每页约1-2处涂改）
    """
    # ... 见下文详细设计
```

### 3. Handright 配置参数

```python
from PIL import ImageFont

# A4 @ 150 DPI
PAGE_W, PAGE_H = 1240, 1754
MARGIN_LEFT, MARGIN_RIGHT = 140, 100
MARGIN_TOP, MARGIN_BOTTOM = 130, 120
LINE_HEIGHT = 58
FONT_SIZE = 30
CHAR_SPACING = 33     # Handright 模板参数

template = Template(
    background=paper_background,          # PIL Image，纸张纹理底图
    font=ImageFont.truetype(font_path, FONT_SIZE),
    line_spacing=LINE_HEIGHT,
    fill=(50, 40, 30),                    # 基础墨色
    left_margin=MARGIN_LEFT,
    top_margin=MARGIN_TOP,
    right_margin=MARGIN_RIGHT,
    bottom_margin=MARGIN_BOTTOM,
    word_spacing=0,                        # 汉字间不额外加空格
    line_spacing_sigma=2,                  # 行距随机抖动 ±2px
    font_size_sigma=1.2,                   # 字号随机抖动 ±1.2pt
    word_spacing_sigma=1.5,               # 字距随机抖动 ±1.5px
    start_chars="“「（《『",             # 不缩进的起始字符
    need_to_change_word_spacing=False,     # 不用西文空格逻辑
    perturb_x_sigma=2.5,                  # 笔画横向扰动 ±2.5px
    perturb_y_sigma=2.5,                  # 笔画纵向扰动 ±2.5px
    perturb_theta_sigma=0.08,             # 笔画旋转扰动 ±0.08 rad ≈ 4.6°
)
```

### 4. 涂改痕迹模拟

在 Handright 渲染完成后，对每页图像进行后处理：

```python
import random

def add_scribble_marks(page: Image.Image, text_lines: list[str], prob: float) -> Image.Image:
    """
    以 prob 概率随机在文本行中模拟涂改痕迹。
    
    涂改类型（随机选一种）：
    1. 单横线划掉 — 在随机一个词上画 1-2 条横线
    2. 涂黑块 — 在随机位置画一个深色椭圆/矩形块
    3. 圈掉重写 — 圈起一个词，旁边写更正
    """
    if prob <= 0:
        return page
    
    draw = ImageDraw.Draw(page)
    
    for line_text in text_lines:
        if random.random() > prob:
            continue
        
        # 随机选一种涂改方式
        mode = random.choice(['strikethrough', 'blob', 'circle_rewrite'])
        
        if mode == 'strikethrough':
            # 随机选一个词位置，画 1-2 条横线
            ...
        elif mode == 'blob':
            # 画一个深色椭圆块
            ...
        elif mode == 'circle_rewrite':
            # 画一个圈 + 旁边写小字更正
            ...
    
    return page
```

### 5. 笔迹训练字库模式（保留）

当 `session_id` 存在且字库中有对应字符时，**优先使用字库字模贴图**（和现在逻辑一样）。字库字模本身是真人手写照片裁剪，不需要 Handright 扰动——它已经是自然的了。

```python
# 渲染优先级：
# 1. 字库中有该字符 → 用字库字模（现有逻辑，不变）
# 2. 字库中无该字符 → 用 Handright 渲染（新增）
```

### 6. 分页逻辑

Handright 的 `handwrite()` 函数接受文本行列表，自动计算换行和分页。我们只需预先将纯文本按行宽切分，传入即可。当前 `strip_markdown` + 按 `chars_per_line` 切分的逻辑保留。

### 7. 前端改动 `static/index.html`

Section 4 新增涂改开关：

```html
<div class="form-row" style="margin-top:8px;">
  <div>
    <label for="scribbleSlider">
      涂改痕迹：<span id="scribbleVal">0%</span>
    </label>
    <input type="range" id="scribbleSlider" min="0" max="10" value="0" step="1"
           oninput="document.getElementById('scribbleVal').textContent = this.value*10 + '%'">
  </div>
</div>
```

JS 渲染时传递涂改参数：

```js
body: JSON.stringify({
    content: content,
    session_id: sid,
    use_default: useDefault,
    font_name: selectedFont,
    scribble_prob: parseInt(document.getElementById('scribbleSlider').value) / 100,  // 新增
})
```

### 8. `models.py` — `RenderRequest` 新增字段

```python
class RenderRequest(BaseModel):
    content: str
    session_id: str | None = None
    use_default: bool = True
    font_name: str | None = None
    scribble_prob: float = 0.0    # 新增：0.0–1.0
```

### 9. `routes/lesson.py` — render 端点适配

传给 `render_handwritten_pages_v3()` 时，传入 `scribble_prob` 参数。

## 文件改动清单

| 文件 | 改动 |
|------|------|
| `requirements.txt` | + `handright>=10.0.0` |
| `services/handwriting.py` | 替换 `render_handwritten_pages` 为 Handright 版本 + 涂改后处理 |
| `models.py` | `RenderRequest` + `scribble_prob` |
| `routes/lesson.py` | render 端点透传 `scribble_prob` |
| `static/index.html` | Section 4 + 涂改滑块 |

## 验收标准

- [ ] `pip install handright` 后可正常渲染
- [ ] 同一段文字渲染两次，笔画细节不同（非确定性随机）
- [ ] 5 种字体全部可用（Handright 使用 Pillow ImageFont）
- [ ] 涂改概率 0% = 无痕迹，10% = 明显有划掉/涂黑
- [ ] 笔迹训练字库模式不受影响
- [ ] PDF 输出保持 A4 格式，带横格线 + 纸张纹理
- [ ] 和当前版本效果对比，肉眼可见更"像人写的"
