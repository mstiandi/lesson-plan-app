# SPEC: 教案草稿生成器 v2

## 目标

将当前的"填表→AI生成→手写PDF"单页工具，升级为**学校定位→AI定制化→电子教案编辑→笔迹训练→手写PDF**的完整教案工作流。

---

## 1. 前端重构

### 1.1 四段式纵向布局

```
┌─ SECTION 1: 学校信息 ──────────────────────┐
│  省/直辖市  [dropdown]   市/区  [cascading]  │
│  县/镇      [dropdown]   学校  [text input]  │
└────────────────────────────────────────────┘

┌─ SECTION 2: 教学信息 ──────────────────────┐
│  学科  [dropdown]   教材版本  [dropdown]     │
│  年级  [dropdown]   课时数    [dropdown]     │
└────────────────────────────────────────────┘

┌─ SECTION 3: 课程信息 + 生成电子教案 ────────┐
│  课题名称  [text input]                     │
│  [🤖 生成电子教案]                           │
│  ┌──────────────────────────────────────┐   │
│  │ 富文本编辑区 (contenteditable)        │   │
│  │ - Markdown 渲染为格式化文本           │   │
│  │ - 可直接编辑修改                      │   │
│  │ - 工具栏: 加粗/斜体/标题/列表         │   │
│  └──────────────────────────────────────┘   │
│  [复制内容]  [打印]                          │
└────────────────────────────────────────────┘

┌─ SECTION 4: 手写版PDF ─────────────────────┐
│  ○ 使用默认手写字体 (即刻可用)               │
│  ○ 训练我的笔迹 (上传教案照片 → 提取字模)    │
│     ┌──────────────────────────────────┐    │
│     │ [拖拽上传区] 上传3-10张教案照片    │    │
│     │ 已上传: □□■□□  (进度指示)         │    │
│     │ 状态: 训练中... / 字库就绪 (N字)   │    │
│     └──────────────────────────────────┘    │
│  [🖨️ 下载手写版PDF]                          │
│  ┌─ PDF 预览 (iframe) ──────────────────┐   │
│  └──────────────────────────────────────┘   │
└────────────────────────────────────────────┘
```

### 1.2 技术方案

- **保持单 HTML 文件**（`static/index.html`），嵌入式 CSS + vanilla JS
- 富文本编辑：轻量级 `contenteditable` + `document.execCommand` 工具栏，或引入 Tiptap (60KB gzip) 如果需要更好体验
- 行政区划数据：静态 JSON 文件 `static/locations.json`（省→市→区县三级联动），约 200KB
- 文件上传：`<input type="file" multiple accept="image/*">` + 拖拽区域

### 1.3 交互状态

| 状态 | 触发 | UI 表现 |
|------|------|---------|
| 空闲 | 页面加载 | 表单可填写，手写区折叠 |
| 生成中 | 点击生成 | 按钮禁用 + spinner，编辑区骨架屏 |
| 生成完成 | API 返回 | 编辑区填充，手写区展开 |
| 上传中 | 选择照片 | 上传区显示缩略图 + 进度 |
| 训练中 | 上传完成 | 进度条，"正在分析笔迹…" |
| 字库就绪 | 训练完成 | 显示字模数量，下载按钮可用 |
| 渲染中 | 点击下载 | "正在排版…" |
| 错误 | 任何失败 | 红色提示条，可重试 |

---

## 2. 后端重构

### 2.1 文件结构

```
D:\lesson-plan-app\
├── main.py                  # FastAPI app 创建, 挂载 static, startup
├── config.py                # 环境变量读取, 常量定义
├── models.py                # Pydantic 请求/响应模型
├── db.py                    # SQLite 连接, 建表, 基础查询
├── routes/
│   ├── __init__.py
│   ├── lesson.py            # 教案生成 API
│   └── handwriting.py       # 上传, 训练, PDF 渲染 API
├── services/
│   ├── __init__.py
│   ├── ai.py                # AI 调用封装 (DeepSeek/Anthropic)
│   ├── handwriting.py       # 笔迹提取 + 渲染引擎
│   └── location.py          # 行政区划数据 + 学校教案要求匹配
├── static/
│   ├── index.html           # 前端主文件
│   └── locations.json       # 省市区数据
├── uploads/                 # 用户上传的手写照片 (gitignore)
├── handwriting_banks/       # 用户字模库 (gitignore)
│   └── {session_id}/
│       ├── chars.db         # SQLite: char → 图片路径映射
│       └── images/          # 单个字模 PNG 文件
├── fonts/
│   └── ZCOOLKuaiLe.ttf      # 默认手写字体
├── requirements.txt
├── README.md
├── CLAUDE.md
└── SPEC.md
```

