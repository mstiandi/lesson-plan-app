# SPEC: v3.3 学校要求查询改为静态数据 + UI 优化

## 1. 要求查询：AI → 静态数据

### 问题
Vercel Hobby Plan 函数 10s 超时，`/api/requirements/query` 每次调 AI 超过时限 → 500。

### 方案
改成纯静态数据查询，不调 AI。数据来源 `location_requirements.json`（38 条省/市级教学要求，来源为各省教育厅公开文件），追加通用业务格式规范。

### `routes/lesson.py` — `/api/requirements/query` 替代实现

```python
@router.post("/requirements/query")
async def query_requirements(req: RequirementsQuery):
    """查询学校要求 — 基于各省教育厅公开数据 + 通用规范。"""
    loc_reqs = get_location_requirements(req.province, req.city)
    business_name = BUSINESS_TYPE_NAMES.get(req.business_type, '此文档')

    lines = []
    
    # 地区特定要求
    if loc_reqs:
        lines.append(f"【{req.province}教学要求】\n{loc_reqs}")

    # 学校层次推断
    school = req.school_name
    tier_hint = ""
    for keyword, tier in [("附中", "省级重点"), ("一中", "市级重点/县中"), 
                           ("实验", "市级示范"), ("二中", "普通"), ("乡", "农村"), ("镇", "农村")]:
        if keyword in school:
            tier_hint = f"（推断学校层次：{tier}）"
            break
    if tier_hint:
        lines.append(f"学校层次{tier_hint}")

    # 通用要求
    lines.append(f"【{business_name}通用规范】")
    lines.append("1. 格式须符合该校教务处统一模板")
    lines.append("2. 内容须体现实质性教学思考，避免套话空话")
    lines.append("3. 须结合教材版本和学情具体撰写")
    lines.append("4. 教学目标须区分核心素养目标和具体可检测目标")
    lines.append("5. 如当地有中考独立命题，须在内容中体现命题风格")

    requirements = "\n".join(lines)
    
    source = f"数据来源：教育部/各省教育厅公开文件 + {req.province}教研室通用要求"
    
    return {"success": True, "requirements": requirements, "source": source}
```

### 前端显示数据来源

`requirementsText` 下方标注来源：

```html
<div id="reqSource" style="font-size:11px;color:#aaa;margin-top:2px;"></div>
```

`queryRequirements` 成功回调中设置 `reqSource.textContent`。

## 2. UI：学校要求框增大

`requirementsText` textarea 从 3 行改成 6 行：

```html
<textarea id="requirementsText" rows="6"
          placeholder="填写学校名称并选择业务类型后，自动查询该校要求…"></textarea>
```

## 3. 文件改动

| 文件 | 改动 |
|------|------|
| `routes/lesson.py` | `/api/requirements/query` 替换为静态数据实现 |
| `services/ai.py` | 可删掉 `REQUIREMENTS_QUERY_PROMPT` 和 `build_requirements_query`（或保留备用） |
| `static/index.html` | textarea rows=6 + 显示数据来源 |

## 4. 验收

- [ ] 选择学校+业务 → 瞬间返回要求（不调 AI，<100ms）
- [ ] 要求内容体现省份特征（如选"安徽淮南"有安徽相关条目）
- [ ] 要求内容可编辑
- [ ] 底部显示数据来源说明
- [ ] Vercel 部署不再 500
