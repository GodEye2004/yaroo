from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from services.llm_service import github_llm
from services.subscribtion_service import check_and_reset_subscription
from utils.helpers import truncate_text
from db_config import supabase

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

@router.get("/get_extracted_data/{user_id}")
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