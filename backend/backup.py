import io
import re
import traceback
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os, json, httpx
import chardet
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
import uvicorn
from typing import List, Dict
from unstructured.partition.pdf import partition_pdf
import unicodedata
from hazm import Normalizer
from bs4 import BeautifulSoup
import random
import tempfile
from dotenv import load_dotenv

# ✅ تغییر: استفاده از Supabase به جای SQLAlchemy
from db_config import supabase

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
# ----------------------------
# FastAPI setup
# ----------------------------
app = FastAPI()

# ✅ تغییر: حذف startup event برای SQLAlchemy
# دیگر نیازی به create_all نیست، جدول را در Supabase ساختیم

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
FALLBACK_SOURCES = {
    "contract": [
        {"title": "قراردادهای هوشمند و بلاکچین در ایران", "url": "https://networkerbash.ir/قراردادهای-هوشمند-در-ایران/",
         "text": ""},
        {"title": "سرمایه گذاری ملکی شمال - اخبار شمال", "url": "https://www.shomalnews.com/", "text": ""},
        {"title": "قوانین قرارداد در قانون مدنی ایران", "url": "https://rc.majlis.ir/fa/law/show/99677", "text": ""},
        {"title": "فرصت‌های سرمایه‌گذاری در مازندران و گیلان", "url": "https://www.hamshahrionline.ir/tag/مازندران",
         "text": ""},
        {"title": "خرید و فروش ملک در شمال - دیوار", "url": "https://seeone.net/بلاگ/نکات-مهم-برای-خرید-ویلا-در-شمال/",
         "text": ""},
        {"title": "ویدیوهای سرمایه‌گذاری ملکی - آپارات",
         "url": "https://www.aparat.com/search/سرمایه%20گذاری%20ملکی%20شمال", "text": ""},
        {"title": "اخبار اقتصادی شمال کشور", "url": "https://www.isna.ir/tag/شمال", "text": ""},
        {"title": "قراردادهای هوشمند و بلاکچین در ایران", "url": "https://networkerbash.ir/قراردادهای-هوشمند-در-ایران/",
         "text": ""},
        {"title": "تورم مسکن در شمال ایران", "url": "https://www.eghtesadonline.com/tag/مسکن%20شمال", "text": ""},
        {"title": "راهنمای خرید ویلا در شمال", "url": "https://www.kojaro.com/pr/209705-buy-villa-north-pr/",
         "text": ""},
    ],
    "resume": [
        {"title": "نمونه رزومه فارسی", "url": "https://fa.wikipedia.org/wiki/رزومه", "text": ""},
        {"title": "ساخت رزومه آنلاین", "url": "https://www.jobinja.ir/resume-builder", "text": ""},
    ],
    "will": [
        {"title": "وصیت‌نامه در قانون ایران", "url": "https://rc.majlis.ir/fa/law/show/99677", "text": ""},
    ],
    "default": [
        {"title": "ویکی‌پدیا فارسی", "url": "https://fa.wikipedia.org", "text": ""},
        {"title": "خبرگزاری ایسنا", "url": "https://www.isna.ir", "text": ""},
        {"title": "دیوار ایران", "url": "https://divar.ir", "text": ""},
        {"title": "آپارات", "url": "https://www.aparat.com", "text": ""},
        {"title": "همشهری آنلاین", "url": "https://www.hamshahrionline.ir", "text": ""},
    ]
}


async def fetch_related_web_data(category: str, user_text: str) -> list:
    print("INFO: External search APIs blocked (sanctions). Using local fallback sources.")
    category_key = category.lower()
    sources_pool = FALLBACK_SOURCES.get(category_key, FALLBACK_SOURCES.get("default", []))
    if len(sources_pool) < 5:
        sources_pool += FALLBACK_SOURCES["default"]
    selected = random.sample(sources_pool, min(5, len(sources_pool)))
    print(
        f"DEBUG: Selected {len(selected)} fallback sources for category '{category}' from pool of {len(sources_pool)}")
    return selected


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


async def fetch_and_scrape_related(category: str, user_text: str) -> list:
    sources = await fetch_related_web_data(category, user_text)
    enriched_sources = []
    for src in sources:
        content = await scrape_web_content(src["url"])
        enriched_sources.append({
            "title": src["title"],
            "url": src["url"],
            "text": content
        })
    print(f"DEBUG: Completed scraping. Total enriched sources: {len(enriched_sources)}")
    if not enriched_sources:
        enriched_sources = [{
            "title": "منابع خارجی محدود (تحریم)",
            "url": "",
            "text": "به دلیل محدودیت‌های دسترسی، از داده‌های آپلود شده استفاده کنید. منابع وب scrape نشدند."
        }]
    return enriched_sources


