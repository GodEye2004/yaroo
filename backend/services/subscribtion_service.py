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
                # برای رایگان، max_pages است ولی در صفحات باقیمانده برای رایگان مهم نیست
                # برای پلن‌های پولی، صفحات باقیمانده را برابر max_pages قرار می‌دهیم
                pages_to_reset = plan.max_pages if subscription.plan_type != "free" else 0
                
                supabase.table("subscriptions").update({
                    "pages_remaining": pages_to_reset,
                    "last_reset": now.isoformat()
                }).eq("user_id", user_id).execute()
                
                return UserSubscription(
                    user_id=user_id,
                    plan_type=subscription.plan_type,
                    pages_remaining=pages_to_reset,
                    last_reset=now,
                    is_active=True
                )
        
        return subscription
    except Exception as e:
        print(f"Error in check_and_reset_subscription: {e}")
        return subscription

async def create_or_update_subscription(user_id: str, plan_type: str):
    """ایجاد یا به‌روزرسانی اشتراک کاربر"""
    try:
        plan = PLANS.get(plan_type)
        if not plan:
            return False, "پلن انتخابی معتبر نیست"

        # تعیین صفحات باقیمانده بر اساس پلن
        if plan_type == "free":
            pages_remaining = 0  # کاربران رایگان صفحات کسر نمی‌شود
        else:
            pages_remaining = plan.max_pages

        # بررسی وجود اشتراک قبلی
        existing = await get_user_subscription(user_id)

        if existing:
            # به‌روزرسانی اشتراک موجود
            supabase.table("subscriptions").update({
                "plan_type": plan_type,
                "pages_remaining": pages_remaining,
                "last_reset": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("user_id", user_id).execute()
        else:
            # ایجاد اشتراک جدید
            supabase.table("subscriptions").insert({
                "user_id": user_id,
                "plan_type": plan_type,
                "pages_remaining": pages_remaining,
                "last_reset": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).execute()

        return True, "اشتراک با موفقیت فعال شد"
    except Exception as e:
        print(f"Error creating/updating subscription: {e}")
        return False, str(e)

async def deduct_pages(user_id: str, pages_used: int):
    """کسر صفحات استفاده شده از اشتراک کاربر (فقط برای پلن‌های پولی)"""
    try:
        subscription = await get_user_subscription(user_id)
        if not subscription:
            return False, "اشتراکی یافت نشد"

        # کاربران رایگان صفحات کسر نمی‌شود
        if subscription.plan_type == "free":
            return True, 0

        new_pages = max(0, subscription.pages_remaining - pages_used)

        supabase.table("subscriptions").update({
            "pages_remaining": new_pages,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("user_id", user_id).execute()

        return True, new_pages
    except Exception as e:
        print(f"Error deducting pages: {e}")
        return False, str(e)

async def can_upload_file(user_id: str, file_pages_count: int) -> tuple[bool, str]:
    """بررسی آیا کاربر می‌تواند فایل را آپلود کند"""
    try:
        subscription = await check_and_reset_subscription(user_id)
        if not subscription:
            return False, "اشتراکی یافت نشد"
        
        plan = PLANS.get(subscription.plan_type)
        if not plan:
            return False, "پلن اشتراک نامعتبر است"
        
        # بررسی محدودیت تعداد صفحات
        if file_pages_count > plan.max_pages:
            return False, f"فایل شما {file_pages_count} صفحه دارد. در پلن {plan.name} فقط می‌توانید فایل‌های حداکثر {plan.max_pages} صفحه آپلود کنید."
        
        # برای کاربران پولی، بررسی صفحات باقیمانده
        if subscription.plan_type != "free":
            if file_pages_count > subscription.pages_remaining:
                return False, f"صفحات کافی در اشتراک شما وجود ندارد. نیاز: {file_pages_count} صفحه، موجود: {subscription.pages_remaining} صفحه"
        
        return True, "مجاز است"
    except Exception as e:
        print(f"Error in can_upload_file: {e}")
        return False, str(e)