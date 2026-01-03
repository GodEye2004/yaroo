from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:mo90mo80@127.0.0.1:5433/postgres"



engin = create_async_engine(
    DATABASE_URL,
    # remember=> logs sql m disable on producion.
    echo=True,  
)

AsyncSessionLocal = sessionmaker(
    bind=engin,
    class_=AsyncSession,
    expire_on_commit=False
)