# SPEC: v3.0 三大业务升级 — 教案 / 教学计划 / 教学总结

## 核心要求（优先级最高）

### 1. 内容质量过关
- AI 生成内容必须符合学校检查标准——结构完整、术语规范、可操作、不空洞
- 每个业务类型的 prompt 独立设计
- **硬性限制：用户必须提供或确认目标学校的教案/计划/总结要求，AI 才能生成**

### 2. 手写效果像真人写的
- 渲染管线不变：300 DPI + Handright + 钟齐志莽行书默认 + 涂改可选
- 所有三种业务输出统一走现有渲染引擎

---

## 前端布局（重构 Step 1、新增 Step 2）

```
┌─ SECTION 1: 学校信息 ─────────────────────┐
│  省/市/区县 + 学校名称（和现在一样）         │
│  【学校要求查询按钮已移到 Section 2】        │
└────────────────────────────────────────────┘

┌─ SECTION 2: 业务选择 + 学校要求 【新】─────┐
│                                              │
│  ┌─── 业务卡片选择 ───────────────────┐      │
│  │ 📖 教案  │ 📋 教学计划 │ 📝 教学总结 │     │
│  └───────────────────────────────────┘      │
│                                              │
│  ┌─── 共用教学信息 ──────────────────┐      │
│  │ 学科 [下拉]  年级 [下拉]  教材 [下拉] │     │
│  └───────────────────────────────────┘      │
│                                              │
│  ┌─── 学校要求（自动查询 + 硬性限制）──┐     │
│  │  🔍 正在查询"{学校名}"的"{教案/计划/总结}"要求...  │
│  │  ┌──────────────────────────────┐       │
│  │  │ [可编辑文本框，显示查询结果]    │       │
│  │  └──────────────────────────────┘       │
│  │  ✅ 已确认要求  [重新查询]               │
│  │  ⚠️ 请先确认学校要求，才能生成            │
│  └───────────────────────────────────┘      │
│                                              │
│  ┌─── 业务专属字段（随业务切换）─────┐      │
│  │ [教案模式] 课题名称 + 课时数          │      │
│  │ [计划模式] 学期 + 教学周数 + 班级情况  │      │
│  │ [总结模式] 学期 + 计划完成情况 + 成绩  │      │
│  └───────────────────────────────────┘      │
│                                              │
│  [🤖 生成电子文档]（要求未确认时禁用）        │
└────────────────────────────────────────────┘

┌─ SECTION 3: 生成电子文档 ──────────────────┐
│  编辑器（可编辑） → 复制/打印                 │
└────────────────────────────────────────────┘

┌─ SECTION 4: 手写版PDF ────────────────────┐
│  字体选择 + 涂改滑块 + 纸张样式（不变）       │
│  [🖨️ 下载手写版PDF]                         │
└────────────────────────────────────────────┘
```

---

## 关键交互流程

### 学校要求自动查询（硬性限制）

```
用户在 Section 1 填完学校信息（省/市/区/学校名）
    ↓
用户在 Section 2 选择业务类型（教案/计划/总结）
    ↓
【自动触发】调用 /api/requirements/query
    传入：province, city, district, school_name, business_type
    ↓
AI 查询并返回该校该业务的格式要求
    ↓
结果显示在可编辑文本框中
    ↓
用户审阅 → 可修改 → 点击"✅ 确认要求"
    ↓
"生成"按钮解锁
```

**"生成"按钮禁用条件（硬性限制）：**
- 学校名称未填写 → 禁用
- 要求文本框为空 → 禁用
- 用户未点击确认 → 禁用

### 业务切换时重新查询

```
用户从"教案"切到"教学计划"
    → 自动重新查询该校的"教学计划"要求
    → 显示到要求文本框
    → 用户需重新确认
    → 之前已确认的教案要求不清除（存在内存中，切回去时恢复）
```

---

## 新增/修改 API

### `POST /api/requirements/query`（新增）

```python
class RequirementsQuery(BaseModel):
    province: str
    city: str
    district: str
    school_name: str
    business_type: str  # "lesson_plan" | "teaching_plan" | "teaching_summary"

# 返回
{
    "requirements": "根据该校所在地区教育政策和学校层次…\n\n教案要求：…\n格式要求：…",
    "source": "AI 根据地区和学校信息推断"
}
```

**实现：** 调用 AI，用专用 prompt 查询该校对应业务的要求。如果 `location_requirements.json` 有匹配数据，作为 context 注入；同时让 AI 根据学校名称推断学校层次（省级重点/市级重点/普通/农村），给出对应要求。

