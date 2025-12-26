"""
تنظیمات اصلی برنامه
"""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://hfkcxtntiltfqnofylkw.supabase.co")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# App Settings
MAX_CHUNK_SIZE = 1000
MAX_MEMORY = 5  # حافظه مکالمه

# CORS Settings
ALLOWED_ORIGINS = ["*"]

# Performance Settings
TIMEOUT_KEEP_ALIVE = 120
LIMIT_CONCURRENCY = 100  # افزایش برای تست فشار
LIMIT_MAX_REQUESTS = 1000  # افزایش برای تست فشار

# File Processing
MAX_FILE_SIZE_MB = 50  # حداکثر حجم فایل به مگابایت
TEMP_DIR = "/tmp"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
