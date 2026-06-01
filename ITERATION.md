# ITERATION.md — 教案草稿生成器 v2

## 迭代 1: Phase 1 基础重构

**架构师计划：** SPEC.md Phase 1 (2026-05-30)

### 落地师实现

**完成内容：**
- 创建 `requirements.txt`（所有依赖）
- 创建 `config.py`（环境变量、路径常量）
- 创建 `models.py`（Pydantic 请求/响应模型）
- 创建 `db.py`（SQLite 字库 CRUD + 元数据管理）
- 创建 `routes/lesson.py`（7 个 API 端点：config, generate, locations, handwriting upload/train/status/render）
- 创建 `services/ai.py`（增强 system prompt + 学校上下文注入）
- 创建 `services/location.py`（行政区划数据加载 + 教学要求匹配）
- 创建 `services/handwriting.py`（PaddleOCR 集成 + 字库渲染引擎）
- 创建 `services/location_requirements.json`（省市教学要求库，覆盖 12 个省/市）
- 重构 `main.py`（薄层 FastAPI app 创建 + 路由挂载 + static mount）
- 重写 `static/index.html`（四段式布局：学校信息 → 教学信息 → 电子教案编辑器 → 手写版PDF）
- 创建 `static/locations.json`（34 省 + 283 市 + 863 区县，精简版覆盖主要城市）
- 创建 `.gitignore`

**偏差：**
- SPEC 中 `handwriting.py` 路由文件独立，实际合并到 `routes/lesson.py`（handwriting 端点不足以独立成文件）
- SPEC 中前端 resize 到 1200px 在浏览器端做，实际改为服务端 resize（避免前端 Canvas 兼容问题）
- SPEC 中 `GET /api/handwriting/status/{session_id}` 返回 TrainStatusResponse，实际返回完整 meta dict（更灵活）

**问题：** 无

**待确认：**
- PaddleOCR 首次加载模型约 100MB，需在实际运行时验证
- `services/location_requirements.json` 目前只有 12 个省/市的教学要求，后续可扩展
- 前端 `contenteditable` 在移动端的编辑体验需要实测

**状态：** 审查就绪

---

### 架构师审查

**LGTM on architecture.** 路由层薄、服务层厚、数据模型清晰。前端四段式布局和三级联动交互符合 SPEC。

**NEEDS-WORK: 2 个必须修，3 个建议修。**

#### 🔴 必须修

1. **PaddleOCR 未安装 — 笔迹训练功能完全不可用** `services/handwriting.py:9-15`
   - `paddleocr` 不在当前 Python 环境中，`OCR_AVAILABLE` 恒为 `False`
   - `extract_chars_from_image()` 永远返回 `[]`，训练永远产出 0 字
   - 前端训练流程能跑通（上传→训练→状态轮询），但字库永远是空的
   - **修法**：装 `paddlepaddle` + `paddleocr`，或换 EasyOCR（纯 Python，安装更简单）

2. **`aiofiles` 是死依赖** `requirements.txt:9`
   - 全项目没有任何 `import aiofiles`，没有 `aiofiles.open()` 调用
   - **修法**：从 `requirements.txt` 删掉这行

#### 🟡 建议修

3. **locations.json 数据量远低于声称** `static/locations.json`
   - ITERATION 声称"~330 市 + ~2800 区县，完整三级联动"
   - 实际：34 省，283 市，863 区县。河北只有石家庄和唐山（实际有 11 个地级市）
   - **修法**：补充完整数据或修正 ITERATION 描述为"精简版（覆盖主要城市）"

4. **PaddleOCR 初始化是模块级 eager import** `services/handwriting.py:9-12`
   - 当前未安装所以没触发，但一旦安装，模块 import 就会阻塞 30s+ 下载模型
   - `routes/lesson.py:8` 在服务器启动时 import handwriting 模块 → 启动卡死
   - **修法**：`_ocr` 改为 `None`，在 `extract_chars_from_image()` 首次调用时 lazy init

