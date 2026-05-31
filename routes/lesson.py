import uuid
import asyncio
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import Response
from urllib.parse import quote
from models import GenerateRequest, RenderRequest, TrainRequest, RequirementsQuery, ReviseRequest
from services.ai import (
    build_system_prompt, build_user_content, call_ai, build_requirements_query,
    REVISE_PROMPT, BUSINESS_TYPE_NAMES,
)
from services.location import get_location_requirements
from services.handwriting import render_handwritten_pages, pages_to_pdf, render_font_preview
from services.handwriting import extract_chars_from_image, preprocess_image, normalize_char_image
from config import (
    DEFAULT_FONT, UPLOADS_DIR, HANDWRITING_BANKS_DIR,
    MIN_UPLOAD_PHOTOS, MAX_UPLOAD_PHOTOS, OCR_CONFIDENCE_THRESHOLD,
)
from db import get_chars_db, insert_char, count_chars, count_unique_chars, load_meta, save_meta
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

router = APIRouter(prefix="/api")
executor = ThreadPoolExecutor(max_workers=3)

# Render cache: token → (pdf_bytes, expiry_timestamp)
_render_cache: dict[str, tuple[bytes, float]] = {}
_RENDER_CACHE_TTL = 600  # 10 minutes


def _cache_cleanup():
    """Remove expired entries from render cache."""
    now = time.time()
    expired = [k for k, v in _render_cache.items() if v[1] < now]
    for k in expired:
        del _render_cache[k]


def _cache_put(pdf_bytes: bytes) -> str:
    _cache_cleanup()
    token = uuid.uuid4().hex
    _render_cache[token] = (pdf_bytes, time.time() + _RENDER_CACHE_TTL)
    return token


