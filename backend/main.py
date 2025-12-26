import io
import re
import traceback
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os, json, httpx
import chardet
from langchain_community.document_loaders import PyPDFLoader
from pydantic import BaseModel, Field
import uvicorn
from typing import List, Dict
import unicodedata
from hazm import Normalizer
from bs4 import BeautifulSoup
import random
import tempfile
from dotenv import load_dotenv
# ✅ تغییر: استفاده از Supabase به جای SQLAlchemy
from db_config import supabase
# افزودن ایمپورت‌های لازم برای Azure AI Inference
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference.models import UserMessage

load_dotenv()
print("SUPABASE_KEY:", repr(os.getenv("SUPABASE_SERVICE_KEY")))

# تغییر: استفاده از GITHUB_TOKEN به جای OPENAI_API_KEY
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ENDPOINT = "https://models.inference.ai.azure.com"
MODEL_NAME = "gpt-4o"  # تغییر از "gpt-4.1-mini" به "gpt-4o-mini" که معتبر است

# ----------------------------
# FastAPI setup
# ----------------------------
app = FastAPI()

# ✅ تغییر: حذف startup event برای SQLAlchemy # دیگر نیازی به create_all نیست، جدول را در Supabase ساختیم

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_CHUNK_SIZE = 1000
normalizer = Normalizer()
chat_memory = {}
MAX_MEMORY = 5