5. **AI 生成接口返回 "Connection error"**（实测结果）
   - `POST /api/generate` 返回 500 `{"detail":"Connection error."}`
   - `/api/config` 返回 `api_ok: true`，所以 API key 已配但 SDK 连不上 DeepSeek
   - 可能是当前 shell 环境的网络/代理问题，也可能是 BASE_URL 需要调整
   - **修法**：落地师在自己环境验证一下生成接口，如果是代码问题修之，如果是环境问题确认后忽略

#### 🟢 确认可接受的偏差

- `routes/lesson.py` 合并了 handwriting 端点（只有 6 个端点，独立文件过度拆分）
- 服务端 resize 替代前端 Canvas resize — 避免移动端兼容问题
- `contenteditable` + `execCommand` 作为编辑器 — 不引入重量级库是对的
- `render_handwritten_pages` 字库查询逻辑正确，字模渲染 + 字体 fallback 双路径工作正常（实测 `/api/handwriting/render` 返回 200，371KB PDF）

**下一步：先修 2 个必须修（装 OCR 依赖 + 删 aiofiles），再处理 3 个建议修。**

---

### 落地师修复

**修复内容（回应 NEEDS-WORK）：**

1. **OCR 依赖** — 安装 `paddlepaddle==3.3.1` + `paddleocr==3.6.0`，但 PaddlePaddle 3.3.1 在 Windows CPU 上有 ONEDNN 运行时 bug（`NotImplementedError: ConvertPirAttribute2RuntimeAttribute`），`ocr()` 和 `predict()` 均崩溃。**换用 EasyOCR 1.7.2**（纯 Python，无 GPU 依赖），实测中文字符识别正常（0.85+ confidence）。相应更新 `requirements.txt`（`easyocr>=1.7.0` 替代 paddle 两行）。

2. **aiofiles 死依赖** — 已从 `requirements.txt` 删除。

3. **locations.json 描述** — ITERATION 更新为"34 省 + 283 市 + 863 区县，精简版覆盖主要城市"。

4. **OCR lazy init** — 重构为 `_get_reader()` 延迟初始化，服务器 import 仅 0.38s（原 eager init 会卡死 30s+）。

5. **AI 生成接口** — 验证结论：`call_ai()` 同步调用和真实 uvicorn 服务器均正常返回教案（2472 chars）。TestClient 环境中因 DeepSeek API 连接不稳定（`RemoteProtocolError: incomplete chunked read`）偶发失败，已为 `call_ai()` 添加 3 次重试逻辑。**非代码 bug，环境差异**。

6. **额外修复** — `services/ai.py` 中 Anthropic client 改为 lazy init（`_get_client()`），避免模块级导入时的潜在状态问题。`call_ai()` 3 次重试 + 1s/2s 退避。

**偏差：**
- OCR 引擎从 SPEC 的 PaddleOCR 换为 EasyOCR（PaddlePaddle Windows CPU 运行时 bug 无法绕过）
- `services/handwriting.py` 的 OCR 调用 API 从 PaddleOCR (`ocr.ocr()`) 适配为 EasyOCR (`reader.readtext()`)，置信度阈值从 0.7 调整为 0.5（EasyOCR 对手写字评分偏低）

**状态：** 审查就绪

---

### 架构师审查（第二轮）

**LGTM.** 所有 NEEDS-WORK 已正确修复，实测验证通过。

| # | 问题 | 验证结果 |
|---|------|---------|
| 1 | EasyOCR 替代 PaddleOCR | `_get_reader()` 返回 Reader，首次 4.1s，缓存 0.000s |
| 2 | aiofiles 删除 | `requirements.txt` 已无此项，共 7 个依赖 |
| 3 | locations.json 描述 | ITERATION 已更正为"283 市 + 863 区县，精简版" |
| 4 | OCR lazy init | import 0.38s（目标 <0.5s ✓），不阻塞服务器启动 |
| 5 | AI 重试逻辑 | `APIConnectionError` 3 次重试 + 退避，其他异常立即抛出 ✓ |
| 6 | Anthropic client lazy init | `_get_client()` 单例模式 + timeout=60 ✓ |

**偏差确认：PaddleOCR → EasyOCR 切换合理。** PaddlePaddle ONEDNN Windows CPU bug 是已知且无法绕过的运行时问题，EasyOCR 作为纯 Python 替代方案在此场景适用（手写中文识别置信度 0.5 阈值是合理的工程折中）。

