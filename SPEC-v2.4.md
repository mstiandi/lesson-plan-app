# SPEC: v2.4 教案规范优化 + 纸张样式 + 地区数据修复

## 1. 背景纸样式：横线 → A4 空白纸

### 现状
当前手写 PDF 带横格线（ruling lines），模仿作业本。

### 问题
中国教师教案本通常不是横线纸。常见格式：
- 学校统一印制的教案纸：顶部有表头（学校/班级/教师/日期/课题），下方空白自由书写
- 或直接 A4 白纸打印手写效果
- 横线格更接近学生作业本，不是教案本

### 改动
**去掉横格线。** 纸张保持米黄色纹理（`make_paper_texture` 已有），加一个极淡的外边框模拟稿纸边界。

```python
# _add_ruling_lines 改名为 _add_paper_frame，只画一个淡色外框
def _add_paper_frame(img, margin_left, margin_top, margin_right, margin_bottom):
    """画一个极淡的矩形边框，模拟教案纸边界。"""
    draw = ImageDraw.Draw(img)
    W, H = img.width, img.height
    draw.rectangle(
        [(margin_left - 40, margin_top - 30), (W - margin_right, H - margin_bottom)],
        outline=(190, 185, 175),
        width=2,
    )
```

> 删除 `_add_ruling_lines`，替换为 `_add_paper_frame`。边框只勾勒书写区域边界，不画横线。

### 前端预览
字体预览卡片在 Section 4 的字体选择器里，不变。

---

## 2. 区域政策 + 学校教案规范注入

### 2.1 增强 System Prompt

在 `services/ai.py` 的 `build_system_prompt` 中，加强地区相关引导：

```python
def build_system_prompt(school_info, teaching_info, location_requirements):
    province = school_info.get('province', '')
    city = school_info.get('city', '')
    district = school_info.get('district', '')
    school = school_info.get('school_name', '')

    context = f"""
教师所在地区：{province} {city} {district}
学校名称：{school}
使用教材：{teaching_info.get('textbook', '')}（{teaching_info.get('grade', '')} {teaching_info.get('subject', '')}）

教案规范要求：
1. 严格遵循{province}现行教学大纲和课程标准
2. 教学目标须符合当地教研室对{teaching_info.get('subject', '')}学科的核心素养要求
3. 教学重难点设置参照当地学情（城区/县镇/农村学校有所区别）
4. 教学过程设计须体现学生主体地位，避免满堂灌
5. 如当地（特别是{city}）有中考独立命题，须在巩固练习和作业中体现命题风格
6. 教学反思提示应针对本课时实际教学效果，非套话
"""
    if location_requirements:
        context += f"\n地区教学要求参考：\n{location_requirements}"
    ...
```

### 2.2 扩展 location_requirements.json

在现有 12 个省/市基础上，为每个省级行政区至少补充一条教学要求。优先覆盖方案：从各省教育厅公开的"义务教育课程实施办法"中提取关键要求。

```json
{
  "安徽省": "安徽省义务教育课程实施办法（2023），初中阶段重视中考全省统一命题趋势，语文强调整本书阅读和写作能力，数学重视建模思想",
  "安徽省-淮南市": "淮南市中考使用省统考卷，重视基础知识和核心素养并重，教案须体现分层教学理念",
  ...
}
```

> 补充 22 个省的条目（现有 12 省/市），覆盖全部 31 个省级行政区 + 部分重点城市。

---

## 3. 行政区划数据修复 + 手动输入后备

### 问题
`locations.json` 只有 283 市 + 863 区县，遗漏了寿县等大量县级行政区。完整补全数据量大（~2800 区县），且部分数据可能有行政区划调整滞后。

### 方案：下拉联动（保留）+ 手动输入文本框

**Section 1 学校信息区域，每个下拉框旁边加一个"手动输入"开关：**

```html
<div class="form-row">
  <div>
    <label>省 / 直辖市</label>
    <select id="province"><!-- 下拉 --></select>
    <input type="text" id="provinceManual" placeholder="或手动输入省名"
           style="display:none;margin-top:4px;">
    <a href="#" onclick="toggleManual('province')"
       style="font-size:11px;color:#888;">找不到？手动输入</a>
  </div>
  <div>
    <label>市 / 区</label>
    <select id="city" disabled><!-- 下拉 --></select>
    <input type="text" id="cityManual" placeholder="或手动输入市名"
           style="display:none;margin-top:4px;">
    <a href="#" onclick="toggleManual('city')"
       style="font-size:11px;color:#888;">找不到？手动输入</a>
  </div>
</div>
```

JS 逻辑：
```js
function toggleManual(field) {
  const sel = document.getElementById(field);
  const manual = document.getElementById(field + 'Manual');
  const link = sel.nextElementSibling.nextElementSibling;
  if (manual.style.display === 'none') {
    manual.style.display = 'block';
    sel.style.display = 'none';
    link.textContent = '切换为下拉选择';
  } else {
    manual.style.display = 'none';
    sel.style.display = 'block';
    link.textContent = '找不到？手动输入';
  }
}

// 提交时优先用手动输入值
function getLocationValue(field) {
  const manual = document.getElementById(field + 'Manual');
  if (manual.style.display !== 'none' && manual.value.trim()) {
    return manual.value.trim();
  }
  const sel = document.getElementById(field);
  return sel.options[sel.selectedIndex]?.text || '';
}
```

每个字段（省/市/区县）都可以切换到手动输入。默认用下拉，下拉没有的条目用户自己填。

---

## 4. 改动文件清单

| 文件 | 改动 |
|------|------|
| `services/handwriting.py` | `_add_ruling_lines` → `_add_paper_frame`，去掉横线 |
| `services/ai.py` | 增强 `build_system_prompt` 的地区规范引导 |
| `services/location_requirements.json` | 补全 31 个省级行政区教学要求 |
| `static/index.html` | Section 1 每个下拉加手动输入开关 + JS |
| `static/locations.json` | 补充遗漏区县数据（如寿县等）|

---

## 5. 验收标准

- [ ] 手写 PDF 无横线，只有淡色外边框 + 米黄纸纹理
- [ ] 选择"安徽省-淮南市-寿县"（手动输入）→ AI 生成教案含安徽教学规范
- [ ] `location_requirements.json` 覆盖 31 个省级行政区
- [ ] 所有下拉框支持切换到手动文本输入
- [ ] 手动输入的值优先于下拉框选中值
