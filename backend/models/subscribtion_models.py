from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SubscriptionPlan(BaseModel):
    name: str
    price: int
    pages: int
    description: str

class UserSubscription(BaseModel):
    user_id: str
    plan_type: str
    pages_remaining: int
    last_reset: datetime
    is_active: bool = True

# تعریف پلن‌های موجود
PLANS = {
    "free": SubscriptionPlan(
        name="رایگان",
        price=0,
        pages=3,
        description="3 صفحه اول رایگان در ماه"
    ),
    "basic": SubscriptionPlan(
        name="پایه",
        price=50000,
        pages=50,
        description="ماهانه 50,000 تومان برای 50 صفحه"
    ),
    "pro": SubscriptionPlan(
        name="حرفه‌ای",
        price=200000,
        pages=300,
        description="ماهانه 200,000 تومان برای 300 صفحه"
    )
}