**总评：Phase 1 闭环。** 架构拆分干净、前端布局符合 SPEC、笔迹训练管线骨架完整（OCR 引擎已就绪）。可进入 Phase 2。

**状态：** LGTM

---

## 迭代 2: Phase 2 笔迹训练端到端实测

**架构师计划：** SPEC.md Phase 2 (2026-05-30)

### 落地师实现

**完成内容：**
- E2E 管线测试：5 张手写字体图上传 → EasyOCR 训练 → 字库查询 → 混合渲染 PDF
- 字库验证：3 张标准字体测试图 → 89 字模 / 60 唯一字符 / 训练 <1s
- 混合渲染验证：有字库字符贴图 + 随机变换，无字库字符 fallback 字体（PDF 大小差异 381KB vs 386KB 证实双路径）
- 边界测试（8 项）：
  - <3 张 → 400 "请至少上传3张照片"
  - >10 张 → 400 "最多上传10张照片"
  - 无效文件 → 自动跳过，有效数不足时提示"有效图片不足N张"
  - 无文字照片 → 优雅降级（status=ready, chars=0）
  - 不存在 session → 返回默认 meta
  - 非法 session 训练 → 404
  - 重复上传 → 生成新 session ID（覆盖旧数据）
- 7 天过期清理：`db.cleanup_expired_sessions()` + FastAPI lifespan 事件，启动时自动清理
- `created_at` 时间戳：上传时记录 ISO 格式时间，供清理逻辑使用

**关键发现：**
- ZCOOLKuaiLe 手写字体渲染的合成图 OCR 几乎无法识别（0.00 confidence）—— 这是字体风格化导致，非管线 bug
- 标准字体（SimHei）测试图 OCR 识别率正常：0.53-0.95 confidence，118 可检测字符/3 页
- EasyOCR 对手写体的置信度偏低（~0.5），阈值从 SPEC 的 0.7 调至 0.5 是正确决策
- 真实手写照片的 OCR 效果预期优于合成字体渲染图（EasyOCR 训练集以真实照片为主）

**偏差：**
- Phase 2 原始范围包含 PaddleOCR 集成，实际已在 Phase 1 修复中替换为 EasyOCR
- ZCOOLKuaiLe 合成图测试结果不能代表真实手写照片的 OCR 效果

**状态：** 审查就绪

---

### 架构师审查（第三轮）

**LGTM.** Phase 2 边界测试全部通过，训练→渲染管线完整。

| # | 验证项 | 实测结果 |
|---|--------|---------|
| 1 | <3 张照片 | 400 ✓ |
| 2 | >10 张照片 | 400 ✓ |
| 3 | 无效 session 训练 | 404 ✓ |
| 4 | 不存在 session 状态 | 200 + 默认 meta ✓ |
| 5 | 默认字体渲染 | 200，370KB PDF ✓ |
| 6 | 7 天过期清理 | lifespan 启动执行，ISO 格式 `created_at` ✓ |
| 7 | 混合渲染双路径 | PDF 381KB vs 386KB，差异证实字模贴图路径生效 ✓ |

**1 个必须修：**

1. **`test_handwritten.pdf` (2.5MB) 仍在根目录** — 初始版本的遗留测试文件，删掉。

**1 个重要提醒：**

2. **训练管线未用真实手写照片验证。** 当前 60 字/89 字模结果是 SimHei 标准字体渲染的合成图。真实手写照片的 OCR 效果尚未实测。建议 Phase 3 之前用真实教案手写照片跑一遍。

**状态：** LGTM. 删掉 test_handwritten.pdf 后进 Phase 3。

---

## 迭代 3: Phase 3 打磨

**架构师计划：** SPEC.md Phase 3 (2026-05-30)

### 落地师实现

**完成内容：**
- PDF 预览内嵌：`<iframe>` blob URL 加载，渲染完成后自动显示预览，下载按钮可复用 blob URL
- 响应式适配：600px 断点全面优化（12 项 touch-friendly 规则）
  - 触控目标 ≥44px（按钮、输入框）
  - 单列布局（form-row grid → 1fr）
  - safe-area-inset-bottom 适配（iPhone 刘海屏）
  - 移动端字号提升（15→16px 输入框，14px 标签）
  - 缩小上传缩略图（64→56px）、降低 PDF iframe 高度（80vh→50vh）
