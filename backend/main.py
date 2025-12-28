import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import routers
from routers import categories, subscribtion, upload, chat

load_dotenv()

# ----------------------------
# FastAPI setup
# ----------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers


app.include_router(categories.router, tags=["categories"])
app.include_router(subscribtion.router, tags=["subscription"])
app.include_router(upload.router, tags=["upload"])
app.include_router(chat.router, tags=["chat"])
@app.get("/")
async def root():
    return {"message": "API is running"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        timeout_keep_alive=120,
        limit_concurrency=50,
        limit_max_requests=500
    )