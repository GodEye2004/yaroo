from pathlib import Path
import os

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env")
load_dotenv(_backend_dir.parent / ".env")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ENDPOINT = os.getenv("ENDPOINT", "https://models.inference.ai.azure.com")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

MAX_CHUNK_SIZE = 1000
MAX_MEMORY = 5
ALLOWED_ORIGINS = ["*"]
TIMEOUT_KEEP_ALIVE = 120
LIMIT_CONCURRENCY = 100
LIMIT_MAX_REQUESTS = 1000
MAX_FILE_SIZE_MB = 50
TEMP_DIR = "/tmp"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