### 2.2 API 端点

| Method | Path | 描述 | Request | Response |
|--------|------|------|---------|----------|
| `GET` | `/api/config` | 服务状态 | — | `{model, api_ok, default_font}` |
| `POST` | `/api/generate` | 生成教案文本 | `SchoolInfo + TeachingInfo + CourseInfo` | `{content: "markdown"}` |
| `POST` | `/api/handwriting/upload` | 上传手写照片 | `multipart/form-data` (3-10 images) | `{session_id, image_count}` |
| `POST` | `/api/handwriting/train` | 启动笔迹训练 | `{session_id}` | `{status, char_count}` |
| `GET` | `/api/handwriting/status/{session_id}` | 查询训练状态 | — | `{status, char_count, total_chars}` |
| `POST` | `/api/handwriting/render` | 渲染手写PDF | `{content, session_id?, use_default?}` | PDF binary |
| `GET` | `/api/locations` | 获取行政区划 | `?parent=code` | `[{code, name, level}]` |

### 2.3 Pydantic 模型

```python
class SchoolInfo(BaseModel):
    province: str      # "广东省"
    city: str          # "广州市"
    district: str      # "天河区" (optional)
    school_name: str   # "天河中学"

class TeachingInfo(BaseModel):
    subject: str       # "语文"
    grade: str         # "七年级"
    textbook: str      # "部编版"
    hours: int = 1     # 课时数

class GenerateRequest(BaseModel):
    school: SchoolInfo
    teaching: TeachingInfo
    topic: str         # 课题名称

class TrainRequest(BaseModel):
    session_id: str    # UUID from upload step

class RenderRequest(BaseModel):
    content: str
    session_id: str | None = None  # 使用训练好的笔迹
    use_default: bool = True       # 兜底
```

---

## 3. 数据模型

### 3.1 SQLite 笔迹字库 (`handwriting_banks/{session_id}/chars.db`)

```sql
CREATE TABLE chars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unicode TEXT NOT NULL,           -- 单个汉字 "我"
    image_path TEXT NOT NULL,        -- "images/000123.png"
    source_photo TEXT NOT NULL,      -- 来自哪张上传照片
    bbox_x INTEGER,
    bbox_y INTEGER,
    bbox_w INTEGER,
    bbox_h INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_chars_unicode ON chars(unicode);
```

### 3.2 Session 元数据（服务端内存 + 可选文件持久化）

```python
# 用 JSON 文件存储在 handwriting_banks/{session_id}/meta.json
{
    "session_id": "uuid",
    "status": "training",        # uploading | training | ready | error
    "char_count": 1523,
    "total_samples": 3200,
    "created_at": "2026-05-30T...",
    "photo_count": 5
}
```

---

## 4. 笔迹训练管线

### 4.1 上传阶段

```
用户选择 3-10 张手写教案照片
    → 前端 resize 到 1200px 宽 (浏览器端, 减少上传体积)
    → POST /api/handwriting/upload
    → 服务端保存到 uploads/{session_id}/
    → 返回 session_id
```

### 4.2 训练阶段

```
POST /api/handwriting/train { session_id }
    → 异步启动训练 (BackgroundTasks)
    → 对每张照片:
        1. 预处理: 灰度化 → 自适应阈值二值化 → 去噪
        2. PaddleOCR 识别: 获取每个字符的 bbox + 文本 + 置信度
        3. 过滤: 置信度 < 0.7 丢弃
        4. 裁剪: 从原图按 bbox 裁剪字符区域
        5. 标准化: resize 到 64×64, 保持长宽比, 填充白边
        6. 存储: PNG → handwriting_banks/{session_id}/images/
        7. 写入 chars 表
    → 更新 meta.json status = "ready"
```

### 4.3 渲染阶段

```
POST /api/handwriting/render { content, session_id, use_default }
    → 获取 content 纯文本 (strip markdown)
    → 对每个字符 char:
        if session_id 且 chars 表中有该字符:
            → 随机取一个 variant 图片
            → 随机变换: rotation ±1.5°, scale ±3%, offset ±2px
            → 贴到 A4 画布上
        else:
            → 用 ZCOOLKuaiLe 字体渲染 (现有逻辑)
    → 拼成多页 PIL Image
    → fpdf 转 PDF
    → 返回 PDF bytes
```

### 4.4 边界情况处理

