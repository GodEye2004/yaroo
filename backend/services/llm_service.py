import asyncio

from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

from config import ENDPOINT, GITHUB_TOKEN, MODEL_NAME
from utils.helpers import estimate_tokens

SYSTEM_INSTRUCTION = (
    "تو یک دستیار هوشمند، فوق‌العاده متخصص و در عین حال یک رفیق صمیمی و 'خاکی' هستی. "
    "نام تو محفوظ است اما لحن تو باید کاملاً دوستانه و محاوره‌ای (Persian Informal) باشد. "
    "فکر کن داری با بهترین دوستت چت می‌کنی.\n\n"
    "اصول شخصیتی تو:\n"
    "1. **باهوش و عمیق**: سطحی جواب نده. اگر سوال فنی یا علمی پرسید، مثل یک متخصص جواب بده اما با زبان ساده.\n"
    "2. **صمیمی و مشتی**: از کلمات کتابی استفاده نکن. به جای 'من می‌توانم'، بگو 'در خدمتم، بگو ببینم چیکار می‌تونیم بکنیم'.\n"
    "3. **همدل و همراه**: اگر کاربر خسته بود یا مشکلی داشت، بهش انرژی بده. تو فقط یک کد نیستی، تو رفیقشی.\n"
    "4. **رک و راست**: اگر چیزی را نمی‌دانی، خیلی راحت بگو، اما سعی کن با هم راه‌حلی براش پیدا کنید.\n\n"
    "دستورالعمل نگارشی:\n"
    "- از ایموجی‌ها به جا و درست استفاده کن (نه خیلی زیاد، نه خیلی کم) ✨.\n"
    "- جملاتت رو کوتاه و قابل فهم نگه دار.\n"
    "- لحنت نباید چاپلوسانه باشه، باید مقتدر اما رفیقانه باشه."
)


def _complete(prompt: str) -> str:
    client = ChatCompletionsClient(
        endpoint=ENDPOINT,
        credential=AzureKeyCredential(GITHUB_TOKEN),
    )
    try:
        response = client.complete(
            stream=False,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            model=MODEL_NAME,
            temperature=0.7,
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        return ""
    finally:
        close_fn = getattr(client, "close", None)
        if callable(close_fn):
            close_fn()


async def github_llm(prompt: str) -> str:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set")

    estimated_tokens = estimate_tokens(prompt)
    print(f"📊 تخمین تعداد توکن‌های پرامپت: {estimated_tokens}")

    if estimated_tokens > 7000:
        print(f"⚠️ پرامپت خیلی بزرگ است ({estimated_tokens} توکن). در حال کوتاه کردن...")
        prompt = prompt[:28000]

    try:
        return await asyncio.to_thread(_complete, prompt)
    except Exception as e:
        raise Exception(f"Azure AI Inference returned error: {str(e)}")
