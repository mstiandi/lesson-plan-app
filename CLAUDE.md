# CLAUDE.md — 教案草稿生成器

## ⛔ 架构师/落地师协议（最高优先级，不可被其他规则覆盖）

本项目有两类 agent：

| 角色 | 工具 | 规则 |
|------|------|------|
| **架构师** (dev-architect) | Read / Grep / Glob / WebSearch / WebFetch | 读代码、搜索、写 SPEC.md / README.md / CLAUDE.md / ITERATION.md |
| **落地师** (dev-builder) | 全部 | 写所有源文件（.py .html .json .css .js .txt）|

**架构师硬边界：**
```
🚫 禁止 Edit 任何源文件（.py .html .json .css .js .txt）
🚫 禁止 Write 任何源文件
🚫 禁止 Bash 执行代码修改（sed, rm, git commit 等写操作）
✅ 允许 Read / Grep / Glob / WebSearch / WebFetch
✅ 允许 Write SPEC.md / README.md / CLAUDE.md / ITERATION.md
✅ 允许 Bash 执行只读操作（ls, git status, python -c 测试等）
```

**落地师硬边界：**
```
✅ 允许 Edit / Write / Bash（全权限）
⚠️ 不做架构决策，改代码前先读 SPEC.md 和 ITERATION.md
```

**为什么这样设计：** 一人诊断一人执刀。架构师不改代码就不会因为"两行就能修好"的惯性越界。发现了 bug → 写进 ITERATION.md → 落地师修。中间有一道显式交接，避免架构师自己诊断自己修、跳过了审查步骤。

> ⚠️ 当你作为架构师进入此项目时，即使你知道 bug 怎么修、代码怎么改，也不允许动手。把你的发现写进 ITERATION.md，交给落地师。这不是能力问题，是流程设计。

## 技术栈
- Python 3.11+ / FastAPI / Uvicorn
- DeepSeek V4 via Anthropic SDK（兼容接口）
- EasyOCR（中文手写识别，纯 Python，替代 PaddleOCR）
- Pillow (图像处理) + fpdf2 (PDF)
- SQLite (笔迹字库)
- Vanilla HTML/CSS/JS（前端单文件，无框架）

## 文件结构

```
main.py              # App 创建、static mount、uvicorn 启动
config.py            # 只读环境变量：API_KEY, BASE_URL, MODEL
models.py            # 所有 Pydantic 请求/响应模型
db.py                # SQLite 连接池、建表、基础 CRUD
routes/              # API 路由层（薄层，只做参数校验+调用 service）
services/            # 业务逻辑层
  ai.py              #   AI 调用（system prompt 构建 + Anthropic SDK）
  handwriting.py     #   笔迹提取（PaddleOCR）+ 字库管理 + PDF 渲染
  location.py        #   行政区划数据加载 + 学校教案要求匹配
static/              # 前端文件（index.html + locations.json）
fonts/               # 默认手写字体 ZCOOLKuaiLe.ttf
handwriting_banks/   # 用户笔迹字库（运行时，gitignore）
uploads/             # 上传暂存（gitignore）
```

## 约定

- **路由薄层**：routes/ 只做参数提取+HTTP状态，所有逻辑在 services/
- **AI 调用走 executor**：`call_ai()` 是同步函数，通过 `run_in_executor` 在线程池中运行，避免阻塞 async loop
- **笔迹存储模型**：每个 session 一个目录 `handwriting_banks/{session_id}/`，内含 `chars.db`（SQLite）和 `images/`（PNG 文件）
- **前端无构建工具**：CSS/JS 全部内联在 `static/index.html`，不放任何 npm/webpack/vite 进来
- **环境变量 > 默认值**：API_KEY/BASE_URL/MODEL 从环境变量读取，有合理的默认值
- **端口固定 8877**：不与任何常见服务冲突
- **Markdown 处理**：AI 返回 markdown → `strip_markdown()` 去格式 → 纯文本渲染手写 PDF

## 已知坑点

1. **DeepSeek Base URL**：`https://api.deepseek.com/anthropic`，注意末尾是 `/anthropic` 不是 `/v1`
2. **EasyOCR 首次加载慢**：首次调用会下载模型（~100MB），已通过 lazy init 避免阻塞服务器启动
3. **手写字体编码**：ZCOOLKuaiLe.ttf 的字符集有限，生僻字可能显示异常
4. **Windows 路径**：所有路径用 `os.path.join()` 或 `/`，不要硬编码反斜杠
5. **PIL 字体大小**：`ImageFont.truetype()` 在某些 Windows 字体上会崩溃，必须 try/except
6. **线程池大小**：`ThreadPoolExecutor(max_workers=3)` —— 别改大，DeepSeek 有并发限制

## 领域知识

- **新课标（2022版）**：中国中小学现行课程标准，强调核心素养目标（语文：语言运用/思维能力/审美创造；数学：数感/运算能力/推理意识等）
- **教案结构**：课题 → 教学目标（核心素养+具体）→ 重难点 → 教学准备 → 教学过程（导入/新授/巩固/小结）→ 作业布置 → 板书设计 → 教学反思
- **教材版本**：人教版（最广）/ 苏教版 / 北师大版 / 部编版（语文统一）/ 冀教版 / 鲁教版
- **年级**：七年级到九年级（初中），高中可扩展
- **行政区划**：三级联动——省级（34个）→ 市级（~330）→ 区县级（~2800），静态 JSON 大约 200KB

## 手写训练管线速查

```
上传照片 → 预处理(灰度/二值化/去噪) → PaddleOCR(识别+bbox)
→ 过滤低置信度 → 裁剪字符区域 → 标准化 64×64
→ 存储 chars.db + images/ → status=ready
→ 渲染时: 查字库 → 有则贴图+随机变换 / 无则 fallback 字体
```
