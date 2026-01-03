from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from db_config import AsyncSessionLocal
from models.tenant_data import TenatData

router = APIRouter()

@router.post("/select_category")
async def select_category(request: Request):
    body = await request.json()
    user_id = body.get("user_id")
    category = body.get("category")
    print("Raw category received from front:", repr(category))
    
    if not user_id or not category:
        return JSONResponse(status_code=400, content={"error": "user_id and category are required"})

    async with AsyncSessionLocal() as session:
        # Check if row exists
        result = await session.execute(select(TenatData).where(TenatData.user_id == user_id))
        row = result.scalars().first()
        
        if row:
            # Update existing row
            row.category = category
        else:
            # Insert new row with data as empty dict
            new_row = TenatData(
                user_id=user_id,
                category=category,
                data={},               # ensures NOT NULL constraint is satisfied
                related_sources=[]     # empty list by default
            )
            session.add(new_row)
        
        await session.commit()

    return {"message": f"Category '{category}' activated."}
