from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from models.subscription_models import PLANS
from services.subscription_service import check_and_reset_subscription, create_or_update_subscription

router = APIRouter()


@router.post("/select_subscription")
async def select_subscription(request: Request):
    body = await request.json()
    user_id = body.get("user_id")
    plan_type = body.get("plan_type")

    if not user_id or not plan_type:
        return JSONResponse(status_code=400, content={"error": "user_id و plan_type الزامی هستند"})
    if plan_type not in PLANS:
        return JSONResponse(status_code=400, content={"error": "پلن انتخابی معتبر نیست"})

    success, message = await create_or_update_subscription(user_id, plan_type)
    if not success:
        return JSONResponse(status_code=400, content={"error": message})

    plan = PLANS[plan_type]
    return {
        "success": True,
        "message": message,
        "plan": {
            "type": plan_type,
            "name": plan.name,
            "price": plan.price,
            "max_pages": plan.max_pages,
            "description": plan.description,
        },
        "user_id": user_id,
    }


@router.get("/get_subscription/{user_id}")
async def get_subscription(user_id: str):
    subscription = await check_and_reset_subscription(user_id)

    if not subscription:
        return {
            "user_id": user_id,
            "has_subscription": False,
            "message": "هنوز اشتراکی انتخاب نکرده‌اید",
        }

    plan = PLANS.get(subscription.plan_type)
    plan_info = None
    limits = None
    if plan:
        plan_info = {
            "type": subscription.plan_type,
            "name": plan.name,
            "price": plan.price,
            "max_pages": plan.max_pages,
            "description": plan.description,
        }
        limits = {
            "max_pages_per_file": plan.max_pages,
            "description": f"حداکثر {plan.max_pages} صفحه در هر فایل",
        }

    last_reset = subscription.last_reset
    last_reset_str = last_reset.isoformat() if hasattr(last_reset, "isoformat") else str(last_reset)

    return {
        "user_id": user_id,
        "plan": plan_info,
        "subscription": {
            "plan_type": subscription.plan_type,
            "pages_remaining": subscription.pages_remaining,
            "last_reset": last_reset_str,
            "is_active": subscription.is_active,
        },
        "has_subscription": True,
        "limits": limits,
    }
