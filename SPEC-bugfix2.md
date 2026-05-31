# SPEC: PDF 预览 + 下载修复（Vercel 无状态兼容）

## 问题
Vercel 函数是无状态的，渲染请求和下载请求可能打到不同实例，`_render_cache` 内存缓存在另一实例中为空 → "PDF 已过期或不存在"。

## 修法
前端渲染时已经拿到了 blob（`window._pdfBlob`），直接用 blob URL 下载，不走服务端缓存。

## 改动

### `static/index.html` — `downloadPDF()` 函数

**替换为：**

```js
function downloadPDF() {
  if (!window._pdfBlob) return;
  var topic = document.getElementById('topic').value.trim() || '教案';
  var ts = new Date().toISOString().slice(0,16).replace('T','-').replace(':','');
  var filename = '教案-' + topic + '-手写版-' + ts + '.pdf';
  var url = URL.createObjectURL(window._pdfBlob);
  var a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function() { URL.revokeObjectURL(url); }, 60000);
}
```

### `routes/lesson.py` — 可删除渲染缓存相关代码（非必须）

`_render_cache`、`_cache_put`、`_cache_cleanup`、`/handwriting/download/...` 端点可以删除或保留备用。

## 验收
- [ ] 手机和电脑 PDF 预览正常显示
- [ ] 点击下载直接保存 PDF，不报过期
