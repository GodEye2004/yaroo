import json
from typing import Any


def truncate_text(text: str, max_chars: int = 3000) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [ادامه متن حذف شد]"


def estimate_tokens(text: str) -> int:
    return len(text or "") // 4


def ensure_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value
