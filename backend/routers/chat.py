from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from config import MAX_MEMORY
from db_config import AsyncSessionLocal
from models.tenant_data import TenantData
from services.llm_service import github_llm
from services.subscription_service import check_and_reset_subscription
from utils.helpers import ensure_json, truncate_text

router = APIRouter()

chat_memory = {}


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
            content={"error": "لطفا ابتدا اشتراک خود را انتخاب کنید"},
        )

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(TenantData).where(TenantData.user_id == user_id)
            )
            row = result.scalars().first()
        except Exception as e:
            print(f"❌ خطا در اجرای کوئری: {e}")
            return JSONResponse(status_code=500, content={"error": f"DB query failed: {str(e)}"})

    if not row:
        return JSONResponse(status_code=400, content={"error": "No data for this user."})

    data_to_format = ensure_json(row.data)
    related_sources = ensure_json(row.related_sources) or []

    if isinstance(data_to_format, dict) and "full_text" in data_to_format:
        data_to_format = data_to_format.copy()
        data_to_format["full_text"] = truncate_text(data_to_format["full_text"], max_chars=2000)

    if isinstance(data_to_format, dict) and "blocks" in data_to_format:
        data_to_format["blocks"] = data_to_format["blocks"][:5]

    formatted_data = str(data_to_format)[:3000]

    web_sources = ""
    if related_sources:
        web_sources = "\n منابع مرتبط از وب:\n"
        for idx, source in enumerate(related_sources[:3], 1):
            if not isinstance(source, dict):
                continue
            web_sources += f"\n{idx}. {source.get('title', 'بدون عنوان')}\n"
            if source.get("text"):
                preview = truncate_text(source["text"], max_chars=300)
                web_sources += f" محتوا: {preview}\n"

    history = chat_memory.get(user_id, [])
    conversation_context = ""
    if history:
        recent_history = history[-3:]
        conversation_context = "\n".join(
            [f"{msg['role']}: {truncate_text(msg['content'], max_chars=200)}" for msg in recent_history]
        )

    prompt = f"""
    تو یک دستیار هوشمند فارسی هستی که همیشه با دقت، منطق و لحن طبیعی پاسخ می‌دی. هدف تو اینه که کاربر حس کنه با یه متخصص صمیمی و باتجربه در حال گفت‌وگوئه.

    📂 دسته‌بندی: {row.category}
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

    try:
        answer = await github_llm(prompt)
    except Exception as e:
        print(f"❌ LLM error: {e}")
        return JSONResponse(status_code=502, content={"error": f"LLM request failed: {str(e)}"})

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    chat_memory[user_id] = history[-MAX_MEMORY:]

    return {"answer": answer}


@router.get("/get_extracted_data/{user_id}")
async def get_extracted_data(user_id: str):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TenantData).where(TenantData.user_id == user_id)
            )
            row = result.scalars().first()

        if not row:
            return JSONResponse(
                status_code=404,
                content={"error": f"No data found for user_id: {user_id}"},
            )

        return {
            "user_id": user_id,
            "category": row.category,
            "data": ensure_json(row.data),
            "related_sources": ensure_json(row.related_sources) or [],
        }
    except Exception as e:
        print(f"❌ خطا در دریافت داده: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to retrieve data: {str(e)}"},
        )