@router.post("/requirements/query")
async def query_requirements(req: RequirementsQuery):
    """查询指定学校指定业务类型的格式要求（硬性限制流程第一步）。"""
    school = {"province": req.province, "city": req.city, "district": req.district, "school_name": req.school_name}

    loc_reqs = get_location_requirements(school["province"], school["city"])
    system, user = build_requirements_query(school, req.business_type, loc_reqs)

    try:
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(executor, call_ai, system, user)
        return {"success": True, "requirements": content.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_lesson_plan(req: GenerateRequest):
    school = req.school.model_dump()
    teaching = req.teaching.model_dump()

    loc_reqs = get_location_requirements(school["province"], school["city"])
    system_prompt = build_system_prompt(
        school, teaching, req.business_type, loc_reqs, req.requirements, req.word_count
    )

    extra = {}
    if req.business_type == "teaching_plan":
        extra = {"semester": req.semester, "weeks": req.weeks, "class_situation": req.class_situation}
    elif req.business_type == "teaching_summary":
        extra = {"semester": req.semester, "plan_completion": req.plan_completion, "exam_results": req.exam_results}
    else:
        extra = {"topic": req.topic}

    user_content = build_user_content(school, teaching, req.business_type, extra)

    try:
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(executor, call_ai, system_prompt, user_content)
        return {"success": True, "content": content.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/revise")
async def revise_content(req: ReviseRequest):
    """根据用户修改建议修订已生成的内容。"""
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


@router.post("/school-requirements")
async def query_school_requirements(req: GenerateRequest):
    """[兼容旧版] AI 根据学校信息 + 地区政策智能生成教案要求建议。"""
    school = req.school.model_dump()
    teaching = req.teaching.model_dump()

    loc_reqs = get_location_requirements(school["province"], school["city"])
    system, user = build_requirements_query(school, "lesson_plan", loc_reqs)

    try:
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(executor, call_ai, system, user)
        return {"success": True, "requirements": content.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/handwriting/upload")
async def upload_photos(files: list[UploadFile] = File(...)):
    if len(files) < MIN_UPLOAD_PHOTOS:
        raise HTTPException(status_code=400, detail=f"请至少上传{MIN_UPLOAD_PHOTOS}张照片")
    if len(files) > MAX_UPLOAD_PHOTOS:
        raise HTTPException(status_code=400, detail=f"最多上传{MAX_UPLOAD_PHOTOS}张照片")

    session_id = uuid.uuid4().hex
    upload_dir = UPLOADS_DIR / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    for f in files:
        if f.filename and f.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
            path = upload_dir / f"photo_{saved+1:03d}{Path(f.filename).suffix}"
            content = await f.read()
            path.write_bytes(content)
            # Resize to max 1200px wide
            try:
                img = Image.open(path)
                if img.width > 1200:
                    ratio = 1200 / img.width
                    new_h = int(img.height * ratio)
                    img = img.resize((1200, new_h), Image.LANCZOS)
                    img.save(path)
            except Exception:
                pass
            saved += 1

    if saved < MIN_UPLOAD_PHOTOS:
        raise HTTPException(status_code=400, detail=f"有效图片不足{MIN_UPLOAD_PHOTOS}张")

    from datetime import datetime
    meta = {
        "session_id": session_id,
        "status": "uploading",
        "char_count": 0,
        "total_samples": 0,
        "created_at": datetime.now().isoformat(),
        "photo_count": saved,
    }
    save_meta(session_id, meta)

    return {"session_id": session_id, "image_count": saved}


@router.post("/handwriting/train")
async def train_handwriting(req: TrainRequest, background_tasks: BackgroundTasks):
    session_id = req.session_id
    upload_dir = UPLOADS_DIR / session_id
    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    meta = load_meta(session_id)
    meta["status"] = "training"
    save_meta(session_id, meta)

    background_tasks.add_task(_run_training, session_id)

    return {"status": "training", "session_id": session_id}


def _run_training(session_id: str):
    upload_dir = UPLOADS_DIR / session_id
    bank_dir = HANDWRITING_BANKS_DIR / session_id
    images_dir = bank_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    conn = get_chars_db(session_id)
    meta = load_meta(session_id)

    total_samples = 0

    for photo_path in sorted(upload_dir.iterdir()):
        if not photo_path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp'):
            continue

        try:
            img = Image.open(photo_path)
            img = preprocess_image(img)
            img.save(photo_path)

            chars = extract_chars_from_image(str(photo_path))
            img_full = Image.open(photo_path)

            for char_info in chars:
                char = char_info["char"]
                bbox = char_info["bbox"]
                x, y, w, h = bbox

                try:
                    char_region = img_full.crop((x, y, x + w, y + h))
                    char_region = normalize_char_image(char_region)

                    img_name = f"{total_samples:06d}.png"
                    char_region.save(images_dir / img_name)

                    insert_char(conn, char, f"images/{img_name}", char_info["source_photo"], bbox)
                    total_samples += 1
                except Exception:
                    continue
        except Exception:
            continue

    unique = count_unique_chars(conn)
    meta["status"] = "ready"
    meta["char_count"] = unique
    meta["total_samples"] = total_samples
    save_meta(session_id, meta)


@router.get("/handwriting/status/{session_id}")
async def get_handwriting_status(session_id: str):
    meta = load_meta(session_id)
    return meta


@router.post("/handwriting/render")
async def render_handwritten(req: RenderRequest):
    try:
        font_path = DEFAULT_FONT
        if req.font_name:
            from config import scan_fonts
            for f in scan_fonts():
                if f["name"] == req.font_name:
                    font_path = f["path"]
                    break
        elif req.use_default and not req.session_id:
            font_path = DEFAULT_FONT

        loop = asyncio.get_running_loop()
        pages = await loop.run_in_executor(
            executor,
            render_handwritten_pages,
            req.content,
            font_path,
            req.session_id,
            req.scribble_prob,
            req.template_id,
        )
        pdf_bytes = pages_to_pdf(pages)

        # Cache for download and return token
        token = _cache_put(pdf_bytes)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"X-Download-Token": token},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/handwriting/download/{token}/{filename}")
async def download_rendered(token: str, filename: str):
    """Serve a previously rendered PDF as a file download."""
    _cache_cleanup()
    entry = _render_cache.get(token)
    if not entry:
        raise HTTPException(status_code=404, detail="PDF 已过期或不存，请重新生成")
    pdf_bytes, _ = entry
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
        },
    )


@router.get("/locations")
async def get_locations(parent: str = ""):
    from services.location import get_provinces, get_cities, get_districts

    if not parent:
        return get_provinces()
    parts = parent.split(",")
    if len(parts) == 1:
        return get_cities(parts[0])
    else:
        return get_districts(parts[0], parts[1])


@router.get("/templates")
async def list_templates():
    from services.templates import list_templates as lt
    return lt()


@router.get("/font-preview/{font_name}")
async def font_preview(font_name: str, text: str = "教案设计 教学目标 重难点"):
    from config import scan_fonts
    for f in scan_fonts():
        if f["name"] == font_name:
            png = render_font_preview(f["path"], text)
            return Response(content=png, media_type="image/png")
    raise HTTPException(status_code=404, detail="Font not found")