# ----------------------------
# LLM
# ----------------------------
async def github_llm(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "stream": True
    }

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
        ) as response:

            if response.status_code != 200:
                raise Exception(f"OpenAI returned {response.status_code}")

            final_text = ""

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue

                raw = line.replace("data:", "").strip()

                if raw == "[DONE]":
                    break

                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                if not delta:
                    continue

                content = delta.get("content", "")
                if content:
                    final_text += content

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

            # مرحله 1: تلاش برای استخراج متن با PyPDFLoader
            print("\n🔍 مرحله 1: استخراج متن با PyPDFLoader...")
            context = ""
            context_blocks = []
            use_ocr = False

            try:
                reader = PyPDFLoader(pdf_path)
                pages = reader.load()
                print(f"✅ تعداد صفحات: {len(pages)}")

                for page_num, page in enumerate(pages, 1):
                    page_text = page.page_content
                    cleaned_text = deep_clean_farsi_text(page_text)

                    if cleaned_text:
                        print(f"   📖 صفحه {page_num}: {len(cleaned_text)} کاراکتر استخراج شد")
                        print(f"   📝 پیش‌نمایش: {cleaned_text[:100]}...")
                        context += cleaned_text + "\n\n"
                        context_blocks.append({
                            "page": page_num,
                            "text": cleaned_text,
                            "char_count": len(cleaned_text)
                        })
                    else:
                        print(f"   ⚠️  صفحه {page_num}: متن قابل استخراجی یافت نشد")

                # بررسی کیفیت متن استخراج شده
                if looks_garbled(context):
                    print("⚠️  متن فارسی نامفهوم تشخیص داده شد، سوئیچ به OCR...")
                    use_ocr = True
                elif len(context.strip()) < 50:
                    print(f"⚠️  متن استخراج شده خیلی کوتاه است ({len(context.strip())} کاراکتر)، سوئیچ به OCR...")
                    use_ocr = True
                else:
                    print(f"✅ استخراج متن موفق: کل {len(context)} کاراکتر")

            except Exception as e:
                print(f"❌ خطا در PyPDFLoader: {str(e)}")
                print(f"   سوئیچ به OCR...")
                use_ocr = True

            # مرحله 2: در صورت نیاز، استفاده از OCR
            if use_ocr:
                print("\n🔍 مرحله 2: استخراج متن با OCR (partition_pdf)...")
                try:
                    elements = partition_pdf(pdf_path, strategy="hi_res", languages=["fas"])
                    print(f"✅ تعداد المان‌های استخراج شده: {len(elements)}")

                    context_blocks = []
                    full_text = []

                    for i, el in enumerate(elements):
                        text = deep_clean_farsi_text(el.text) if hasattr(el, 'text') else ""
                        if text:
                            block = {
                                "id": i,
                                "type": el.category if hasattr(el, 'category') else "unknown",
                                "text": text,
                                "char_count": len(text)
                            }

                            if hasattr(el, 'bbox'):
                                block["bbox"] = el.bbox

                            print(f"   📦 بلوک {i} ({block['type']}): {len(text)} کاراکتر")
                            print(f"      {text[:80]}...")

                            context_blocks.append(block)
                            full_text.append(text)

                    context = "\n\n".join(full_text)
                    print(f"✅ استخراج OCR موفق: کل {len(context)} کاراکتر از {len(context_blocks)} بلوک")

                except Exception as e:
                    print(f"❌ خطا در OCR: {str(e)}")
                    traceback.print_exc()
                    raise Exception(f"استخراج متن ناموفق: {str(e)}")

            # پاک‌سازی فایل موقت
            try:
                os.unlink(pdf_path)
                print(f"🗑️  فایل موقت حذف شد")
            except Exception as e:
                print(f"⚠️  خطا در حذف فایل موقت: {str(e)}")

            # آماده‌سازی JSON نهایی
            print("\n📊 آماده‌سازی JSON نهایی...")
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

            print(f"✅ JSON ساخته شد:")
            print(f"   - روش استخراج: {json_data['extraction_method']}")
            print(f"   - تعداد کاراکتر: {json_data['total_characters']}")
            print(f"   - تعداد بلوک: {json_data['total_blocks']}")
            print(f"   - پیش‌نمایش متن کامل:\n{context[:500]}...")


        elif filename.endswith(".txt"):
            detected = chardet.detect(content)
            encoding = detected.get("encoding") or "utf-8"
            raw_text = content.decode(encoding, errors="ignore")
            json_data = {"text": deep_clean_farsi_text(raw_text)}

        elif filename.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(content))
            full_text = "\n".join([para.text for para in doc.paragraphs])
            cleaned = deep_clean_farsi_text(full_text)
            json_data = {"text": cleaned}

        else:
            return JSONResponse(
                status_code=400,
                content={"error": "Unsupported file type. Only JSON, PDF, TXT."}
            )

        # ✅ ذخیره در Supabase
        print(f"\n💾 شروع ذخیره‌سازی در Supabase...")
        print(f"   - User ID: {user_id}")
        print(f"   - Category: {category}")
        print(f"   - حجم JSON: {len(json.dumps(json_data, ensure_ascii=False))} کاراکتر")

        # اگر نیاز به منابع وب هست (فعلاً غیرفعال می‌کنیم)
        related_data = []
        # text_data = json.dumps(json_data, ensure_ascii=False)
        # related_data = await fetch_and_scrape_related(category, text_data)

        existing = supabase.table("ai_assist").select("*").eq("user_id", user_id).execute()
        print(f"   - بررسی رکورد موجود: {'یافت شد' if existing.data else 'یافت نشد'}")

        if existing.data:
            print(f"   - به‌روزرسانی رکورد موجود...")
            result = supabase.table("ai_assist").update({
                "category": category,
                "data": json_data,
                "related_sources": related_data
            }).eq("user_id", user_id).execute()
            print(f"   ✅ رکورد به‌روزرسانی شد")
        else:
            print(f"   - ساخت رکورد جدید...")
            result = supabase.table("ai_assist").insert({
                "user_id": user_id,
                "category": category,
                "data": json_data,
                "related_sources": related_data
            }).execute()
            print(f"   ✅ رکورد جدید ساخته شد")

        print(f"✅ ذخیره‌سازی در Supabase موفق")
        print(f"\n📋 خلاصه پردازش:")
        print(f"   - نام فایل: {file.filename}")
        print(f"   - نوع فایل: {filename.split('.')[-1]}")
        print(f"   - دسته‌بندی: {category}")
        print(f"   - تعداد کاراکتر استخراج شده: {json_data.get('total_characters', len(str(json_data)))}")

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
    formatted_data = json.dumps(record["data"], ensure_ascii=False, indent=2)

    web_sources = ""
    if record.get("related_sources"):
        web_sources = "\n منابع مرتبط از وب:\n"
        for idx, source in enumerate(record["related_sources"][:5], 1):
            web_sources += f"\n{idx}. {source.get('title', 'بدون عنوان')}\n"
            if source.get('text'):
                preview = source['text'][:500] + "..." if len(source['text']) > 500 else source['text']
                web_sources += f" محتوا: {preview}\n"

    history = chat_memory.get(user_id, [])

    conversation_context = ""
    if history:
        conversation_context = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in history]
        )

    prompt = f"""
    تو یک دستیار هوشمند فارسی هستی که همیشه با دقت، منطق و لحن طبیعی پاسخ می‌دی.
    هدف تو اینه که کاربر حس کنه با یه متخصص صمیمی و باتجربه در حال گفت‌وگوئه.

    📂 دسته‌بندی: {record["category"]}
    📋 داده‌ها:
    {formatted_data}
    {web_sources}

    💬 حافظه گفتگو تا این لحظه:
    {conversation_context}

    ❓ سؤال جدید کاربر:
    {question}

    📘 دستورالعمل پاسخ‌گویی:

    1. **مرحله اول — جستجو در داده‌ها**
       - ابتدا اطلاعات JSON و منابع وب داخلی رو بررسی کن.
       - روابط بین داده‌ها و اشخاص رو تحلیل کن.
       - اگر پاسخ مستقیم پیدا کردی، فقط بر اساس همون توضیح بده.
       - در پایان بنویس: «منبع: داده‌های فایل» یا «منبع: وب داخلی».

    2. **مرحله دوم — در صورت نبود پاسخ صریح**
       - اگر داده‌ها پاسخ دقیقی ندادن، از دانش کلی یا جستجوی وب استفاده کن.
       - پاسخ رو خلاصه، شفاف و حرفه‌ای بنویس (حدود ۲ تا ۵ جمله).
       - پاسخ رو با عبارت «🔍 رفتم سرچ کردم و پیدا کردم که...» شروع کن.
       - در انتها منبع وب رو ذکر کن.

    3. **نکات لحن و بیان**
       - محترمانه، طبیعی و صمیمی بنویس.
       -حالا پاسخ بده:
"""

    answer = await github_llm(prompt)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    chat_memory[user_id] = history[-MAX_MEMORY:]

    return {"answer": answer}


# endpoint برای دریافت JSON استخراج شده
@app.get("/get_extracted_data/{user_id}")
async def get_extracted_data(user_id: str):
    """
    دریافت داده‌های JSON استخراج شده برای یک کاربر
    """
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
        print(f"   - Category: {record.get('category')}")
        print(f"   - Data keys: {list(record.get('data', {}).keys())}")

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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        timeout_keep_alive=120,
        limit_concurrency=50,
        limit_max_requests=500
    )