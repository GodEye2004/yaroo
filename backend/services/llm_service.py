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

    final_text = ""

    try:
        response = client.complete(
            stream=False,
            messages=[UserMessage(content=prompt)],
            model=MODEL_NAME,
            temperature=0.3
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