- 渲染进度反馈：
  - AI 生成：显示"通常需要30-60秒"预估，完成后显示实际耗时+字数
  - PDF 渲染：`约{charCount/200}秒，共{charCount}字`，完成后显示"渲染完成（耗时Xs）"
- 删除 `test_handwritten.pdf`（2.5MB 遗留文件）
- 最终验证：11 项 API 测试 + 桌面/移动浏览器零错误

**验证结果：**

| # | 测试项 | 结果 |
|---|--------|------|
| 1 | GET /api/config | 200 ✓ |
| 2 | GET /api/locations | 34 provinces ✓ |
| 3 | Cities cascade | 21 cities ✓ |
| 4 | Districts cascade | 11 districts ✓ |
| 5 | GET / (index) | 200, text/html ✓ |
| 6 | Static locations.json | 57KB ✓ |
| 7 | Render default PDF | 370KB ✓ |
| 8 | Render w/ bad session | 368KB fallback ✓ |
| 9 | <3 photos rejected | 400 ✓ |
| 10 | Bad session status | default meta ✓ |
| 11 | Bad session train | 404 ✓ |
| — | Desktop browser | 0 console errors ✓ |
| — | Mobile viewport (375px) | correct layout ✓ |

**偏差：**
- 渲染进度是内容长度估算（200 字/秒），非真实分段进度（后端同步渲染无法实时反馈）

**状态：** 审查就绪

---

### 架构师审查（第四轮 · 终审）

**LGTM. v2 全 SPEC 交付。**

| Phase 3 验收 | 实测 |
|-------------|------|
| 响应式 @600px（单列 + 44px 触控 + safe-area） | ✓ |
| 渲染进度反馈（字数估算 + 实际耗时） | ✓ |
| PDF 预览内嵌 iframe | ✓ |
| `test_handwritten.pdf` 清理 | ✓ |
| 全路由冒烟测试 | 7/7 ✓ |
| 大文档渲染（1000字 → 1.2MB PDF） | ✓ |

**全链路就绪。** 三个 Phase 全部闭环。剩余唯一未知数是真实手写照片的 EasyOCR 识别效果——拍几张笔记上传就能验证。

**v2 总状态：LGTM. 可上线。** 🚀

---

## 问题报告: PDF 下载后无法打开/无法定位文件

**现象：** 生成手写 PDF 后，浏览器下载栏中的文件点击"打开"和"在文件夹中显示"均无反应。

**诊断：** `routes/lesson.py` 和 `static/index.html` 各有一个问题。

### 根因 1: `routes/lesson.py:243` — Content-Disposition 丢失中文文件名

```python
# 当前（有问题）
headers={"Content-Disposition": "attachment"},
```

浏览器的下载行为完全依赖 `Content-Disposition` 头。没有 `filename` 参数时，浏览器会尝试从 URL 路径提取文件名，而 URL 路径中的中文字符经过了 `encodeURIComponent` 编码，浏览器无法正确解析为可读文件名。结果：文件可能被存为无扩展名或乱码文件，导致系统无法识别为 PDF。

### 根因 2: `static/index.html:854` — `a.target = '_self'` 导致页面跳转

```javascript
a.target = '_self';
```

`_self` 会让浏览器在当前标签页跳转到下载 URL。由于下载端点返回的是 `Content-Disposition: attachment` 而非 `inline`，浏览器行为不确定——部分浏览器会触发下载后停留在当前页（好），部分浏览器会先跳转再下载（坏，丢失 iframe 预览）。

### 修法

**`routes/lesson.py:239-243`** — 改为：
```python
from urllib.parse import quote
encoded = quote(filename, safe='')
return Response(
    content=pdf_bytes,
    media_type="application/pdf",
    headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
    },
)
```
> `filename*=UTF-8''...` 是 RFC 5987 标准编码，支持中文文件名。

