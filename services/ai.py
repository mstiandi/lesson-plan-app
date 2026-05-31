import re
import anthropic
from config import API_KEY, BASE_URL, MODEL

_client = None

BUSINESS_TYPE_NAMES = {
    "lesson_plan": "教案",
    "teaching_plan": "教学计划",
    "teaching_summary": "教学总结",
}


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY, timeout=60)
    return _client


# ═══════════════════════════════════════════════════
# 三种业务 System Prompt
# ═══════════════════════════════════════════════════

SYSTEM_PROMPT_LESSON_PLAN = """你是一位经验丰富的中国中小学教案编写专家，熟悉各学科2022版新课标和一线教学实践。

根据教师提供的信息，生成一份结构完整、可直接使用的教案草稿。教师会审阅修改后手抄到教案本上。

**重要：不要写任何开场白、客套话或解释。直接从"## 课题"开始输出。不要说"好的""根据您的信息"之类的废话。**

严格按以下结构输出（用Markdown格式）：

## 课题
[课题名称]

## 教学目标
- **核心素养目标**：根据学科特点写2-3条（如语文：语言运用、思维能力、审美创造；数学：数感、运算能力、推理意识等）
- **具体目标**：本课时结束后学生应能…（写2-3条可检测的具体目标）

## 教学重点
[1条，写清楚本课时最重要的教学内容]

## 教学难点
[1条，写学生最可能遇到困难的地方，附简短的突破思路]

## 教学准备
[教师需要准备什么教具/PPT/材料；学生需要准备什么]

## 教学过程

### 一、导入（约X分钟）
[具体的导入方式：问题/情境/复习/故事…要有师生互动设计]

### 二、新授（约X分钟）
[分步骤写清楚每个环节：教师做什么、学生做什么、设计意图是什么]
1. …
2. …
3. …

### 三、巩固练习（约X分钟）
[具体的练习题或活动设计，至少2道/个]

### 四、课堂小结（约X分钟）
[小结方式：学生总结/教师梳理/思维导图…]

### 五、作业布置
[分层作业：基础题 + 拓展题]

## 板书设计
[用文字描述板书布局，或列出关键词/结构图]

## 教学反思提示
[2-3条本课时教学后应重点反思的问题，供教师手写]

**篇幅指引：** 约 800-1500 字（一课时教案）

**格式要求：**
- 纯 Markdown，不要代码块包裹
- 大标题用 ##，小标题用 ###
- 列表用 - 开头
- 不要写"注："或"提示："之类的编者注释
- 不要出现"请您审阅""以上是教案"等对教师的喊话"""


SYSTEM_PROMPT_TEACHING_PLAN = """你是一位经验丰富的中国中小学教学管理专家，熟悉各学科教学计划编写规范和学校教务管理要求。

根据教师提供的信息，生成一份完整的学期教学计划。教师会审阅修改后提交教务处存档。

**重要：不要写任何开场白、客套话或解释。直接从"## 学期教学计划"开始输出。**

严格按以下结构输出（用Markdown格式）：

## 学期教学计划

## 一、学情分析
- **班级基本情况**：[根据提供的班级情况，分析学生整体水平、学习习惯、能力分布]
- **上学期存在问题**：[分析可能存在的知识薄弱点和学习态度问题]

## 二、教材分析
- **教材版本与结构**：[所用教材的编排体系、单元划分、知识点分布]
- **重点章节**：[本学期的重点单元/章节及原因]
- **难点章节**：[学生可能遇到困难的章节及原因]

## 三、教学目标
- **知识与技能**：[本学期学生应掌握的知识点和技能，分条列出]
- **过程与方法**：[通过什么教学方式培养什么能力]
- **情感态度与价值观**：[结合学科特点，写1-2条]

## 四、教学进度表
用表格形式列出（必须包含周次、教学内容、课时、教学重难点、备注五列）：

| 周次 | 教学内容 | 课时 | 教学重难点 | 备注 |
|------|---------|------|-----------|------|
| 第1周 | … | … | … |
| … | … | … | … |

覆盖全部教学周数。

## 五、教学措施
[5-8条具体可行的教学策略和方法，每条约50字，避免套话]

## 六、培优补差计划
- **培优措施**：[2-3条，针对学有余力学生]
- **补差措施**：[2-3条，针对学习困难学生]

## 七、教学评价方案
- **过程性评价**：[课堂表现、作业、单元测试等]
- **终结性评价**：[期中/期末考试安排]

**篇幅指引：** 约 2000-3000 字（整学期规划，须包含完整进度表）

**格式要求：**
- 纯 Markdown，不要代码块包裹
- 大标题用 ##，小标题用 ###
- 列表用 - 开头
- 不要写"注："或"提示："之类的编者注释
- 不要出现"请您审阅""以上是教学计划"等对教师的喊话"""


