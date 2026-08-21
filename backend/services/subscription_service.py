import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Union

from sqlalchemy import select

from db_config import AsyncSessionLocal
from models.subscription_models import PLANS, Subscription, UserSubscription


def _to_utc(dt: datetime) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _as_schema(row: Subscription) -> UserSubscription:
    return UserSubscription.model_validate(row)


async def get_user_subscription(user_id: str) -> Optional[UserSubscription]:
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            row = result.scalars().first()
            if not row:
                return None
            return _as_schema(row)
    except Exception:
        logging.exception("Error getting subscription")
        return None


async def check_and_reset_subscription(user_id: str) -> Optional[UserSubscription]:
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            row = result.scalars().first()
            if not row:
                return None

            now = datetime.now(timezone.utc)
            last_reset = _to_utc(row.last_reset)
            plan = PLANS.get(row.plan_type)

            if plan and (now - last_reset) >= timedelta(days=365):
                row.pages_remaining = plan.max_pages
                row.last_reset = now
                row.updated_at = now
                await session.commit()
                await session.refresh(row)

            return _as_schema(row)
    except Exception as e:
        print("Error in check_and_reset_subscription:", e)
        return None


async def create_or_update_subscription(user_id: str, plan_type: str):
    try:
        plan = PLANS[plan_type]
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            row = result.scalars().first()
            if row:
                row.plan_type = plan_type
                row.pages_remaining = plan.max_pages
                row.last_reset = now
                row.updated_at = now
                row.is_active = True
            else:
                session.add(
                    Subscription(
                        user_id=user_id,
                        plan_type=plan_type,
                        pages_remaining=plan.max_pages,
                        last_reset=now,
                        created_at=now,
                        updated_at=now,
                        is_active=True,
                    )
                )
            await session.commit()

        return True, f"اشتراک {plan.name} با موفقیت فعال شد"
    except Exception as e:
        return False, str(e)


async def deduct_pages(user_id: str, pages_used: int) -> Tuple[bool, Union[int, str]]:
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            row = result.scalars().first()
            if not row:
                return False, "اشتراکی یافت نشد"

            if row.plan_type == "free":
                return True, row.pages_remaining

            row.pages_remaining = max(0, row.pages_remaining - pages_used)
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return True, row.pages_remaining
    except Exception:
        logging.exception("Error deducting pages")
        return False, "خطا در کم کردن صفحات"


async def can_upload_file(user_id: str, file_pages_count: int) -> Tuple[bool, str]:
    try:
        subscription = await check_and_reset_subscription(user_id)
        if not subscription or not subscription.is_active:
            return False, "اشتراکی یافت نشد"

        plan = PLANS.get(subscription.plan_type)
        if not plan:
            return False, "پلن اشتراک نامعتبر است"

        if file_pages_count > plan.max_pages:
            return False, (
                f"فایل شما {file_pages_count} صفحه دارد. "
                f"در پلن {plan.name} فقط می‌توانید فایل‌های حداکثر {plan.max_pages} صفحه آپلود کنید."
            )

        if subscription.plan_type != "free" and file_pages_count > subscription.pages_remaining:
            return False, (
                f"صفحات کافی در اشتراک شما وجود ندارد. "
                f"نیاز: {file_pages_count} صفحه، موجود: {subscription.pages_remaining} صفحه"
            )

        return True, "مجاز است"
    except Exception:
        logging.exception("Error in can_upload_file")
        return False, "خطا در بررسی امکان آپلود فایل"
