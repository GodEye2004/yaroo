from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env")
load_dotenv(_backend_dir.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Check your .env file.")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

parsed = urlparse(DATABASE_URL)
query = dict(parse_qsl(parsed.query, keep_blank_values=True))
sslmode = query.pop("sslmode", None)
DATABASE_URL = urlunparse(parsed._replace(query=urlencode(query)))

host = parsed.hostname or ""
connect_args = {}
needs_ssl = sslmode in {"require", "verify-ca", "verify-full"} or (
    host not in {"localhost", "127.0.0.1"} and not host.startswith("/")
)
if needs_ssl:
    connect_args["ssl"] = True

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
