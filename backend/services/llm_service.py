import os
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference.models import UserMessage
from dotenv import load_dotenv
from utils.helpers import estimate_tokens

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ENDPOINT = "https://models.inference.ai.azure.com"
MODEL_NAME = "gpt-4o"

async def github_llm(prompt: str) -> str:
    estimated_tokens = estimate_tokens(prompt)
    print(f"📊 تخمین تعداد توکن‌های پرامپت: {estimated_tokens}")

    if estimated_tokens > 7000:
        print(f"⚠️ پرامپت خیلی بزرگ است ({estimated_tokens} توکن). در حال کوتاه کردن...")
        prompt = prompt[:28000]

    client = ChatCompletionsClient(
        endpoint=ENDPOINT,
        credential=AzureKeyCredential(GITHUB_TOKEN)
    )

    # system prompt engineering.
    system_instruction = (
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

    final_text = ""

    try:
        response = client.complete(
            stream=False,
            messages=[
                # system message
                {"role": "system", "content": system_instruction},
                # user message
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.7 # temperature for creativity
        )

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            final_text = response.choices[0].message.content

    except Exception as e:
        raise Exception(f"Azure AI Inference returned error: {str(e)}")
    finally:
        close_fn = getattr(client, "close", None)
        if close_fn:
            if callable(close_fn):
                maybe_awaitable = close_fn()
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable

    return final_text.strip()
