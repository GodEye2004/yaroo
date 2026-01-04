from typing import Optional, Tuple
from datetime import datetime, timezone, timedelta
from models.subscribtion_models import UserSubscription, PLANS
from db_config import AsyncSessionLocal  # db_config must expose an asyncpg.Pool (use init_db_pool to set _db_pool)
import asyncpg
import traceback
import logging
from sqlalchemy import text

_db_pool: asyncpg.Pool | None = None

async def init_db_pool(dsn: str):
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(dsn)

async def get_user_subscription(user_id: str) -> Optional[UserSubscription]:
    try:
        # Prefer asyncpg pool if initialized for simple fetch; otherwise fall back to AsyncSessionLocal
        row = None
        if _db_pool:
            async with _db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT user_id, plan_type, pages_remaining, last_reset, is_active "
                    "FROM subscriptions WHERE user_id = $1 LIMIT 1",
                    user_id
                )
                data = dict(row) if row else None
        else:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(
                        "SELECT user_id, plan_type, pages_remaining, last_reset, is_active "
                        "FROM subscriptions WHERE user_id = :user_id LIMIT 1"
                    ),
                    {"user_id": user_id}
                )
                row_obj = result.fetchone()
                data = dict(row_obj._mapping) if row_obj else None

        if not data:
            return None

        last_reset = data.get("last_reset")
        if isinstance(last_reset, str):
            try:
                lr = last_reset
                if lr.endswith("Z"):
                    lr = lr[:-1] + "+00:00"
                data["last_reset"] = datetime.fromisoformat(lr)
            except Exception:
                data["last_reset"] = datetime.now(timezone.utc)
        elif last_reset is None:
            data["last_reset"] = datetime.now(timezone.utc)

        return UserSubscription(**data)
    except Exception as e:
        logging.exception("Error getting subscription")
        return None

async def check_and_reset_subscription(user_id: str) -> Optional[UserSubscription]:
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM subscriptions WHERE user_id = :uid"),
                {"uid": user_id}
            )
            row = result.first()
            if not row:
                return None

            subscription = UserSubscription(
                user_id=row.user_id,
                plan_type=row.plan_type,
                pages_remaining=row.pages_remaining,
                last_reset=row.last_reset,
                is_active=row.is_active
            )

            # Reset pages if 365 days passed
            now = datetime.now(timezone.utc)
            last_reset = subscription.last_reset
            if last_reset.tzinfo is None:
                last_reset = last_reset.replace(tzinfo=timezone.utc)

            if (now - last_reset) >= timedelta(days=365):
                plan = PLANS.get(subscription.plan_type)
                pages_to_reset = plan.max_pages if plan.plan_type != "free" else plan.max_pages
                await session.execute(
                    text("""
                        UPDATE subscriptions
                        SET pages_remaining=:pages, last_reset=:lr, updated_at=:ua
                        WHERE user_id=:uid
                    """),
                    {"pages": pages_to_reset, "lr": now, "ua": now, "uid": user_id}
                )
                await session.commit()
                subscription.pages_remaining = pages_to_reset
                subscription.last_reset = now

            return subscription
    except Exception as e:
        print("Error in check_and_reset_subscription:", e)
        return None



async def create_or_update_subscription(user_id: str, plan_type: str):
    try:
        plan = PLANS[plan_type]
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO subscriptions
                    (user_id, plan_type, pages_remaining, last_reset, created_at, updated_at, is_active)
                    VALUES (:uid, :plan, :pages, :lr, :created, :updated, :active)
                    ON CONFLICT (user_id) DO UPDATE
                    SET plan_type=:plan, pages_remaining=:pages, last_reset=:lr, updated_at=:updated, is_active=:active
                """),
                {
                    "uid": user_id,
                    "plan": plan_type,
                    "pages": plan.max_pages,
                    "lr": now,
                    "created": now,
                    "updated": now,
                    "active": True
                }
            )
            await session.commit()  # 🔑 commit immediately

        return True, f"اشتراک {plan.name} با موفقیت فعال شد"
    except Exception as e:
        return False, str(e)

async def deduct_pages(user_id: str, pages_used: int) -> Tuple[bool, Optional[int] or str]:
    try:
        subscription = await get_user_subscription(user_id)
        if not subscription:
            return False, "اشتراکی یافت نشد"

        if subscription.plan_type == "free":
            return True, 0

        new_pages = max(0, subscription.pages_remaining - pages_used)
        now = datetime.now(timezone.utc)

        if _db_pool:
            async with _db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE subscriptions SET pages_remaining=$1, updated_at=$2 WHERE user_id=$3",
                    new_pages, now, user_id
                )
        else:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("UPDATE subscriptions SET pages_remaining=:pr, updated_at=:ua WHERE user_id=:uid"),
                    {"pr": new_pages, "ua": now, "uid": user_id}
                )

        return True, new_pages
    except Exception:
        logging.exception("Error deducting pages")
        return False, "خطا در کم کردن صفحات"

async def can_upload_file(user_id: str, file_pages_count: int) -> Tuple[bool, str]:
    try:
        subscription = await get_user_subscription(user_id)
        if not subscription:
            return False, "اشتراکی یافت نشد"

        subscription = await check_and_reset_subscription(user_id)
        if not subscription:
            return False, "اشتراکی یافت نشد"

        plan = PLANS.get(subscription.plan_type)
        if not plan:
            return False, "پلن اشتراک نامعتبر است"

        if file_pages_count > plan.max_pages:
            return False, f"فایل شما {file_pages_count} صفحه دارد. در پلن {plan.name} فقط می‌توانید فایل‌های حداکثر {plan.max_pages} صفحه آپلود کنید."

        if subscription.plan_type != "free":
            if file_pages_count > subscription.pages_remaining:
                return False, f"صفحات کافی در اشتراک شما وجود ندارد. نیاز: {file_pages_count} صفحه، موجود: {subscription.pages_remaining} صفحه"

        return True, "مجاز است"
    except Exception:
        logging.exception("Error in can_upload_file")
        return False, "خطا در بررسی امکان آپلود فایل"
