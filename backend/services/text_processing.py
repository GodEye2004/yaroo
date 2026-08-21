import unicodedata

from hazm import Normalizer

normalizer = Normalizer()


def deep_clean_farsi_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = normalizer.normalize(text)
    return text.strip()


def looks_garbled(text: str) -> bool:
    """Detect OCR that split Persian words into 1-2 character tokens."""
    if not text:
        return False
    words = [w for w in text.split() if w]
    if len(words) < 8:
        return False
    short = sum(1 for w in words if len(w) <= 2)
    return (short / len(words)) > 0.6
