import io
import traceback

import PyPDF2
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select

from db_config import AsyncSessionLocal
from models.subscription_models import PLANS
from models.tenant_data import TenantData
from services.file_processing import process_docx, process_json, process_txt
from services.pdf_extraction import process_pdf_advanced
from services.subscription_service import (
    can_upload_file,
    check_and_reset_subscription,
    deduct_pages,
)

router = APIRouter()


def count_pdf_pages(pdf_bytes: bytes) -> int:
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        return len(pdf_reader.pages)
    except Exception as e:
        print(f"Error counting PDF pages: {e}")
        return 0


@router.post("/upload_json")
async def upload_json(
    user_id: str = Form(...),
    category: str = Form(...),
    file: UploadFile = File(...),
):
    subscription = await check_and_reset_subscription(user_id)
    if not subscription or not subscription.is_active:
        return JSONResponse(
            status_code=402,
            content={"error": "لطفا ابتدا اشتراک خود را انتخاب کنید"},
        )

    print("=" * 60)
    print(f"📥 UPLOAD_JSON RECEIVED")
    print(f"👤 User ID: {user_id}")
    print(f"📂 Category: {category}")
    print(f"📄 Filename: {file.filename}")
    print(f"✅ اشتراک کاربر: {subscription.plan_type}")

    content = await file.read()
    filename = (file.filename or "").lower()

    pages_count = 1
    if filename.endswith(".pdf"):
        pages_count = count_pdf_pages(content)
        if pages_count == 0:
            return JSONResponse(
                status_code=400,
                content={"error": "فایل PDF نامعتبر است یا قابل خواندن نیست"},
            )

    print(f"📊 تعداد صفحات فایل: {pages_count}")

    can_upload, message = await can_upload_file(user_id, pages_count)
    if not can_upload:
        return JSONResponse(status_code=402, content={"error": message})

    json_data = {}
    try:
        if filename.endswith(".json"):
            json_data = process_json(content)

        elif filename.endswith(".pdf"):
            max_pages = None
            plan = PLANS.get(subscription.plan_type)
            if plan and pages_count > plan.max_pages:
                max_pages = plan.max_pages
                print(f"⚠️ محدود کردن به {max_pages} صفحه اول")

            processed = await process_pdf_advanced(content, max_pages)
            json_data = {
                "filename": file.filename,
                "category": category.strip().lower(),
                "extraction_method": processed["extraction_method"],
                "total_characters": processed["total_characters"],
                "total_blocks": processed["total_blocks"],
                "pages_total": pages_count,
                "pages_processed": len(processed["blocks"]),
                "full_text": processed["full_text"],
                "blocks": processed["blocks"],
                "quality": processed.get("quality", "unknown"),
                "metadata": {
                    "file_size_bytes": len(content),
                    "extraction_quality": processed.get("quality", "unknown"),
                },
            }

        elif filename.endswith(".txt"):
            json_data = process_txt(content)

        elif filename.endswith(".docx"):
            json_data = process_docx(content)

        else:
            return JSONResponse(
                status_code=400,
                content={"error": "فرمت فایل پشتیبانی نمی‌شود. فقط JSON, PDF, TXT, DOCX."},
            )

        remaining_pages = subscription.pages_remaining
        pages_used = 0
        if subscription.plan_type != "free":
            success, result = await deduct_pages(user_id, pages_count)
            if not success:
                print(f"⚠️ خطا در کسر صفحات: {result}")
            else:
                pages_used = pages_count
                remaining_pages = result
                print(f"✅ {pages_count} صفحه کسر شد. صفحات باقیمانده: {result}")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TenantData).where(TenantData.user_id == user_id)
            )
            row = result.scalars().first()
            if row:
                row.category = category
                row.data = json_data
            else:
                session.add(
                    TenantData(
                        user_id=user_id,
                        category=category,
                        data=json_data,
                        related_sources=[],
                    )
                )
            await session.commit()

        plan = PLANS.get(subscription.plan_type)
        response = {
            "message": f"فایل '{file.filename}' با موفقیت آپلود شد ✅",
            "category": category,
            "file_type": filename.split(".")[-1],
            "subscription_info": {
                "plan": subscription.plan_type,
                "plan_name": plan.name if plan else "نامشخص",
                "pages_used": pages_used,
                "pages_remaining": remaining_pages,
                "max_allowed_pages": plan.max_pages if plan else 0,
                "file_pages": pages_count,
                "upload_status": "موفق",
            },
            "extraction_summary": {
                "method": json_data.get("extraction_method", "unknown"),
                "quality": json_data.get("quality", "unknown"),
                "total_characters": json_data.get("total_characters", 0),
                "total_blocks": json_data.get("total_blocks", 0),
                "pages_processed": json_data.get("pages_processed", 0),
            },
        }

        print("upload successfully!")
        print("=" * 60)
        return response

    except Exception as e:
        print(f"❌ ERROR in upload_json: {str(e)}")
        traceback.print_exc()
        print("=" * 60)
        return JSONResponse(status_code=500, content={"error": f"Processing failed: {str(e)}"})