SYSTEM_PROMPT_TEACHING_SUMMARY = """你是一位经验丰富的中国中小学教学管理专家，熟悉教师学期教学总结的撰写规范和学校考核要求。

根据教师提供的信息，生成一份结构完整的学期教学工作总结。教师会审阅修改后提交教务处。

**重要：不要写任何开场白、客套话或解释。直接从"## 学期教学总结"开始输出。**

严格按以下结构输出（用Markdown格式）：

## 学期教学总结

## 一、基本情况
[任教学科、年级、班级数、周课时数等基本信息概述]

## 二、教学计划完成情况
- **计划内容**：本学期计划教学单元/章节 __个
- **完成情况**：[根据提供的信息描述完成进度，如已完成/未完成的原因]
- **未完成内容及原因**：[如适用，如实说明]

## 三、主要成绩与经验
[3-5条，具体描述本学期教学中的亮点和有效做法，每条80-150字，用具体事例支撑，避免空话]

## 四、存在问题与不足
[3-5条，诚恳分析教学中存在的问题。注意：不能只归因于外部（"学生基础差""课时不够"），
每条问题必须包含：具体表现 + 自身原因分析 + 初步改进思路]

## 五、考试成绩分析
- **平均分**：[如提供数据，分析整体水平]
- **及格率/优秀率**：[分析两极分化情况]
- **典型错题分析**：[2-3道典型错题及背后反映的教学问题]
- **进退步分析**：[与上学期或平行班对比]

## 六、改进措施与下学期设想
[4-6条具体可操作的改进措施，每条50-80字，与"存在问题"逐条对应]

## 七、个人专业发展
- **本学期参加的教研活动**：[可写"如适用"]
- **自学与反思**：[教学理念、方法上的收获]
- **下学期个人发展目标**：[1-2条]

**篇幅指引：** 约 1500-2500 字（整学期回顾）

**格式要求：**
- 纯 Markdown，不要代码块包裹
- 大标题用 ##，小标题用 ###
- 列表用 - 开头
- 不要写"注："或"提示："之类的编者注释
- 不要出现"请您审阅""以上是总结"等对教师的喊话"""


# ═══════════════════════════════════════════════════
# 学校要求查询 Prompt
# ═══════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════
# 修改建议 Prompt
# ═══════════════════════════════════════════════════

REVISE_PROMPT = """你是一位专业的教学文档编辑。请根据用户的修改建议，对以下文档进行修改。

## 修改原则：
1. 只修改用户提到的部分，其他内容保持原样
2. 保持原文档的整体结构不变
3. 修改后的内容必须与原文风格一致
4. 如果用户要求"更详细"，增加具体事例而非空话
5. 如果用户要求"更简洁"，删减重复和冗余，保留关键信息

**重要：不要写任何开场白、客套话或解释。直接输出修改后的完整文档。**

## 学校要求（必须遵守）：
{requirements}

## 原文档：
{original_content}

## 用户修改建议：
{revision_note}

请输出修改后的完整文档（不要只输出修改部分，输出整份文档）。"""


# ═══════════════════════════════════════════════════
# System Prompt 构建
# ═══════════════════════════════════════════════════

def _get_base_prompt(business_type: str) -> str:
    if business_type == "teaching_plan":
        return SYSTEM_PROMPT_TEACHING_PLAN
    elif business_type == "teaching_summary":
        return SYSTEM_PROMPT_TEACHING_SUMMARY
    return SYSTEM_PROMPT_LESSON_PLAN


def build_system_prompt(school_info: dict, teaching_info: dict, business_type: str = "lesson_plan", location_requirements: str = "", requirements: str = "", word_count: int = 0) -> str:
    """Build system prompt with school context injected."""
    province = school_info.get('province', '')
    city = school_info.get('city', '')
    district = school_info.get('district', '')
    school = school_info.get('school_name', '')
    subject = teaching_info.get('subject', '')
    grade = teaching_info.get('grade', '')
    textbook = teaching_info.get('textbook', '')

    context_parts = [
        f"教师所在地区：{province} {city} {district}",
        f"学校名称：{school}",
        f"使用教材：{textbook}（{grade} {subject}）",
    ]

    if location_requirements:
        context_parts.append(f"\n地区教学要求参考：\n{location_requirements}")

    context_block = "\n".join(context_parts)

    guidance = f"""
在生成文档时请注意：
1. 严格遵循{province}现行教学大纲和课程标准
2. 内容须符合当地教研室对{subject}学科的要求
3. 根据"{school}"校名判断学校层次，匹配对应的教学深度要求
4. 如当地（特别是{city}）有中考独立命题，须在内容中体现命题风格
5. 考虑学校的实际条件，不预设高端设备
6. 使用规范的学术术语，避免口语化表达
7. 确保内容充实、可操作，不出现空洞的套话"""

    if word_count > 0:
        guidance += f"\n\n**字数要求：** 整份文档目标约{word_count}字。请根据此字数调整各板块详略程度，确保总字数接近目标。"

    if requirements:
        guidance += f"""

## 🔴 必须遵守的学校要求（硬性约束）：
{requirements}

请严格逐条对照上述要求生成文档，不得遗漏任何一条。"""

    return _get_base_prompt(business_type) + "\n\n" + context_block + guidance


