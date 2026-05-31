import sqlite3
import json
from pathlib import Path
from config import HANDWRITING_BANKS_DIR


def get_chars_db(session_id: str) -> sqlite3.Connection:
    """Open or create the chars.db for a handwriting session."""
    session_dir = HANDWRITING_BANKS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    db_path = session_dir / "chars.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unicode TEXT NOT NULL,
            image_path TEXT NOT NULL,
            source_photo TEXT NOT NULL,
            bbox_x INTEGER,
            bbox_y INTEGER,
            bbox_w INTEGER,
            bbox_h INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chars_unicode ON chars(unicode)"
    )
    conn.commit()
    return conn


def insert_char(
    conn: sqlite3.Connection,
    unicode: str,
    image_path: str,
    source_photo: str,
    bbox: tuple[int, int, int, int] | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO chars (unicode, image_path, source_photo, bbox_x, bbox_y, bbox_w, bbox_h) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            unicode,
            image_path,
            source_photo,
            bbox[0] if bbox else None,
            bbox[1] if bbox else None,
            bbox[2] if bbox else None,
            bbox[3] if bbox else None,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_chars_for(conn: sqlite3.Connection, char: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, image_path, bbox_x, bbox_y, bbox_w, bbox_h FROM chars WHERE unicode = ?",
        (char,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "image_path": r[1],
            "bbox": (r[2], r[3], r[4], r[5]) if r[2] is not None else None,
        }
        for r in rows
    ]


def count_chars(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM chars").fetchone()[0]


def count_unique_chars(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(DISTINCT unicode) FROM chars").fetchone()[0]


def load_meta(session_id: str) -> dict:
    meta_path = HANDWRITING_BANKS_DIR / session_id / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "session_id": session_id,
        "status": "uploading",
        "char_count": 0,
        "total_samples": 0,
        "created_at": "",
        "photo_count": 0,
    }


def save_meta(session_id: str, meta: dict):
    session_dir = HANDWRITING_BANKS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    meta_path = session_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def cleanup_expired_sessions(ttl_days: int = 7):
    """Remove sessions older than ttl_days from handwriting_banks and uploads."""
    import shutil
    from datetime import datetime, timedelta
    from config import UPLOADS_DIR

    cutoff = datetime.now() - timedelta(days=ttl_days)

    for base_dir in (HANDWRITING_BANKS_DIR, UPLOADS_DIR):
        if not base_dir.exists():
            continue
        for session_dir in base_dir.iterdir():
            if not session_dir.is_dir():
                continue
            meta_path = session_dir / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    created = meta.get("created_at", "")
                    if created:
                        created_dt = datetime.fromisoformat(created)
                        if created_dt < cutoff:
                            shutil.rmtree(session_dir, ignore_errors=True)
                except (ValueError, OSError):
                    pass
