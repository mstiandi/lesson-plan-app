from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from config import PORT, DEFAULT_FONT, MODEL, API_KEY, STATIC_DIR, SESSION_TTL_DAYS
from routes.lesson import router as lesson_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db import cleanup_expired_sessions
    cleanup_expired_sessions(ttl_days=SESSION_TTL_DAYS)
    yield


app = FastAPI(title="教师教案助手", lifespan=lifespan)

app.include_router(lesson_router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/config")
async def get_config():
    from config import scan_fonts
    return {
        "model": MODEL,
        "api_ok": bool(API_KEY),
        "fonts": scan_fonts(),
    }


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