| 情况 | 处理 |
|------|------|
| 上传<3张照片 | 拒绝，"请至少上传3张照片" |
| 照片中无法识别文字 | 跳过该照片，警告用户 |
| 某字符在照片中出现多次 | 存储多个 variant，渲染时随机选 |
| 目标字符不在字库中 | 回退到默认手写字体 |
| 训练中用户再次上传 | 覆盖旧 session，重新开始 |
| Session 过期 (7天) | 定时清理 handwriting_banks/ 中过期数据 |

---

## 5. AI 定制化：学校定位 → 教案生成

### 5.1 增强 System Prompt

在原有 prompt 基础上，注入学校上下文：

```
教师所在地区：{province} {city} {district}
学校名称：{school_name}
使用教材：{textbook}（{grade} {subject}）

在生成教案时请注意：
1. 教学目标须参照{province}现行课程标准
2. 教学难度须匹配当地教学水平（市级重点/普通/农村学校）
3. 如当地有中考命题特点，可在巩固练习中有所体现
4. 教学准备中考虑学校的实际条件
```

### 5.2 地区教案要求匹配（可选增强）

`services/location.py` 维护一份各省市教学要求摘要库（JSON），AI 生成前查询匹配：
- 例如：江苏省 → 苏教版配套要求 → 强调苏教版单元整体教学
- 例如：北京市 → 中考改革方向 → 重视核心素养评价

MVP 阶段用静态 JSON 即可，后续可接入搜索引擎实时检索。

---

## 6. 实现阶段

### Phase 1: 基础重构（1-2天）
- [ ] 后端拆分为 routes/services/models
- [ ] 前端四段式布局
- [ ] 行政区划三级联动
- [ ] AI prompt 注入学校信息
- [ ] 电子教案编辑区 (contenteditable)
- [ ] README.md + CLAUDE.md

### Phase 2: 笔迹训练（2-3天）
- [ ] PaddleOCR 集成
- [ ] 上传 + 训练 + 状态查询 API
- [ ] 前端上传区 + 训练状态 UI
- [ ] 字库存储 (SQLite + 文件)
- [ ] 字库渲染引擎（替代纯字体渲染）
- [ ] 默认字体 fallback

### Phase 3: 打磨（1天）
- [ ] PDF 预览内嵌
- [ ] 错误处理 + 边界情况
- [ ] 响应式适配（移动端教师场景）
- [ ] 性能：大文档渲染进度反馈

---

## 7. 技术选型

| 层 | 选型 | 原因 |
|----|------|------|
| 后端框架 | FastAPI (已有) | 异步支持, BackgroundTasks 适合训练任务 |
| AI SDK | anthropic + DeepSeek (已有) | 成本低, 中文能力强 |
| OCR | PaddleOCR (新增) | 中文手写识别 SOTA, 离线可用 |
| 图像处理 | PIL/Pillow (已有) | 字符提取 + 渲染 |
| PDF | fpdf2 (已有) | 轻量, 够用 |
| 数据库 | SQLite (新增) | 零配置, 单机够用 |
| 前端 | Vanilla HTML/CSS/JS (已有) | 无构建工具, 部署简单 |
| 行政区划数据 | 静态 JSON | 无外部依赖, 离线可用 |

### 依赖清单 (`requirements.txt`)

```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
anthropic>=0.30.0
Pillow>=10.0.0
fpdf2>=2.7.0
paddlepaddle>=3.0.0
paddleocr>=2.7.0
python-multipart>=0.0.6
aiofiles>=23.0.0
```

---

## 8. 验收标准

### 8.1 电子教案生成
- [ ] 填写完整学校+教学+课程信息后，点击生成，30s 内返回结构化教案
- [ ] 教案内容在编辑区可修改（光标定位、输入、删除、回车）
- [ ] 复制按钮可复制纯文本，打印按钮可调起浏览器打印
- [ ] 不同地区 + 不同教材组合产出不同风格的教案（非千篇一律）

### 8.2 笔迹训练
- [ ] 上传 3 张以上手写照片后，训练在 60s 内完成
- [ ] 训练完成后字库至少覆盖常见汉字 500+
- [ ] 生成的手写 PDF 中，有字库的字符用用户笔迹，无字库的用默认字体

### 8.3 手写 PDF
- [ ] 默认字体模式下，生成 A4 排版 PDF，带横格线，纸张纹理
- [ ] 自定义笔迹模式下，写出的字"看起来像用户写的"
- [ ] PDF 可直接打印，效果清晰
