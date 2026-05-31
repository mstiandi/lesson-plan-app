import json
from pathlib import Path
from config import STATIC_DIR

_locations: dict | None = None
_location_requirements: dict | None = None


def _load_locations() -> dict:
    global _locations
    if _locations is None:
        path = STATIC_DIR / "locations.json"
        if path.exists():
            _locations = json.loads(path.read_text(encoding="utf-8"))
        else:
            _locations = {"provinces": []}
    return _locations


def _load_requirements() -> dict:
    global _location_requirements
    if _location_requirements is None:
        req_path = Path(__file__).parent / "location_requirements.json"
        if req_path.exists():
            _location_requirements = json.loads(req_path.read_text(encoding="utf-8"))
        else:
            _location_requirements = {}
    return _location_requirements


def get_provinces() -> list[dict]:
    data = _load_locations()
    return [
        {"code": p["code"], "name": p["name"]}
        for p in data.get("provinces", [])
    ]


def get_cities(parent_code: str) -> list[dict]:
    data = _load_locations()
    for p in data.get("provinces", []):
        if p["code"] == parent_code:
            return [
                {"code": c["code"], "name": c["name"]}
                for c in p.get("cities", [])
            ]
    return []


def get_districts(province_code: str, city_code: str) -> list[dict]:
    data = _load_locations()
    for p in data.get("provinces", []):
        if p["code"] == province_code:
            for c in p.get("cities", []):
                if c["code"] == city_code:
                    return [
                        {"code": d["code"], "name": d["name"]}
                        for d in c.get("districts", [])
                    ]
    return []


def get_location_requirements(province: str, city: str) -> str:
    """Get teaching requirements for a specific location."""
    reqs = _load_requirements()
    province_reqs = reqs.get(province, "")
    city_reqs = reqs.get(f"{province}-{city}", "")

    parts = []
    if province_reqs:
        parts.append(f"【{province}】{province_reqs}")
    if city_reqs:
        parts.append(f"【{city}】{city_reqs}")
    return "\n".join(parts)
