from pydantic import BaseModel


class SchoolInfo(BaseModel):
    province: str
    city: str
    district: str = ""
    school_name: str


class TeachingInfo(BaseModel):
    subject: str
    grade: str
    textbook: str
    hours: int = 1


class RequirementsQuery(BaseModel):
    province: str
    city: str
    district: str = ""
    school_name: str
    business_type: str  # "lesson_plan" | "teaching_plan" | "teaching_summary"


class GenerateRequest(BaseModel):
    school: SchoolInfo
    teaching: TeachingInfo
    business_type: str = "lesson_plan"
    requirements: str = ""
    word_count: int = 0

    # 教案字段
    topic: str = ""

    # 教学计划字段
    semester: str = ""
    weeks: int = 20
    class_situation: str = ""

    # 教学总结字段
    plan_completion: str = ""
    exam_results: str = ""


class ReviseRequest(BaseModel):
    original_content: str
    revision_note: str
    business_type: str = "lesson_plan"
    requirements: str = ""


class TrainRequest(BaseModel):
    session_id: str


class RenderRequest(BaseModel):
    content: str
    session_id: str | None = None
    use_default: bool = True
    font_name: str | None = None
    scribble_prob: float = 0.0
    template_id: str = "blank_a4"


class ConfigResponse(BaseModel):
    model: str
    api_ok: bool
    fonts: list[dict]


class GenerateResponse(BaseModel):
    success: bool
    content: str


class UploadResponse(BaseModel):
    session_id: str
    image_count: int


class TrainStatusResponse(BaseModel):
    status: str
    char_count: int
    total_samples: int
    photo_count: int


class ErrorResponse(BaseModel):
    detail: str
