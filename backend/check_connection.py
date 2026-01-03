import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db_config import AsyncSessionLocal

async def test_connection():
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            print("Connection succesful ! Result:", value)
        except Exception as e:
            print(f"Database connection error: {e}")
            return False
        
if __name__ == "__main__":
    asyncio.run(test_connection())