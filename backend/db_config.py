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