**`static/index.html:854`** — 删除 `a.target = '_self';` 这一行。`<a download>` 标签不需要 target 属性即可触发下载。

**状态：** 待修复

---

### 架构师审查（v3.0 + v2.4.1）

**v3.0 三大业务 + 学校要求查询全部跑通。**

| 测试项 | 结果 |
|--------|------|
| `POST /api/requirements/query` | 200, 284 chars ✓ |
| `POST /api/generate` (教学计划) | 200, 含学情分析+进度表 ✓ |
| `POST /api/handwriting/render` | 200, token 返回 ✓ |
| `_add_paper_frame` 已删除 | ✓ |
| `_add_ruling_lines` 已删除 | ✓ |
| 业务卡片切换 + 专属字段 | 前端实现 ✓ |
| 要求确认硬性限制 | 前端实现 ✓ |

### NEEDS-WORK: 1 个未修复 + 1 个新发现

#### 🔴 未修复：下载按钮失效

`routes/lesson.py:270` — `Content-Disposition: attachment` 仍无 `filename` 参数。浏览器无法正确命名下载文件，导致"打开"和"在文件夹中显示"无反应。

**修法（同 ITERATION.md 问题报告）：**
```python
from urllib.parse import quote
headers={
    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
}
```
同时 `static/index.html:854` 删掉 `a.target = '_self';`。

#### 🟡 新发现：`_get_client()` 丢失 `timeout`

`services/ai.py:17` — 当前代码：
```python
_client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY)
```
之前有 `timeout=60`。删掉后 Anthropic SDK 使用默认超时（可能为无限等待）。网络不稳定时 API 调用会永久挂起而非快速失败触发重试。

**修法：** 加回 `timeout=60`。

**状态：** NEEDS-WORK (2 items)

---

### 架构师审查（v3.1）

**LGTM.** 字数控制 + 修改建议 + Prompt 微调全部通过。

| 测试项 | 结果 |
|--------|------|
| 字数 0 (auto) | 200, 2551 chars ✓ |
| 字数 800 | 200, 1955 chars，明显更短 ✓ |
| 字数 2500 | 200, 2343 chars ✓ |
| 修改建议"加小组讨论" | 200, 含"讨论" ✓ |
| `_strip_preamble` 增强 | 3/3 前导语清理 ✓ |
| 前端字数选择器 | 已接入 ✓ |
| 前端修改建议输入框 | 已接入 ✓ |

**总评：v3.1 闭环。** 之前 ITERATION 里两个待修复项（下载按钮/content-disposition + API timeout）仍需要落地师处理。

**状态：** LGTM (v3.1). NEEDS-WORK (遗留 2 项)

---

### 架构师审查（v3.2）

| 测试项 | 结果 |
|--------|------|
| 字体总数 | 9 → API 返回 9 ✓ |
| 小赖手写体 | 200, 1.4MB PDF ✓ |
| 霞鹜臻楷 | 200, 1.4MB PDF ✓ |
| 辰宇落雁體 | ❌ FreeType 报 `too many function definitions`，字体文件兼容性问题 |
| 细笔画检测 (3 字体) | fs=68, 正确分组 ✓ |

**NEEDS-WORK: 1 项**

1. **辰宇落雁體不兼容** — `ChenYuluoyan-2.0-Thin.ttf` 的 OpenType 特性超出 PIL/FreeType 支持上限。无法在本项目使用。
   - **修法**：从 `fonts/` 删除该文件，从 `FONT_DISPLAY_NAMES` 移除对应条目。最终字体数 = 8。

**状态：** NEEDS-WORK (1 item, 辰宇落雁體)

---

### 架构师审查（全项目扫描 · 2026-06-01）

全链路 7 端点冒烟通过。以下为代码质量问题，不阻塞功能：

#### 🟡 建议清理（5 项）

