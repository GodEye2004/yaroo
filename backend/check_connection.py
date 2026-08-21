import asyncio

from sqlalchemy import text

from db_config import AsyncSessionLocal


async def test_connection():
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            print("Connection successful! Result:", value)
            return True
        except Exception as e:
            print(f"Database connection error: {e}")
            return False


if __name__ == "__main__":
    asyncio.run(test_connection())
