from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from db_config import supabase

router = APIRouter()

@router.post("/select_category")
async def select_category(request: Request):
    body = await request.json()
    user_id = body.get("user_id")
    category = body.get("category")
    print("Raw category receive from front ", repr(category))
    
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