```python
REQUIREMENTS_QUERY_PROMPT = """你是一位熟悉中国中小学教学管理的专家。
请根据以下信息，推断该校教师在撰写{business_type_name}时需要遵守的具体要求：

- 地区：{province} {city} {district}
- 学校：{school_name}
- 业务类型：{business_type_name}

请从以下维度分析：
1. 当地教育行政部门（省/市/区县教研室）对该文档的格式要求
2. 该学校层次（重点/普通/农村）对应的文档深度要求
3. 该地区中考/统考命题特点对该文档内容的影响
4. 该校可能使用的校内模板或格式规范

请以简洁的要点形式输出，每条不超过50字，总共5-8条。"""
```

### `POST /api/generate`（修改）

现有接口，新增 `requirements` 字段（用户确认后的要求文本），注入到生成 prompt 中：

```python
class GenerateRequest(BaseModel):
    school: SchoolInfo
    teaching: TeachingInfo
    business_type: BusinessType
    requirements: str = ""   # 新增：用户确认的学校要求

    # 业务专属字段（同上一版 spec）
    topic: str = ""
    semester: str = ""
    weeks: int = 20
    ...
```

生成时，`requirements` 直接拼入 system prompt 的末尾作为硬性约束：

```python
system_prompt = base_prompt + f"""

## 🔴 必须遵守的学校要求（硬性约束）：
{requirements}

请严格逐条对照上述要求生成文档，不得遗漏任何一条。"""
```

---

## 前端 JS 关键逻辑

```js
let currentBusiness = 'lesson_plan';
let confirmedRequirements = {};  // { 'lesson_plan': '...', 'teaching_plan': '...' }
let requirementsConfirmed = false;

async function switchBusiness(type) {
    currentBusiness = type;
    // UI 切换...
    
    // 如果该业务已确认过要求，恢复
    if (confirmedRequirements[type]) {
        document.getElementById('requirementsText').value = confirmedRequirements[type];
        requirementsConfirmed = true;
        updateGenerateButton();
        return;
    }
    
    // 否则自动查询
    requirementsConfirmed = false;
    updateGenerateButton();
    await queryRequirements(type);
}

async function queryRequirements(type) {
    const schoolName = document.getElementById('schoolName').value.trim();
    if (!schoolName) {
        document.getElementById('requirementsText').value = '';
        document.getElementById('reqStatus').textContent = '⚠️ 请先在 Section 1 填写学校名称';
        return;
    }
    
    document.getElementById('reqStatus').textContent = '🔍 正在查询...';
    const r = await fetch('/api/requirements/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            province: getLocationValue('province'),
            city: getLocationValue('city'),
            district: getLocationValue('district'),
            school_name: schoolName,
            business_type: type
        })
    });
    const data = await r.json();
    document.getElementById('requirementsText').value = data.requirements;
    document.getElementById('reqStatus').textContent = '📋 请审阅并确认以上要求（可修改）';
}

function confirmRequirements() {
    const text = document.getElementById('requirementsText').value.trim();
    if (!text) return;
    confirmedRequirements[currentBusiness] = text;
    requirementsConfirmed = true;
    document.getElementById('reqStatus').textContent = '✅ 已确认要求';
    updateGenerateButton();
}

function updateGenerateButton() {
    const btn = document.getElementById('generateBtn');
    const schoolName = document.getElementById('schoolName').value.trim();
    btn.disabled = !(schoolName && requirementsConfirmed);
}
```

---

## 后端 Prompt 设计（核心）

### 三种业务的 System Prompt 保持不变（同上一版 spec）

教案、教学计划、教学总结各有独立 prompt，结构、质量要求在 spec 中已定义。

**关键差异：** 生成时动态注入 `requirements` 作为硬性约束，追加在 prompt 末尾。

---

## 文件改动清单

| 文件 | 改动 |
|------|------|
| `models.py` | `RequirementsQuery`、`GenerateRequest` 加 `requirements` 字段 |
| `services/ai.py` | 新增 `REQUIREMENTS_QUERY_PROMPT`、三种业务 prompt + 需求注入 |
| `routes/lesson.py` | 新增 `POST /api/requirements/query`、`/api/generate` 适配 |
| `static/index.html` | Section 2 改业务选择 + 要求自动查询 + 确认逻辑 + 生成按钮禁用 |
| `services/location_requirements.json` | 扩展各业务类型细分要求（可选，现有数据已可用） |

---

## 验收标准

- [ ] 填写学校名称 → 选业务 → 自动弹出该业务的学校要求
- [ ] 要求未确认时，"生成"按钮灰色不可点
- [ ] 确认要求后，"生成"按钮解锁
- [ ] 生成内容体现要求中的约束（如"要求写教学进度表"→内容必须有进度表）
- [ ] 切换业务 → 自动重新查询 → 需重新确认
- [ ] 三种业务均可用 6 种字体 + 涂改渲染手写 PDF
- [ ] 手写 PDF 300 DPI 打印效果逼真
