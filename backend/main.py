from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS, LIMIT_CONCURRENCY, LIMIT_MAX_REQUESTS, TIMEOUT_KEEP_ALIVE
from db_config import init_db
from models import subscription_models as _subscription_models  # noqa: F401
from models import tenant_data as _tenant_data  # noqa: F401
from routers import categories, chat, subscription, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(categories.router, tags=["categories"])
app.include_router(subscription.router, tags=["subscription"])
app.include_router(upload.router, tags=["upload"])
app.include_router(chat.router, tags=["chat"])


@app.get("/")
async def root():
    return {"message": "API is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        timeout_keep_alive=TIMEOUT_KEEP_ALIVE,
        limit_concurrency=LIMIT_CONCURRENCY,
        limit_max_requests=LIMIT_MAX_REQUESTS,
    )
