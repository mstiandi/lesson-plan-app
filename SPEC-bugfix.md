# SPEC: 遗留 Bug 修复

## Bug 1: 下载按钮无效

### 根因
`routes/lesson.py:270` — `Content-Disposition: attachment` 无 `filename` 参数。浏览器拿到响应后无法确定文件名，中文 URL 路径经过 `encodeURIComponent` 后浏览器解析失败，导致"打开""在文件夹中显示"均无反应。

### 修法

**`routes/lesson.py:267-271`** 改为：

```python
from urllib.parse import quote
return Response(
    content=pdf_bytes,
    media_type="application/pdf",
    headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
    },
)
```

**`static/index.html`** — 删除 `a.target = '_self';`（第 854 行附近）。

> `filename*=UTF-8''...` 是 RFC 5987 标准，支持中文文件名。浏览器自动识别并正确命名下载文件。

---

## Bug 2: API 调用可能永久挂起

### 根因
`services/ai.py:17` — `_get_client()` 丢失 `timeout=60`：

```python
# 当前
_client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY)

# 应为
_client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY, timeout=60)
```

无超时 = 网络波动时请求永久挂起，永远不触发重试逻辑。

### 修法
加回 `timeout=60`。

---

## 文件改动

| 文件 | 行 | 改动 |
|------|-----|------|
| `routes/lesson.py` | 267-271 | Content-Disposition 加 RFC 5987 filename |
| `static/index.html` | ~854 | 删除 `a.target = '_self';` |
| `services/ai.py` | 17 | 加回 `timeout=60` |

## 验收

- [ ] 生成 PDF 后点击"下载此PDF"，浏览器下载栏显示正确中文文件名
- [ ] 下载的文件可在本地正常打开
- [ ] API 调用在网络不稳定时 60 秒超时而非永久挂起
