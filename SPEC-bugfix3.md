# SPEC: 手机 PDF 预览修复

## 问题
手机浏览器不支持 blob URL 在 iframe 中加载 PDF → 空白。

## 修法
用 `<embed>` 替代 `<iframe>`，并加一个"在新窗口打开"后备按钮。

## `static/index.html` 改动

### 1. HTML: iframe → embed

```html
<embed id="pdfEmbed" type="application/pdf" style="width:100%;height:80vh;border:1px solid #ddd;border-radius:8px;">
<iframe id="pdfFrame" style="display:none;"></iframe>
```

### 2. JS: 渲染成功后同时设 embed

```js
// renderAndDownload 中：
const url = URL.createObjectURL(blob);
document.getElementById('pdfEmbed').src = url;
document.getElementById('pdfPreview').classList.remove('hidden');
```

### 3. JS: downloadPDF 用 blob（已修复，不变）

## 验收
- [ ] 手机 PDF 预览可见
- [ ] 电脑 PDF 预览正常
- [ ] 下载按钮正常
