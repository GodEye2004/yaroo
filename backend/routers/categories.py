from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from db_config import AsyncSessionLocal
from models.tenant_data import TenantData

router = APIRouter()


@router.post("/select_category")
async def select_category(request: Request):
    body = await request.json()
    user_id = body.get("user_id")
    category = body.get("category")

    if not user_id or not category:
        return JSONResponse(status_code=400, content={"error": "user_id and category are required"})

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TenantData).where(TenantData.user_id == user_id))
        row = result.scalars().first()

        if row:
            row.category = category
        else:
            session.add(
                TenantData(
                    user_id=user_id,
                    category=category,
                    data={},
                    related_sources=[],
                )
            )

        await session.commit()

    return {"message": f"Category '{category}' activated."}
