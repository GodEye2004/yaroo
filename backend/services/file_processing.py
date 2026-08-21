import io
import json

import chardet
from docx import Document

from services.text_processing import deep_clean_farsi_text


def process_txt(content: bytes) -> dict:
    detected = chardet.detect(content)
    encoding = detected.get("encoding") or "utf-8"
    raw_text = content.decode(encoding, errors="ignore")
    return {"text": deep_clean_farsi_text(raw_text)}


def process_docx(content: bytes) -> dict:
    doc = Document(io.BytesIO(content))
    full_text = "\n".join([para.text for para in doc.paragraphs])
    return {"text": deep_clean_farsi_text(full_text)}


def process_json(content: bytes) -> dict:
    return json.loads(content.decode("utf-8", errors="ignore"))
