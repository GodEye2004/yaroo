from pydantic import BaseModel
from datetime import datetime

class UserSubscription(BaseModel):
    user_id: str
    plan_type: str
    pages_remaining: int
    last_reset: datetime
    is_active: bool = True

class Plan(BaseModel):
    name: str
    price: float
    max_pages: int
    description: str

# Example plans
PLANS = {
    "free": Plan(name="Free", price=0, max_pages=5, description="پلن رایگان"),
    "basic": Plan(name="Basic", price=10, max_pages=50, description="پلن پایه"),
    "pro": Plan(name="Pro", price=30, max_pages=200, description="پلن حرفه‌ای"),
}
