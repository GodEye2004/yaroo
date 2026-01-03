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
    # بررسی طول پرامپت قبل از ارسال
    estimated_tokens = estimate_tokens(prompt)
    print(f"📊 تخمین تعداد توکن‌های پرامپت: {estimated_tokens}")

    if estimated_tokens > 7000:  # حد امن کمتر از 8000
        print(f"⚠️ پرامپت خیلی بزرگ است ({estimated_tokens} توکن). در حال کوتاه کردن...")
        # اگر پرامپت خیلی بزرگ بود، آن را کوتاه کن
        prompt = prompt[:28000]  # حدود 7000 توکن

    client = ChatCompletionsClient(
        endpoint=ENDPOINT,
        credential=AzureKeyCredential(GITHUB_TOKEN)
    )

    final_text = ""

    try:
        maybe_async = client.complete(
            stream=True,
            messages=[UserMessage(content=prompt)],
            model=MODEL_NAME,
            temperature=0.3
        )

        if hasattr(maybe_async, "__aiter__"):
            async for update in maybe_async:
                if update.choices and update.choices[0].delta and update.choices[0].delta.content:
                    final_text += update.choices[0].delta.content
        else:
            for update in maybe_async:
                if update.choices and update.choices[0].delta and update.choices[0].delta.content:
                    final_text += update.choices[0].delta.content

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



