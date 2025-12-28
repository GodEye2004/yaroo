from typing import Optional
from datetime import datetime, timezone, timedelta
from models.subscribtion_models import UserSubscription, PLANS
from db_config import supabase
import traceback

async def get_user_subscription(user_id: str) -> Optional[UserSubscription]:
    """دریافت اشتراک کاربر"""
    try:
        result = supabase.table("subscriptions").select("*").eq("user_id", user_id).execute()
        if result.data:
            data = result.data[0]
            
            # تبدیل last_reset به datetime
            if isinstance(data.get('last_reset'), str):
                try:
                    last_reset_str = data['last_reset']
                    if last_reset_str.endswith('Z'):
                        last_reset_str = last_reset_str[:-1] + '+00:00'
                    data['last_reset'] = datetime.fromisoformat(last_reset_str)
                except Exception as e:
                    print(f"Error parsing last_reset: {e}")
                    data['last_reset'] = datetime.now(timezone.utc)
            
            return UserSubscription(**data)
        return None
    except Exception as e:
        print(f"Error getting subscription: {e}")
        return None

async def check_and_reset_subscription(user_id: str):
    """بررسی و بازنشانی اشتراک در صورت نیاز (ماهانه)"""
    try:
        subscription = await get_user_subscription(user_id)
        if not subscription:
            return None

        # بررسی آیا نیاز به بازنشانی ماهانه است
        last_reset = subscription.last_reset
        
        # اطمینان از اینکه last_reset offset-aware باشد
        if last_reset.tzinfo is None:
            last_reset = last_reset.replace(tzinfo=timezone.utc)
        
        # now را نیز offset-aware بساز
        now = datetime.now(timezone.utc)
        
        # اگر از آخرین بازنشانی بیش از 30 روز گذشته باشد
        if (now - last_reset).days >= 30:
            plan = PLANS.get(subscription.plan_type)
            if plan:
                supabase.table("subscriptions").update({
                    "pages_remaining": plan.pages,
                    "last_reset": now.isoformat()
                }).eq("user_id", user_id).execute()
                
                return UserSubscription(
                    user_id=user_id,
                    plan_type=subscription.plan_type,
                    pages_remaining=plan.pages,
                    last_reset=now,
                    is_active=True
                )
        
        return subscription
    except Exception as e:
        print(f"Error in check_and_reset_subscription: {e}")
        return subscription  # حتی اگر خطا هم رخ داد، subscription فعلی را برگردان

async def create_or_update_subscription(user_id: str, plan_type: str):
    """ایجاد یا به‌روزرسانی اشتراک کاربر"""
    try:
        plan = PLANS.get(plan_type)
        if not plan:
            return False, "پلن انتخابی معتبر نیست"

        # بررسی وجود اشتراک قبلی
        existing = await get_user_subscription(user_id)

        if existing:
            # به‌روزرسانی اشتراک موجود
            supabase.table("subscriptions").update({
                "plan_type": plan_type,
                "pages_remaining": plan.pages,
                "last_reset": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("user_id", user_id).execute()
        else:
            # ایجاد اشتراک جدید
            supabase.table("subscriptions").insert({
                "user_id": user_id,
                "plan_type": plan_type,
                "pages_remaining": plan.pages,
                "last_reset": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).execute()

        return True, "اشتراک با موفقیت فعال شد"
    except Exception as e:
        print(f"Error creating/updating subscription: {e}")
        return False, str(e)

async def deduct_pages(user_id: str, pages_used: int):
    """کسر صفحات استفاده شده از اشتراک کاربر"""
    try:
        subscription = await get_user_subscription(user_id)
        if not subscription:
            return False, "اشتراکی یافت نشد"

        new_pages = max(0, subscription.pages_remaining - pages_used)

        supabase.table("subscriptions").update({
            "pages_remaining": new_pages,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("user_id", user_id).execute()

        return True, new_pages
    except Exception as e:
        print(f"Error deducting pages: {e}")
        return False, str(e)