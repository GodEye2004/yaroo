import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://hfkcxtntiltfqnofylkw.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_KEY:
    raise ValueError("❌ SUPABASE_SERVICE_KEY is not set!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print(f"✅ Supabase connected: {SUPABASE_URL}")














# import os
# import ssl
# from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
# from sqlalchemy.orm import sessionmaker
#
# # گرفتن DATABASE_URL از محیط
# DATABASE_URL = os.getenv("DATABASE_URL")
# if not DATABASE_URL:
#     raise ValueError("❌ DATABASE_URL environment variable not set!")
#
# # اطمینان از استفاده از asyncpg
# if DATABASE_URL.startswith("postgresql://"):
#     DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
#
# # تنظیم SSL مخصوص Render
# ssl_context = ssl.create_default_context()
# engine = create_async_engine(
#     DATABASE_URL,
#     echo=True,
#     connect_args={"ssl": ssl_context}  # ضروری برای Render
# )
#
# # Async session factory
# AsyncSessionLocal = sessionmaker(
#     bind=engine,
#     class_=AsyncSession,
#     expire_on_commit=False
# )
#
# # Dependency برای FastAPI
# async def get_db():
#     async with AsyncSessionLocal() as session:
#         yield session
