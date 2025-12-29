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
        plan = PLANS[plan_type]
        return {
            "success": True,
            "message": message,
            "plan": {
                "type": plan_type,
                "name": plan.name,
                "price": plan.price,
                "max_pages": plan.max_pages,
                "description": plan.description
            },
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
        
        # تعیین محدودیت‌ها برای نمایش
        if plan:
            plan_info = {
                "type": subscription.plan_type,
                "name": plan.name,
                "price": plan.price,
                "max_pages": plan.max_pages,
                "description": plan.description
            }
            
            # برای کاربران رایگان، همیشه 0 صفحه باقیمانده نشان می‌دهیم
            pages_remaining = subscription.pages_remaining if subscription.plan_type != "free" else 5
            
            return {
                "user_id": user_id,
                "plan": plan_info,
                "subscription": {
                    "plan_type": subscription.plan_type,
                    "pages_remaining": pages_remaining,
                    "last_reset": subscription.last_reset.isoformat() if hasattr(subscription.last_reset, 'isoformat') else str(subscription.last_reset),
                    "is_active": subscription.is_active
                },
                "has_subscription": True,
                "limits": {
                    "max_pages_per_file": plan.max_pages,
                    "description": f"حداکثر {plan.max_pages} صفحه در هر فایل"
                }
            }
    
    return {
        "user_id": user_id,
        "has_subscription": False,
        "message": "هنوز اشتراکی انتخاب نکرده‌اید"
    }