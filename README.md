# 教案草稿生成器 v2

AI 驱动的教案生成工具——输入学校和课程信息，生成可编辑的电子教案，并渲染为手写风格 PDF 打印。

## 功能

- **学校定位定制** — 根据省市/学校自动调整教案的课标要求和难度
- **AI 教案生成** — 基于 DeepSeek V4，按新课标格式输出完整教案（目标/重难点/过程/作业/板书/反思）
- **电子教案编辑** — 生成后可直接在浏览器中修改内容
- **手写版 PDF** — 两种模式：
  - 默认手写字体 — 即刻使用，模拟手写效果
  - 训练我的笔迹 — 上传 3-10 张手写教案照片，提取字模，生成"看起来像你写的"PDF

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+, FastAPI, Uvicorn |
| AI | DeepSeek V4 (Anthropic SDK) |
| OCR | PaddleOCR |
| 图像 | Pillow |
| PDF | fpdf2 |
| 数据库 | SQLite |
| 前端 | Vanilla HTML/CSS/JS (无构建工具) |

## 安装

```bash
cd D:\lesson-plan-app
pip install -r requirements.txt
```

## 运行

```bash
# 设置 API Key
export ANTHROPIC_API_KEY=sk-your-deepseek-key
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic  # 可选，默认即此
export ANTHROPIC_MODEL=deepseek-v4-pro[1m]                    # 可选

# 启动 (默认 8877 端口)
uvicorn main:app --host 127.0.0.1 --port 8877 --reload
```

访问 `http://127.0.0.1:8877`

## 使用流程

1. 填写**学校信息**（省/市/区县/学校名）
2. 填写**教学信息**（学科/年级/教材版本/课时）
3. 输入**课题名称**，点击「生成电子教案」
4. 在编辑区审阅修改教案内容
5. 选择手写模式：
   - **默认字体** → 直接下载 PDF
   - **训练笔迹** → 上传 3-10 张手写教案照片 → 等待字模提取完成 → 下载 PDF

## 项目结构

```
main.py              # FastAPI 入口
config.py            # 环境配置
models.py            # Pydantic 模型
db.py                # SQLite 管理
routes/              # API 路由 (lesson, handwriting)
services/            # 业务逻辑 (ai, handwriting, location)
static/              # 前端静态文件
fonts/               # 默认手写字体
handwriting_banks/   # 用户笔迹字库 (运行时生成)
```
