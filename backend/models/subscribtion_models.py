from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SubscriptionPlan(BaseModel):
    name: str
    price: int
    max_pages: int  # تغییر از pages به max_pages
    description: str

class UserSubscription(BaseModel):
    user_id: str
    plan_type: str
    pages_remaining: int
    last_reset: datetime
    is_active: bool = True

# تعریف پلن‌های موجود با محدودیت تعداد صفحات
PLANS = {
    "free": SubscriptionPlan(
        name="رایگان",
        price=0,
        max_pages=5,  # حداکثر 5 صفحه
        description="حداکثر ۵ صفحه در ماه"
    ),
    "basic": SubscriptionPlan(
        name="پایه",
        price=50000,
        max_pages=50,  # حداکثر 50 صفحه
        description="ماهانه ۵۰,۰۰۰ تومان برای ۵۰ صفحه"
    ),
    "pro": SubscriptionPlan(
        name="حرفه‌ای",
        price=200000,
        max_pages=300,  # حداکثر 300 صفحه
        description="ماهانه ۲۰۰,۰۰۰ تومان برای ۳۰۰ صفحه"
    ),
}