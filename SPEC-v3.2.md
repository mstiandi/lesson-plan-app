# SPEC: v3.2 新增 3 种手写字体（6 → 9）

## 目标

字体从 6 种扩充到 9 种，加入更接近真人手写风格的选择。

## 新增字体

| 文件名 | 显示名 | 来源 | 风格 |
|--------|--------|------|------|
| `Xiaolai-Regular.ttf` | 小赖手写体 | lxgw/kose-font | 濑户字体改版，日常手写感 |
| `ChenYuluoyan-2.0-Thin.ttf` | 辰宇落雁體 | Chenyu-otf/chenyuluoyan_thin | 真人手写，瘦长流动 |
| `LXGWZhenKaiGB-Regular.ttf` | 霞鹜臻楷 | lxgw/LxgwZhenKai | 精致楷书，国标字形 |

## 落地师操作

### 1. 下载字体

```bash
# 小赖手写体
gh release download -R lxgw/kose-font -p "Xiaolai-Regular.ttf" -D fonts/ --clobber

# 辰宇落雁體
gh release download -R Chenyu-otf/chenyuluoyan_thin -p "ChenYuluoyan-2.0-Thin.ttf" -D fonts/ --clobber

# 霞鹜臻楷
gh release download -R lxgw/LxgwZhenKai -p "LXGWZhenKaiGB-Regular.ttf" -D fonts/ --clobber
```

### 2. `config.py` — `FONT_DISPLAY_NAMES` 加 3 行

```python
FONT_DISPLAY_NAMES = {
    "ZhiMangXing-Regular": "钟齐志莽行书（行书·推荐）",
    "LXGWWenKai-Regular": "霞鹜文楷（楷书）",
    "Xiaolai-Regular": "小赖手写体",                              # 新增
    "ChenYuluoyan-2.0-Thin": "辰宇落雁體（真人手写）",            # 新增
    "LXGWZhenKaiGB-Regular": "霞鹜臻楷",                          # 新增
    "YShiWrittenSC-Regular": "写意体（手写简体）",
    "Yozai-Regular": "悠哉手写体",
    "MaokenYingBiKaiShuJ": "猫啃硬笔楷书",
    "ZCOOLKuaiLe": "站酷快乐体",
}
```

### 3. 调参

钟齐志莽行书和辰宇落雁體笔画偏细，需要确认 `_handright_params` 的细笔画字体检测关键词覆盖：

```python
if any(k in name for k in ('zhimang', 'yshiwritten', 'chenyuluoyan', 'xiaolai')):
```

> 加 `'chenyuluoyan'` 和 `'xiaolai'` 到细笔画字体组。

## 不需要改

- 前端字体卡片自动从 `/api/config` 拉取，加新字体自动出现
- 渲染管线不变
- 其他代码不变

## 验收

- [ ] 9 种字体全部出现在下拉框
- [ ] 新增 3 种字体均可正常渲染手写 PDF
- [ ] 细笔画字体自动使用大字号 + 深墨色参数
