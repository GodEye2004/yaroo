from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from services.subscribtion_service import (
    check_and_reset_subscription, 
    create_or_update_subscription
)
from models.subscribtion_models import PLANS

router = APIRouter()

@router.post("/select_subscription")
async def select_subscription(request: Request):
    """انتخاب یا خرید اشتراک توسط کاربر"""
    body = await request.json()
    user_id = body.get("user_id")
    plan_type = body.get("plan_type")
    
    if not user_id or not plan_type:
        return JSONResponse(
            status_code=400,
            content={"error": "user_id و plan_type الزامی هستند"}
        )
    
    if plan_type not in PLANS:
        return JSONResponse(
            status_code=400,
            content={"error": "پلن انتخابی معتبر نیست"}
        )
    
    success, message = await create_or_update_subscription(user_id, plan_type)
    
    if success:
        return {
            "success": True,
            "message": message,
            "plan": PLANS[plan_type].dict(),
            "user_id": user_id
        }
    else:
        return JSONResponse(
            status_code=400,
            content={"error": message}
        )

@router.get("/get_subscription/{user_id}")
async def get_subscription(user_id: str):
    """دریافت وضعیت اشتراک کاربر"""
    subscription = await check_and_reset_subscription(user_id)
    
    if subscription:
        plan = PLANS.get(subscription.plan_type)
        return {
            "user_id": user_id,
            "plan": plan.dict() if plan else None,
            "subscription": subscription.dict(),
            "has_subscription": True
        }
    else:
        return {
            "user_id": user_id,
            "has_subscription": False,
            "message": "هنوز اشتراکی انتخاب نکرده‌اید"
        }