def build_user_content(school_info: dict, teaching_info: dict, business_type: str = "lesson_plan", extra: dict | None = None) -> str:
    """Build user message based on business type."""
    subject = teaching_info['subject']
    grade = teaching_info['grade']
    textbook = teaching_info['textbook']
    extra = extra or {}

    if business_type == "teaching_plan":
        semester = extra.get('semester', '')
        weeks = extra.get('weeks', 20)
        class_situation = extra.get('class_situation', '')
        return f"""请为以下课程生成学期教学计划：

- 学科：{subject}
- 年级：{grade}
- 教材版本：{textbook}
- 学期：{semester}
- 教学周数：{weeks}周
- 班级情况：{class_situation or '未提供，请根据年级一般情况推断'}"""

    elif business_type == "teaching_summary":
        semester = extra.get('semester', '')
        plan_completion = extra.get('plan_completion', '')
        exam_results = extra.get('exam_results', '')
        return f"""请为以下课程生成学期教学总结：

- 学科：{subject}
- 年级：{grade}
- 教材版本：{textbook}
- 学期：{semester}
- 计划完成情况：{plan_completion or '未提供，请按一般情况撰写'}
- 考试成绩情况：{exam_results or '未提供，请按一般情况撰写'}"""

    # lesson_plan (default)
    topic = extra.get('topic', '')
    hours = teaching_info.get('hours', 1)
    return f"""请为以下课程生成教案草稿：

- 学科：{subject}
- 年级：{grade}
- 教材版本：{textbook}
- 课题：{topic}
- 课时数：{hours}课时"""


def build_requirements_query(school_info: dict, business_type: str, location_requirements: str = "") -> tuple[str, str]:
    """Build prompt for the /api/requirements/query endpoint."""
    province = school_info.get('province', '')
    city = school_info.get('city', '')
    district = school_info.get('district', '')
    school_name = school_info.get('school_name', '')
    business_name = BUSINESS_TYPE_NAMES.get(business_type, business_type)

    system = REQUIREMENTS_QUERY_PROMPT.format(
        province=province,
        city=city,
        district=district,
        school_name=school_name,
        business_type_name=business_name,
    )

    if location_requirements:
        system += f"\n\n补充参考——该地区已知教学政策：\n{location_requirements}"

    user = f"请为{school_name}的{business_name}列出具体要求。直接输出条目，每条一行，数字编号。"

    return system, user


# ═══════════════════════════════════════════════════
# AI 调用
# ═══════════════════════════════════════════════════

def call_ai(system: str, user: str) -> str:
    client = _get_client()
    last_err = None
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            content = ""
            for block in response.content:
                if block.type == "text":
                    content = block.text
                    break
            if not content:
                raise Exception("No text in response")
            # Strip code fences
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:]) if len(lines) > 1 else content
                if content.endswith("```"):
                    content = content[:-3]
            # Strip AI preamble/conversational fluff before the first ## heading
            content = _strip_preamble(content)
            return content.strip()
        except anthropic.APIConnectionError as e:
            last_err = e
            if attempt < 2:
                import time
                time.sleep(1 * (attempt + 1))
        except Exception as e:
            raise e
    raise last_err


def _strip_preamble(text: str) -> str:
    """Remove AI conversational preamble before the first ## heading."""
    m = re.search(r'^##\s+', text, re.MULTILINE)
    if m:
        return text[m.start():]

    # If no ## heading found, strip leading conversational prefix
    for prefix in ['好的', '根据您', '为您', '以下是', '这是', '已生成']:
        idx = text.find(prefix)
        if 0 <= idx < 80:
            nl = text.find('\n', idx)
            if nl > 0:
                return text[nl + 1:].strip()
    return text


def strip_markdown(text: str) -> str:
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^-\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text.strip()
