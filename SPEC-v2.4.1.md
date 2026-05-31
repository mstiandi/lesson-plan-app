# SPEC: v2.4.1 去掉手写 PDF 矩形边框

## 目标

移除 v2.4 加入的稿纸外框，恢复纯白 A4 效果（仅有米黄纸纹理，无边线）。

## 改动

### `services/handwriting.py`

1. 删除 `_add_paper_frame` 函数（第43-52行）
2. 删除 `_render_with_handright` 中对 `_add_paper_frame` 的调用（第486行）
3. 删除 `_render_with_char_bank` 中对 `_add_paper_frame` 的调用（第530行）

三处删除，零新增。

## 验收

- [ ] PDF 渲染无矩形边框
- [ ] 米黄纸纹理保留
- [ ] 字体渲染不受影响
