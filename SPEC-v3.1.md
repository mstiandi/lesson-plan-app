# SPEC: v3.1 字数控制 + 修改建议 + Prompt 微调

## 1. 字数控制

### 前端
Section 3 生成按钮上方加一个字数选择：

```html
<div class="form-row">
  <div>
    <label for="wordCount">目标字数</label>
    <select id="wordCount">
      <option value="0">自动（推荐）</option>
      <option value="800">约 800 字（精简）</option>
      <option value="1500">约 1500 字（标准）</option>
      <option value="2500">约 2500 字（详细）</option>
      <option value="4000">约 4000 字（超详细）</option>
    </select>
  </div>
</div>
```

### 后端
`GenerateRequest` 新增 `word_count: int = 0`。生成时注入到 system prompt：

```python
if word_count > 0:
    guidance += f"\n\n**字数要求：** 整份文档目标约{word_count}字。根据此字数调整各板块详略程度。"
```

### Prompt 中字数默认建议

在三种业务的 system prompt 末尾加字数指引：

```
教案：约 800-1500 字（一课时）
教学计划：约 2000-3000 字（整学期规划，须包含完整进度表）
教学总结：约 1500-2500 字（整学期回顾）
```

---

## 2. 修改建议功能

### 交互流程

```
AI 生成初稿 → 编辑区展示
  → 用户不满意 → 在"修改建议"框输入意见
    → 如"教学过程太简单了，加一个小组讨论环节"
    → 如"教学反思写得不够深刻，请重写"
    → 如"多引用一些新课标术语"
  → 点击「根据建议修改」
  → AI 收到 原稿 + 修改建议 → 输出修改后的完整文档
  → 替换编辑区内容
```

### 前端

编辑区下方新增修改建议区域：

```html
<div class="form-row col-1" style="margin-top:12px;">
  <label for="revisionNote">修改建议（可选）</label>
  <div style="display:flex;gap:8px;">
    <input type="text" id="revisionNote" placeholder="如：教学过程加一个小组讨论环节，教学反思写得更深刻些…"
           style="flex:1;">
    <button class="btn-outline btn-sm" id="reviseBtn" onclick="reviseContent()"
            style="width:auto;white-space:nowrap;">
      根据建议修改
    </button>
  </div>
</div>
<div class="spinner" id="reviseSpinner">AI 正在根据建议修改…</div>
```

JS 逻辑：

```js
async function reviseContent() {
  const note = document.getElementById('revisionNote').value.trim();
  if (!note) return showError('请输入修改建议');
  
  const currentContent = document.getElementById('editor').innerText;
  const btn = document.getElementById('reviseBtn');
  const spinner = document.getElementById('reviseSpinner');
  
  btn.disabled = true;
  spinner.className = 'spinner show';
  hideError();
  
  try {
    const r = await fetch('/api/revise', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        original_content: currentContent,
        revision_note: note,
        business_type: currentBusiness,
        requirements: confirmedRequirements[currentBusiness] || ''
      })
    });
    const data = await r.json();
    if (!data.success) throw new Error(data.detail || '修改失败');
    
    generatedContent = data.content;
    renderToEditor(data.content);
    document.getElementById('revisionNote').value = '';
  } catch(e) {
    showError('修改失败：' + e.message);
  } finally {
    btn.disabled = false;
    spinner.className = 'spinner';
  }
}
```

### 后端

新增 `POST /api/revise` 端点。

`models.py`:
```python
class ReviseRequest(BaseModel):
    original_content: str
    revision_note: str
    business_type: str = "lesson_plan"
    requirements: str = ""
```

`services/ai.py`:
```python
REVISE_PROMPT = """你是一位专业的教学文档编辑。请根据用户的修改建议，对以下文档进行修改。

## 修改原则：
1. 只修改用户提到的部分，其他内容保持原样
2. 保持原文档的整体结构不变
3. 修改后的内容必须与原文风格一致
4. 如果用户要求"更详细"，增加具体事例而非空话
5. 如果用户要求"更简洁"，删减重复和冗余，保留关键信息

## 学校要求（必须遵守）：
{requirements}

## 原文档：
{original_content}

## 用户修改建议：
{revision_note}

请输出修改后的完整文档（不要只输出修改部分，输出整份文档）。"""
```

`routes/lesson.py`:
```python
@router.post("/revise")
async def revise_content(req: ReviseRequest):
    system = REVISE_PROMPT.format(
        requirements=req.requirements,
        original_content=req.original_content,
        revision_note=req.revision_note,
    )
    user = f"请根据建议修改这份{BUSINESS_TYPE_NAMES.get(req.business_type, '文档')}。直接输出修改后的完整文档。"
    
    try:
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(executor, call_ai, system, user)
        return {"success": True, "content": content.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 3. Prompt 微调

### 3.1 教学计划 Prompt 优化

进度表增加"教学重难点"列（当前只有周次/内容/课时/备注）：

```
| 周次 | 教学内容 | 课时 | 教学重难点 | 备注 |
```

### 3.2 教学总结 Prompt 优化

"存在问题"部分增加自检提示：

```
## 四、存在问题与不足
[3-5条，诚恳分析。注意：不能只归因于外部（"学生基础差""课时不够"），
每条问题必须包含：具体表现 + 自身原因分析 + 初步改进思路]
```

### 3.3 所有 Prompt 统一加

末尾追加：

```
**格式要求：**
- 纯 Markdown，不要代码块包裹
- 大标题用 ##，小标题用 ###
- 列表用 - 开头
- 不要写"注："或"提示："之类的编者注释
- 不要出现"请您审阅""以上是教案"等对教师的喊话
```

### 3.4 `_strip_preamble` 增强

当前只处理 `##` 开头的格式。有些 AI 会在 `##` 之前插入无标题文字（如"以下是您的教案："）。增强清理逻辑：

```python
def _strip_preamble(text: str) -> str:
    # 移除所有在第一个 ## 之前的文字
    m = re.search(r'^##\s+', text, re.MULTILINE)
    if m:
        return text[m.start():]
    
    # 如果整篇无 ## 标题，移除第一段明显的前导语
    for prefix in ['好的', '根据您', '为您', '以下是', '这是', '已生成']:
        idx = text.find(prefix)
        if 0 <= idx < 80:
            # 找到下一个换行后的内容
            nl = text.find('\n', idx)
            if nl > 0:
                return text[nl+1:].strip()
    return text
```

---

## 4. 文件改动

| 文件 | 改动 |
|------|------|
| `models.py` | `GenerateRequest` + `word_count`, 新增 `ReviseRequest` |
| `services/ai.py` | 新增 `REVISE_PROMPT`，三种 prompt 微调，`_strip_preamble` 增强 |
| `routes/lesson.py` | 新增 `POST /api/revise`，`/api/generate` 传递 `word_count` |
| `static/index.html` | 字数选择器 + 修改建议区域 + `reviseContent()` |

---

## 5. 验收标准

- [ ] 选择"约 800 字精简"→ AI 输出明显短于默认
- [ ] 选择"约 4000 字超详细"→ AI 输出显著更长、更详细
- [ ] 输入修改建议"教学过程加一个小组讨论"→ AI 在修改后的文本中加入了小组讨论环节
- [ ] 输入修改建议"教学反思写得更深刻"→ 修改后的反思部分更具体、有实例
- [ ] 修改建议不影响原文档中未被提及的部分
- [ ] 所有三种业务均支持字数控制和修改建议