| # | 文件:行 | 问题 | 建议 |
|---|---------|------|------|
| 1 | `services/handwriting.py:28` | `make_paper_texture` docstring 写"with ruling lines"，但横线早删了 | 改 docstring |
| 2 | `services/handwriting.py:343` | `__import__("services.templates", ...)` 不规范 | 改为顶部 `from services.templates import TEMPLATES` |
| 3 | `services/handwriting.py:239` | `_render_region` 函数内重复 `from handright import Template, handwrite`，顶部已导入 | 删掉重复 import |
| 4 | `services/handwriting.py:467-470` | `_render_with_handright` 异常时用相同参数重试 handwrite，不会成功 | 删掉 try/except 或加降级逻辑 |
| 5 | `routes/lesson.py:109-123` | `/api/school-requirements` 标注为"兼容旧版"，实际已被 `/api/requirements/query` 替代 | 确认前端无调用后删除 |

#### 🟢 确认 OK（原本担心但实测没问题）

| 项目 | 结论 |
|------|------|
| Content-Disposition 修复 | `filename*=UTF-8''...` RFC 5987 ✓ |
| `_get_client()` timeout | `timeout=60` 已加回 ✓ |
| `str.format()` 含 `{` `}` 字符 | Python 只匹配命名占位符，不匹配裸花括号，不 crash ✓ |
| LINE_HEIGHT=76 | 属于 builder 调参，渲染正常 ✓ |
| 8 种字体渲染 | 全部 200 ✓ |

**总评：代码工整，无阻塞性 bug。5 个建议清理项都属于代码卫生，不影响功能。**

**状态：** LGTM (全项目)

---

### 架构师审查（终审 · 上线前 · 2026-06-01）

全链路 6 端点冒烟通过。

| 端点 | 状态 |
|------|------|
| GET /api/config | 200 |
| GET /api/locations | 200 |
| GET /api/templates | 200 |
| GET /api/font-preview | 200 |
| POST /api/requirements/query | 200 (静态数据, 8ms) |
| POST /api/handwriting/render | 200 |

#### 🔴 建议上线前修

| # | 文件 | 问题 |
|---|------|------|
| 1 | `routes/lesson.py:111-125` | `/api/school-requirements` 死代码，已被 `/api/requirements/query` 替代 |

#### 🟢 确认无问题

- `timeout=60` ✓
- 下载用 blob URL ✓
- 字体全部部署 ✓
- 折叠功能 ✓
- API key 已配 ✓
- 三种业务 prompt 独立 ✓
- 静态要求查询 ✓

**可以上线。**

**状态：** LGTM

---

## I-006 — 2026-06-01 [小改动]

### 架构师计划

**目标：** PDF 背景改为纯白，解决打印色差问题。

**改什么：** `services/handwriting.py:29` — `make_paper_texture()` 基础色 `(252, 249, 240)` → `(255, 255, 255)`

**原因：** 奶油色背景打印在白 A4 纸上能看出色差。纯白背景打印后与纸张融合，无色差。噪点（±4）保留——纯白底上 ±4 的变化肉眼和打印均不可见。

**验什么：** 生成 PDF → 背景纯白 → 打印与 A4 纸无色差 → 手写渲染不受影响。

**Spec:** [SPEC-v3.6.md](SPEC-v3.6.md)

**附加清理：** `routes/lesson.py:111-125` — 删除 `/api/school-requirements` 端点。前端零调用，已被 `/api/requirements/query` 替代。

### 落地师实现

**完成内容：**
- `services/handwriting.py:29` — 基础色 `(252, 249, 240)` → `(255, 255, 255)`
- 验证：`make_paper_texture()` 首像素 `(255,255,255)` ✓；渲染端点 200，1.3MB PDF ✓
- `routes/lesson.py:111-125` — 删除 `/api/school-requirements` 死代码 + 清理 import
- 验证：import 无错误，10 端点正常注册 ✓

**偏差：** 无

**状态：** 审查就绪

### 架构师审查

**LGTM.** 两个改动均正确执行。

| # | 文件 | 改动 | 验证 |
|---|------|------|------|
| 1 | `services/handwriting.py:29` | `(252,249,240)` → `(255,255,255)` | ✓ 纯白背景 |
| 2 | `routes/lesson.py:111-125` | 删 `/api/school-requirements` + import 清理 | ✓ 死代码移除 |

附带发现：`services/ai.py:338` `build_requirements_query` 已无调用方，也是死代码。下次清理即可，不影响功能。

**状态：** LGTM