async def scrape_web_content(url: str) -> str:
    try:
        async with httpx.AsyncClient(
                timeout=25,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for script in soup(["script", "style"]):
                script.decompose()
            paragraphs = [p.get_text().strip() for p in soup.find_all("p")[:20] if p.get_text().strip()]
            text = "\n".join(paragraphs)[:4000]
            text = text.replace("\u200c", " ").strip()
            if text:
                print(f"DEBUG: Successfully scraped {len(text)} characters from {url}")
                return text
            else:
                print(f"WARNING: No text content scraped from {url}")
                return "No readable text found on this page."
    except Exception as e:
        print(f"ERROR scraping {url}: {str(e)}")
        return f"Failed to scrape this source: {str(e)}"





# ----------------------------
# تابع کمکی برای محدود کردن طول متن
# ----------------------------
def truncate_text(text: str, max_chars: int = 3000) -> str:
    """محدود کردن متن به تعداد کاراکتر مشخص"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [ادامه متن حذف شد]"


def estimate_tokens(text: str) -> int:
    """تخمین تعداد توکن‌ها (تقریباً 1 توکن = 4 کاراکتر برای فارسی)"""
    return len(text) // 4


# ----------------------------
# LLM
# ----------------------------
async def github_llm(prompt: str) -> str:
    # بررسی طول پرامپت قبل از ارسال
    estimated_tokens = estimate_tokens(prompt)
    print(f"📊 تخمین تعداد توکن‌های پرامپت: {estimated_tokens}")

    if estimated_tokens > 7000:  # حد امن کمتر از 8000
        print(f"⚠️ پرامپت خیلی بزرگ است ({estimated_tokens} توکن). در حال کوتاه کردن...")
        # اگر پرامپت خیلی بزرگ بود، آن را کوتاه کن
        prompt = prompt[:28000]  # حدود 7000 توکن

    client = ChatCompletionsClient(
        endpoint=ENDPOINT,
        credential=AzureKeyCredential(GITHUB_TOKEN)
    )

    final_text = ""

    try:
        # اگر complete async باشه
        maybe_async = client.complete(
            stream=True,
            messages=[UserMessage(content=prompt)],
            model=MODEL_NAME,
            temperature=0.3
        )

        if hasattr(maybe_async, "__aiter__"):
            # async iterator
            async for update in maybe_async:
                if update.choices and update.choices[0].delta and update.choices[0].delta.content:
                    final_text += update.choices[0].delta.content
        else:
            # sync iterator
            for update in maybe_async:
                if update.choices and update.choices[0].delta and update.choices[0].delta.content:
                    final_text += update.choices[0].delta.content

    except Exception as e:
        raise Exception(f"Azure AI Inference returned error: {str(e)}")
    finally:
        # فقط اگر close async هست await کن
        close_fn = getattr(client, "close", None)
        if close_fn:
            if callable(close_fn):
                maybe_awaitable = close_fn()
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable  # safe await

    return final_text.strip()


# Pydantic models by category
class Contract(BaseModel):
    parties: List[str] = Field(description="اسامی طرفین قرارداد")
    subject: str = Field(description="موضوع قرارداد")
    duration: str = Field(description="مدت قرارداد")
    conditions: List[str] = Field(description="شرایط و تعهدات")
    penalties: str = Field(description="جریمه‌ها و ضمانت‌ها")
    signatures: List[str] = Field(description="امضاها")


class Resume(BaseModel):
    name: str = Field(description="نام و نام خانوادگی")
    contact: dict = Field(description="اطلاعات تماس (ایمیل، تلفن)")
    education: List[dict] = Field(description="تحصیلات")
    experience: List[dict] = Field(description="تجربیات کاری")
    skills: List[str] = Field(description="مهارت‌ها")


class Will(BaseModel):
    testator: str = Field(description="نام وصیت‌کننده")
    beneficiaries: List[str] = Field(description="وارثان و ذی‌نفعان")
    assets: List[dict] = Field(description="دارایی‌ها و نحوه تقسیم")
    conditions: List[str] = Field(description="شرایط وصیت")
    executor: str = Field(description="مجری وصیت")


CATEGORY_MODELS = {
    "contract": Contract,
    "resume": Resume,
    "will": Will,
}


# select categories
@app.post("/select_category")
async def select_category(request: Request):
    body = await request.json()
    user_id = body.get("user_id")
    category = body.get("category")
    print("Raw category recive from front ", repr(category))
    if not user_id or not category:
        return JSONResponse(status_code=400, content={"error": "user_id and category are required"})

    # ✅ تغییر: استفاده از Supabase
    existing = supabase.table("ai_assist").select("*").eq("user_id", user_id).execute()
    if existing.data:
        # آپدیت
        supabase.table("ai_assist").update({
            "category": category
        }).eq("user_id", user_id).execute()
    else:
        # ساخت جدید
        supabase.table("ai_assist").insert({
            "user_id": user_id,
            "category": category,
            "data": {}
        }).execute()

    return {"message": f"Category '{category}' activated."}


# normalize persian text
def deep_clean_farsi_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("‌", " ").replace("\u200c", " ")
    text = normalizer.normalize(text)
    return text.strip()


def looks_garbled(text: str) -> bool:
    bad_patterns = [
        r"[اآبپتثجچحخدذرزسشصضطظعغفقکگلمنوهی]{1,2}\s[اآبپتثجچحخدذرزسشصضطظعغفقکگلمنوهی]{1,2}",
        r"[ﮐﻟﻣﻧﻫﻳﺍﺏﺕﺩﺭﺯﺱﺵﺹﺿﻁﻅﻉﻍﻑﻕﻙﻙﻝﻡﻥﻩﻱ]",
    ]
    for pattern in bad_patterns:
        if re.search(pattern, text):
            return True
    return False


def chunk_text(text: str, size: int = MAX_CHUNK_SIZE) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


# pydantic models for scale data structure
class Person(BaseModel):
    id: str
    name: str
    source_ids: List[int] = Field(..., description="IDs بلوک‌های منبع")


class Relation(BaseModel):
    from_id: str
    to_id: str
    type: str
    source_ids: List[int]


class FamilyTree(BaseModel):
    persons: List[Person]
    relations: List[Relation]
    other_data: Dict[str, str] = {}


@app.post("/upload_json")
async def upload_json(
        user_id: str = Form(...),
        category: str = Form(...),
        file: UploadFile = File(...)
):
    print("UPLOAD_JSON RECEIVED CATEGORY:", repr(category))
    content = await file.read()
    json_data = {}
    filename = file.filename.lower() if file.filename else ""
    try:
        if filename.endswith(".json"):
            json_data = json.loads(content.decode("utf-8", errors="ignore"))

        elif filename.endswith(".pdf"):
            print(f"📄 شروع پردازش PDF: {file.filename}")
            print(f"📦 حجم فایل: {len(content)} بایت")
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                tmp_pdf.write(content)
                pdf_path = tmp_pdf.name
            print(f"💾 فایل موقت ذخیره شد: {pdf_path}")

            context = ""
            context_blocks = []
            use_ocr = False

            # مرحله 1: استخراج متن با PyPDFLoader
            try:
                reader = PyPDFLoader(pdf_path)
                pages = reader.load()
                print(f"✅ تعداد صفحات: {len(pages)}")
                for page_num, page in enumerate(pages, 1):
                    page_text = page.page_content
                    cleaned_text = deep_clean_farsi_text(page_text)
                    if cleaned_text:
                        context += cleaned_text + "\n\n"
                        context_blocks.append({
                            "page": page_num,
                            "text": cleaned_text,
                            "char_count": len(cleaned_text)
                        })
                if len(context.strip()) < 50 or looks_garbled(context):
                    use_ocr = True
            except Exception as e:
                print(f"❌ خطا در PyPDFLoader: {str(e)}")
                use_ocr = True

            # مرحله 2: اگر نیاز به OCR بود، از PyMuPDF استفاده می‌کنیم
            if use_ocr:
                print("🔍 نیاز به OCR تشخیص داده شد...")
                try:
                    # تلاش با PyMuPDF اگر نصب باشد
                    try:
                        import fitz  # PyMuPDF
                        print("استفاده از PyMuPDF برای استخراج متن...")
                        doc = fitz.open(pdf_path)
                        for page_num in range(len(doc)):
                            page = doc.load_page(page_num)
                            text = page.get_text()
                            if text:
                                cleaned_text = deep_clean_farsi_text(text)
                                context += cleaned_text + "\n\n"
                                context_blocks.append({
                                    "page": page_num + 1,
                                    "text": cleaned_text,
                                    "char_count": len(cleaned_text),
                                    "method": "pymupdf"
                                })
                        doc.close()
                    except ImportError:
                        print("PyMuPDF نصب نیست، ادامه با متن استخراج شده...")
                except Exception as e:
                    print(f"❌ خطا در استخراج OCR: {str(e)}")
                    traceback.print_exc()

            # حذف فایل موقت
            try:
                os.unlink(pdf_path)
            except Exception as e:
                print(f"⚠️ خطا در حذف فایل موقت: {str(e)}")

            json_data = {
                "filename": file.filename,
                "category": category.strip().lower(),
                "extraction_method": "ocr" if use_ocr else "text",
                "total_characters": len(context),
                "total_blocks": len(context_blocks),
                "full_text": context,
                "blocks": context_blocks,
                "metadata": {
                    "processed_at": str(json.dumps(context_blocks, ensure_ascii=False)),
                    "file_size_bytes": len(content)
                }
            }

        elif filename.endswith(".txt"):
            detected = chardet.detect(content)
            encoding = detected.get("encoding") or "utf-8"
            raw_text = content.decode(encoding, errors="ignore")
            json_data = {"text": deep_clean_farsi_text(raw_text)}

        elif filename.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(content))
            full_text = "\n".join([para.text for para in doc.paragraphs])
            json_data = {"text": deep_clean_farsi_text(full_text)}

        else:
            return JSONResponse(
                status_code=400,
                content={"error": "Unsupported file type. Only JSON, PDF, TXT, DOCX."}
            )

        # ذخیره در Supabase
        related_data = []
        existing = supabase.table("ai_assist").select("*").eq("user_id", user_id).execute()
        if existing.data:
            supabase.table("ai_assist").update({
                "category": category,
                "data": json_data,
                "related_sources": related_data
            }).eq("user_id", user_id).execute()
        else:
            supabase.table("ai_assist").insert({
                "user_id": user_id,
                "category": category,
                "data": json_data,
                "related_sources": related_data
            }).execute()

        return {
            "message": f"File '{file.filename}' processed successfully ✅",
            "category": category,
            "file_type": filename.split('.')[-1],
            "extraction_summary": {
                "method": json_data.get("extraction_method", "unknown"),
                "total_characters": json_data.get("total_characters", 0),
                "total_blocks": json_data.get("total_blocks", 0)
            },
            "json_data_preview": json.dumps(json_data, ensure_ascii=False)[:500],
        }

    except Exception as e:
        print(f"ERROR in upload_json: {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Processing failed: {str(e)}"})


# asking method
@app.post("/ask")
async def ask(request: Request):
    body = await request.json()
    user_id = body.get("user_id")
    question = body.get("question")
    if not user_id or not question:
        return JSONResponse(status_code=400, content={"error": "user_id and question required."})

    # ✅ تغییر: گرفتن داده از Supabase
    result = supabase.table("ai_assist").select("*").eq("user_id", user_id).execute()
    if not result.data:
        return JSONResponse(status_code=400, content={"error": "No data for this user."})

    record = result.data[0]

    # ✅ محدود کردن داده‌ها برای جلوگیری از خطای token limit
    data_to_format = record["data"]

    # اگر full_text وجود دارد، آن را محدود کن
    if isinstance(data_to_format, dict) and "full_text" in data_to_format:
        data_to_format = data_to_format.copy()
        data_to_format["full_text"] = truncate_text(data_to_format["full_text"], max_chars=2000)

    # اگر blocks وجود دارد، تعداد آن‌ها را محدود کن
    if isinstance(data_to_format, dict) and "blocks" in data_to_format:
        data_to_format["blocks"] = data_to_format["blocks"][:5]  # فقط 5 بلوک اول

    formatted_data = json.dumps(data_to_format, ensure_ascii=False, indent=2)
    formatted_data = truncate_text(formatted_data, max_chars=3000)

    # محدود کردن منابع وب
    web_sources = ""
    if record.get("related_sources"):
        web_sources = "\n منابع مرتبط از وب:\n"
        for idx, source in enumerate(record["related_sources"][:3], 1):  # فقط 3 منبع اول
            web_sources += f"\n{idx}. {source.get('title', 'بدون عنوان')}\n"
            if source.get('text'):
                preview = truncate_text(source['text'], max_chars=300)
                web_sources += f" محتوا: {preview}\n"

    history = chat_memory.get(user_id, [])
    conversation_context = ""
    if history:
        # فقط 3 پیام آخر را نگه دار
        recent_history = history[-3:]
        conversation_context = "\n".join(
            [f"{msg['role']}: {truncate_text(msg['content'], max_chars=200)}" for msg in recent_history]
        )

    prompt = f"""
    تو یک دستیار هوشمند فارسی هستی که همیشه با دقت، منطق و لحن طبیعی پاسخ می‌دی. هدف تو اینه که کاربر حس کنه با یه متخصص صمیمی و باتجربه در حال گفت‌وگوئه.

    📂 دسته‌بندی: {record["category"]}
    📋 داده‌ها: {formatted_data}
    {web_sources}
    💬 حافظه گفتگو: {conversation_context}
    ❓ سؤال: {question}

    📘 دستورالعمل:
    1. ابتدا داده‌ها و منابع داخلی را بررسی کن
    2. اگر پاسخ پیدا کردی، به صورت خلاصه و شفاف توضیح بده
    3. در پایان منبع را ذکر کن
    4. اگر داده کافی نیست، از دانش کلی استفاده کن
    5. پاسخ را کوتاه و مفید بنویس (2 تا 5 جمله)

    پاسخ:
    """

    answer = await github_llm(prompt)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    chat_memory[user_id] = history[-MAX_MEMORY:]

    return {"answer": answer}


# endpoint برای دریافت JSON استخراج شده
@app.get("/get_extracted_data/{user_id}")
async def get_extracted_data(user_id: str):
    """ دریافت داده‌های JSON استخراج شده برای یک کاربر """
    print(f"\n🔍 درخواست دریافت داده برای user_id: {user_id}")
    try:
        result = supabase.table("ai_assist").select("*").eq("user_id", user_id).execute()
        if not result.data:
            print(f"❌ هیچ داده‌ای برای user_id={user_id} یافت نشد")
            return JSONResponse(
                status_code=404,
                content={"error": f"No data found for user_id: {user_id}"}
            )

        record = result.data[0]
        print(f"✅ داده یافت شد:")
        print(f" - Category: {record.get('category')}")
        print(f" - Data keys: {list(record.get('data', {}).keys())}")

        return {
            "user_id": user_id,
            "category": record.get("category"),
            "data": record.get("data"),
            "related_sources": record.get("related_sources", [])
        }
    except Exception as e:
        print(f"❌ خطا در دریافت داده: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to retrieve data: {str(e)}"}
        )


# if __name__ == "__main__":
#     uvicorn.run(
#         "main:app",
#         host="0.0.0.0",
#         port=8000,
#         timeout_keep_alive=120,
#         limit_concurrency=50,
#         limit_max_requests=500
#     )

# در انتهای main.py
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        timeout_keep_alive=120,
        log_level="info"
    )