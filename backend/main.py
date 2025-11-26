import io
import re
import traceback
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os, json, httpx
import chardet
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.future import select
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
# from langchain_core.pydantic_v1 import BaseModel
from langchain_core.output_parsers import JsonOutputParser

from typing import List, Dict
from unstructured.partition.pdf import partition_pdf
import unicodedata
from hazm import Normalizer
from db_config import get_db
from models import TenatData
from bs4 import BeautifulSoup
import random
import tempfile
from models import Base  # your declarative base
from db_config import engine  # your async engine


api_key = os.getenv("OPENAI_API_KEY")
# ----------------------------
# FastAPI setup
# ----------------------------
app = FastAPI()

# @app.on_event("startup")
# async def startup_event():
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)
#     print("Database tables are ready!")


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
        {"title": "قراردادهای هوشمند و بلاکچین در ایران", "url": "https://networkerbash.ir/قراردادهای-هوشمند-در-ایران/", "text": ""},
        {"title": "سرمایه گذاری ملکی شمال - اخبار شمال", "url": "https://www.shomalnews.com/", "text": ""},
        {"title": "قوانین قرارداد در قانون مدنی ایران", "url": "https://rc.majlis.ir/fa/law/show/99677", "text": ""},
        {"title": "فرصت‌های سرمایه‌گذاری در مازندران و گیلان", "url": "https://www.hamshahrionline.ir/tag/مازندران", "text": ""},
        {"title": "خرید و فروش ملک در شمال - دیوار", "url": "https://seeone.net/بلاگ/نکات-مهم-برای-خرید-ویلا-در-شمال/", "text": ""},
        {"title": "ویدیوهای سرمایه‌گذاری ملکی - آپارات", "url": "https://www.aparat.com/search/سرمایه%20گذاری%20ملکی%20شمال", "text": ""},
        {"title": "اخبار اقتصادی شمال کشور", "url": "https://www.isna.ir/tag/شمال", "text": ""},
        {"title": "قراردادهای هوشمند و بلاکچین در ایران", "url": "https://networkerbash.ir/قراردادهای-هوشمند-در-ایران/", "text": ""},
        {"title": "تورم مسکن در شمال ایران", "url": "https://www.eghtesadonline.com/tag/مسکن%20شمال", "text": ""},
        {"title": "راهنمای خرید ویلا در شمال", "url": "https://www.kojaro.com/pr/209705-buy-villa-north-pr/", "text": ""},
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
    print(f"DEBUG: Selected {len(selected)} fallback sources for category '{category}' from pool of {len(sources_pool)}")
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
# async def github_llm(prompt: str) -> str:
#     headers = {
#         "Authorization": f"Bearer {GITHUB_TOKEN}",
#         "Content-Type": "application/json"
#     }
#
#     payload = {
#         "model": "openai/gpt-4o-mini",
#         "messages": [
#             {"role": "user", "content": prompt}
#         ],
#         "temperature": 0.3,
#         "stream": True
#     }
#
#     async with httpx.AsyncClient(timeout=None) as client:
#         async with client.stream(
#             "POST",
#             "https://models.github.ai/inference/chat/completions",
#             headers=headers,
#             json=payload
#         ) as response:
#
#             if response.status_code != 200:
#                 raise Exception(f"GitHub returned {response.status_code}")
#
#             final_text = ""
#
#             async for line in response.aiter_lines():
#                 if not line or not line.startswith("data:"):
#                     continue
#
#                 raw = line.replace("data:", "").strip()
#
#                 if raw == "[DONE]":
#                     break
#
#                 # اگر JSON نبود ردش کن
#                 try:
#                     data = json.loads(raw)
#                 except Exception:
#                     continue
#
#                 # اگر choices خالی بود، رد کن
#                 choices = data.get("choices", [])
#                 if not choices:
#                     continue
#
#                 # delta شاید خالی باشد
#                 delta = choices[0].get("delta", {})
#                 if not delta:
#                     continue
#
#                 # content یا empty
#                 content = delta.get("content", "")
#                 if content:
#                     final_text += content
#
#             return final_text.strip()

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
# You can add a generic model for default
}

