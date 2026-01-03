from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from services.llm_service import github_llm
from services.subscribtion_service import check_and_reset_subscription
from utils.helpers import truncate_text
from db_config import AsyncSessionLocal
from sqlalchemy import text
import json
from sqlalchemy import text
import json

router = APIRouter()

# حافظه چت (می‌توانید آن را در یک دیتابیس ذخیره کنید)
chat_memory = {}
MAX_MEMORY = 5

@router.post("/ask")
async def ask(request: Request):

    body = await request.json()
    user_id = body.get("user_id")
    question = body.get("question")
    if not user_id or not question:
        return JSONResponse(status_code=400, content={"error": "user_id and question required."})
    
    subscription = await check_and_reset_subscription(user_id)
    if not subscription:
        return JSONResponse(
            status_code=402,
            content={"error": "لطفا ابتدا اشتراک خود را انتخاب کنید"}
        )

    # ✅ گرفتن داده از PostgreSQL با استفاده از AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        try:
            q = text("SELECT * FROM ai_assist WHERE user_id = :user_id LIMIT 1")
            result = await session.execute(q, {"user_id": user_id})
            row = result.fetchone()
        except Exception as e:
            print(f"❌ خطا در اجرای کوئری: {e}")
            return JSONResponse(status_code=500, content={"error": f"DB query failed: {str(e)}"})

    if not row:
        return JSONResponse(status_code=400, content={"error": "No data for this user."})

    # row._mapping را به dict تبدیل می‌کنیم تا دسترسی راحت‌تر شود
    record = dict(row._mapping)

    # اگر ستون‌های JSON به صورت متن آمده بودند، آن‌ها را تبدیل کن
    def ensure_json(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return v
        return v

    record["data"] = ensure_json(record.get("data"))
    record["related_sources"] = ensure_json(record.get("related_sources"))

    # ✅ محدود کردن داده‌ها برای جلوگیری از خطای token limit
    data_to_format = record.get("data")

    # اگر full_text وجود دارد، آن را محدود کن
    if isinstance(data_to_format, dict) and "full_text" in data_to_format:
        data_to_format = data_to_format.copy()
        data_to_format["full_text"] = truncate_text(data_to_format["full_text"], max_chars=2000)

    # اگر blocks وجود دارد، تعداد آن‌ها را محدود کن
    if isinstance(data_to_format, dict) and "blocks" in data_to_format:
        data_to_format["blocks"] = data_to_format["blocks"][:5]  # فقط 5 بلوک اول

    formatted_data = str(data_to_format)[:3000]

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

    📂 دسته‌بندی: {record.get("category")}
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

@router.get("/get_extracted_data/{user_id}")
async def get_extracted_data(user_id: str):
    """ دریافت داده‌های JSON استخراج شده برای یک کاربر """

    print(f"\n🔍 درخواست دریافت داده برای user_id: {user_id}")
    try:
        async with AsyncSessionLocal() as session:
            q = text("SELECT * FROM ai_assist WHERE user_id = :user_id LIMIT 1")
            result = await session.execute(q, {"user_id": user_id})
            row = result.fetchone()

        if not row:
            print(f"❌ هیچ داده‌ای برای user_id={user_id} یافت نشد")
            return JSONResponse(
                status_code=404,
                content={"error": f"No data found for user_id: {user_id}"}
            )

        record = dict(row._mapping)

        # اگر داده‌ها به صورت JSON رشته‌ای بودند، آن‌ها را بارگذاری کن
        def ensure_json(v):
            if isinstance(v, str):
                try:
                    return json.loads(v)
                except Exception:
                    return v
            return v

        record["data"] = ensure_json(record.get("data"))
        record["related_sources"] = ensure_json(record.get("related_sources", []))

        print(f"✅ داده یافت شد:")
        print(f" - Category: {record.get('category')}")
        try:
            print(f" - Data keys: {list(record.get('data', {}).keys())}")
        except Exception:
            print(" - Data is not a dict")

        return {
            "user_id": user_id,
            "category": record.get("category"),
            "data": record.get("data"),
            "related_sources": record.get("related_sources", [])
        }
    except Exception as e:
        print(f"❌ خطا در دریافت داده: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to retrieve data: {str(e)}"}
        )