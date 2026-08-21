from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from db_config import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True, nullable=False)
    plan_type = Column(String, nullable=False)
    pages_remaining = Column(Integer, nullable=False)
    last_reset = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True, nullable=False)


class UserSubscription(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


PLANS = {
    "free": Plan(name="Free", price=0, max_pages=5, description="پلن رایگان"),
    "basic": Plan(name="Basic", price=10, max_pages=50, description="پلن پایه"),
    "pro": Plan(name="Pro", price=30, max_pages=200, description="پلن حرفه‌ای"),
}