# select categories
@app.post("/select_category")
async def select_category(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    user_id = body.get("user_id")
    category = body.get("category")

    print("Raw category recive from front ", repr(category))
    if not user_id or not category:
        return JSONResponse(status_code=400, content={"error": "user_id and category are required"})
    existing = await db.execute(select(TenatData).where(TenatData.user_id == user_id))
    record = existing.scalars().first()
    if record:
        record.category = category
    else:
        record = TenatData(user_id=user_id, category=category, data={})
    db.add(record)
    await db.commit()
    return {"message": f"Category '{category}' activated."}


# normalize persian text
def deep_clean_farsi_text(text: str) -> str:
    if not text:
        return ""
    # Unicode normalization
    text = unicodedata.normalize("NFKC", text)
    # Correction of Arabic/Persian characters
    text = text.replace("ي", "ی").replace("ك", "ک")
    # Remove noise and hidden gaps
    text = text.replace("‌", " ").replace("\u200c", " ")
    # Normalize grammar and spacing with hazm
    text = normalizer.normalize(text)
    return text.strip()

def looks_garbled(text: str) -> bool:
    bad_patterns = [
        r"[اآبپتثجچحخدذرزسشصضطظعغفقکگلمنوهی]{1,2}\s[اآبپتثجچحخدذرزسشصضطظعغفقکگلمنوهی]{1,2}",
        r"[ﮐﻟﻣﻧﻫﻳﺍﺏﺕﺩﺭﺯﺱﺵﺹﺿﻁﻅﻉﻍﻑﻕﻙﻙﻝﻡﻥﻩﻱ]",  # Defective Arabic glyphs
    ]
    for pattern in bad_patterns:
        if re.search(pattern, text):
            return True
    return False

def chunk_text(text: str, size: int = MAX_CHUNK_SIZE) -> list[str]:

    return [text[i:i + size] for i in range(0, len(text), size)]


# pydantic models for scale data structure => like a graph mode?????
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
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    print("UPLOAD_JSON RECEIVED CATEGORY:", repr(category))
    content = await file.read()
    json_data = {}
    filename = file.filename.lower() if file.filename else ""

    try:
        if filename.endswith(".json"):
            json_data = json.loads(content.decode("utf-8", errors="ignore"))

        elif filename.endswith(".pdf"):
            # save temporary pdf
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                tmp_pdf.write(content)
                pdf_path = tmp_pdf.name

            # --- phase1: try to extract with PyPDFLoader/PyPDF2 ---
            try:
                reader = PyPDFLoader(pdf_path)
                pages = [page.extract_text() for page in reader.pages]
                context_lines = [deep_clean_farsi_text(p) for p in pages if p]
                context = "\n".join(context_lines)
                if looks_garbled(context):
                    print("Detected garbled Persian text, switching to OCR...")
                    elements = partition_pdf(pdf_path, strategy="hi_res", languages=["fas"])
            except Exception:
                context = ""
                elements = partition_pdf(pdf_path, strategy="hi_res", languages=["fas"])

            # --- phase2: if text insufficient, OCR ---
            if not context or len(context.strip()) < 50:
                print("Falling back to OCR extraction...")
                elements = partition_pdf(pdf_path, strategy="hi_res", languages=["fas"])

            # --- phase3: build structured blocks ---
            context_blocks = []
            for i, el in enumerate(elements):
                text = deep_clean_farsi_text(el.text)
                if text:
                    block = {"id": i, "text": text}
                    if hasattr(el, 'bbox'):
                        block["bbox"] = el.bbox

                    if el.category == "Image" and hasattr(el, 'image_path'):
                        try:
                            import easyocr
                            ocr_reader = easyocr.Reader(['fa'])
                            ocr_text = ocr_reader.readtext(el.image_path)
                            block["ocr_text"] = [result[1] for result in ocr_text]
                        except Exception as ocr_err:
                            print(f"OCR error on image: {ocr_err}")
                            block["ocr_text"] = []
                    context_blocks.append(block)

            context_json = json.dumps(context_blocks, ensure_ascii=False)

            # Delete temporary file
            os.unlink(pdf_path)

            # --- phase4: run LLM ---
            # normalize the category
            # Normalize category
            category = category.strip().lower()
            print("UPLOAD_JSON RECEIVED CATEGORY (normalized):", repr(category))

            if category not in CATEGORY_MODELS:
                raise ValueError(f"Unknown category: {category}")

            # Get the Pydantic model and parser
            pydantic_model = CATEGORY_MODELS[category]
            parser = JsonOutputParser(pydantic_object=pydantic_model)

            contract_prompt = PromptTemplate(
                template=(
                    "از متن ساختاری PDF زیر، تمام اطلاعات صریح مربوط به قرارداد را استخراج کن.\n"
                    "هدف، استخراج داده‌های اصلی قرارداد است — نه صرفاً روابط اشخاص.\n\n"
                    "📋 بخش‌های مورد انتظار در خروجی:\n"
                    "1. general_info: شامل عنوان، نوع قرارداد، موضوع، تاریخ، محل، مدت، مبلغ یا تعهدات مالی، و سایر جزئیات عمومی.\n"
                    "2. parties: شامل فهرست طرفین قرارداد با نام کامل، سمت (مثلاً کارفرما، سرمایه‌پذیر، شریک)، و اطلاعات تماس در صورت وجود.\n"
                    "3. persons (اختیاری): اگر در متن به اشخاص دیگر اشاره شده، آن‌ها را با id و نام بیاور.\n"
                    "4. relations (اختیاری): روابط بین اشخاص (مثل پدر، همکار، مدیرعامل) در صورت ذکر صریح.\n"
                    "5. clauses: بندها یا مفاد قرارداد که شامل حقوق، تعهدات، فسخ، ضمانت و سایر شروط هستند.\n"
                    "6. signatures (اختیاری): امضاها، تاریخ امضا، یا اشاره به گواهینامه‌ها.\n\n"
                    "📌 قوانین:\n"
                    "- فقط از اطلاعات صریح استفاده کن.\n"
                    "- اگر موردی وجود ندارد، مقدارش را null یا آرایه خالی بگذار.\n"
                    "- ساختار خروجی باید دقیقاً JSON معتبر باشد.\n\n"
                    "📘 مثال خروجی:\n"
                    "{{\n"
                    '  "general_info": {{ "title": "قرارداد سرمایه‌گذاری", "subject": "تأسیس شرکت نرم‌افزاری", "date": "1402/03/01", "place": "تهران" }},\n'
                    '  "parties": [ {{ "id": "p1", "name": "شرکت الف", "role": "سرمایه‌پذیر" }}, {{ "id": "p2", "name": "علی رضایی", "role": "سرمایه‌گذار" }} ],\n'
                    '  "persons": [ {{ "id": "p3", "name": "حافظ آشوری", "source_ids":[3] }} ],\n'
                    '  "relations": [ {{ "from": "p3", "to": "p2", "type": "همکار" }} ],\n'
                    '  "clauses": [ {{ "id": "c1", "text": "سرمایه‌گذار متعهد می‌شود مبلغ ۵۰۰ میلیون تومان پرداخت نماید." }} ],\n'
                    '  "signatures": [ {{ "party_id": "p1", "date": "1402/03/02" }} ]\n'
                    "}}\n\n"
                    "{format_instructions}\n\n"
                    "متن ساختاری PDF:\n{context}"
                ),
                input_variables=["context"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )

            relations_prompt = PromptTemplate(
                template=(
                    "از متن ساختاری PDF زیر، فقط اطلاعات صریح مربوط به اشخاص و روابط آن‌ها را استخراج کن.\n"
                    "اگر در متن اشاره‌ای به نسبت خانوادگی یا شغلی وجود دارد، آن را به‌صورت دقیق بیاور.\n\n"
                    "📋 ساختار خروجی JSON:\n"
                    "{{\n"
                    '  "persons": [ {{ "id":"p1","name":"نام شخص","source_ids":[1] }}, ... ],\n'
                    '  "relations": [ {{ "from_id":"p1", "to_id":"p2", "type":"پدر", "source_ids":[1] }} , ... ]\n'
                    "}}\n\n"
                    "📌 قوانین:\n"
                    "- فقط روابط صریح، نه استنباطی.\n"
                    "- اگر رابطه‌ای وجود ندارد، آرایه relations خالی باشد.\n\n"
                    "{format_instructions}\n\n"
                    "متن ساختاری PDF:\n{context}"
                ),
                input_variables=["context"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )

            # --- run LLM for contract ---
            contract_text = contract_prompt.format(context=context_json)
            # contract_response = await github_llm(contract_text)
            contract_response = await github_llm(contract_prompt.format(context=context_json))
            print("LLM RESPONSE:", contract_response[:1000])  # preview first 1000 chars
            contract_data = parser.parse(contract_response)

            # --- run LLM for relations ---
            relations_text = relations_prompt.format(context=context_json)
            relations_response = await github_llm(relations_text)
            relations_data = parser.parse(relations_response)

            # --- merge contract + relations ---
            merged_data = contract_data.copy()
            merged_data["persons"] = relations_data.get("persons", [])
            merged_data["relations"] = relations_data.get("relations", [])

            json_data = merged_data
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

        # --- save in DB ---
        existing = await db.execute(select(TenatData).where(TenatData.user_id == user_id))
        record = existing.scalars().first()
        if record:
            record.category = category
            record.data = json_data
        else:
            record = TenatData(user_id=user_id, category=category, data=json_data)
        db.add(record)

        # --- WebScraping ---
        print(f"INFO: Starting web scrape for category='{category}'")
        text_data = json.dumps(json_data, ensure_ascii=False)
        related_data = await fetch_and_scrape_related(category, text_data)
        record.related_sources = related_data

        await db.commit()
        print(f"SUCCESS: Saved to DB with {len(related_data)} sources")

        return {
            "message": f"File '{filename}' processed successfully with LangChain",
            "category": category,
            "file_type": filename.split('.')[-1],
            "json_data_preview": json.dumps(json_data, ensure_ascii=False)[:500],
        }

    except Exception as e:
        print(f"ERROR in upload_json: {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Processing failed: {str(e)}"})


# asking method
@app.post("/ask")
async def ask(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    user_id = body.get("user_id")
    question = body.get("question")

    if not user_id or not question:
        return JSONResponse(status_code=400, content={"error": "user_id and question required."})

    # --- مرحله ۱: دریافت داده کاربر ---
    result = await db.execute(select(TenatData).where(TenatData.user_id == user_id))
    record = result.scalars().first()
    if not record or not record.data:
        return JSONResponse(status_code=400, content={"error": "No data for this user."})

    formatted_data = json.dumps(record.data, ensure_ascii=False, indent=2)

    web_sources = ""
    if record.related_sources:
        web_sources = "\n منابع مرتبط از وب:\n"
        for idx, source in enumerate(record.related_sources[:5], 1):
            web_sources += f"\n{idx}. {source.get('title', 'بدون عنوان')}\n"
            if source.get('text'):
                preview = source['text'][:500] + "..." if len(source['text']) > 500 else source['text']
                web_sources += f" محتوا: {preview}\n"

    # --- مرحله ۲: آماده‌سازی حافظه گفتگو ---
    # گرفتن تاریخچه‌ی مکالمه‌ی قبلی (در صورت وجود)
    history = chat_memory.get(user_id, [])

    # ساخت prompt ترکیبی با حافظه
    conversation_context = ""
    if history:
        conversation_context = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in history]
        )

    # --- مرحله ۳: ساخت prompt نهایی ---
    prompt = f"""
    تو یک دستیار هوشمند فارسی هستی که همیشه با دقت، منطق و لحن طبیعی پاسخ می‌دی.  
    هدف تو اینه که کاربر حس کنه با یه متخصص صمیمی و باتجربه در حال گفت‌وگوئه.

    📂 دسته‌بندی: {record.category}
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
       - از توضیح اضافه یا تکرار پرهیز کن.  
       - هدف اینه که پاسخ تو دقیق، خوش‌خوان و اعتماد‌برانگیز باشه.

    حالا پاسخ بده:
    """

    # --- مرحله ۴: گرفتن پاسخ از LLM ---
    answer = await github_llm(prompt)

    # --- مرحله ۵: به‌روزرسانی حافظه ---
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})

    # محدود کردن طول حافظه
    chat_memory[user_id] = history[-MAX_MEMORY:]

    return {"answer": answer}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("test:app", host="0.0.0.0", port=port, reload=True)