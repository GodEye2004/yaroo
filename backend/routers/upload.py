import io
import json
import traceback
import tempfile
import os
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
import PyPDF2
from io import BytesIO
import chardet
from docx import Document

from services.subscribtion_service import (
    check_and_reset_subscription, 
    deduct_pages,
    can_upload_file,
    PLANS
)
from services.pdf_extraction import process_pdf_advanced  # ✅ تغییر اینجا
from services.text_processing import deep_clean_farsi_text
from db_config import supabase

router = APIRouter()

def count_pdf_pages(pdf_bytes: bytes) -> int:
    try:
        pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
        return len(pdf_reader.pages)
    except Exception as e:
        print(f"Error counting PDF pages: {e}")
        return 0

@router.post("/upload_json")
async def upload_json(
        user_id: str = Form(...),
        category: str = Form(...),
        file: UploadFile = File(...)
):
    print("=" * 60)
    print(f"📥 UPLOAD_JSON RECEIVED")
    print(f"👤 User ID: {user_id}")
    print(f"📂 Category: {category}")
    print(f"📄 Filename: {file.filename}")

    # 1. بررسی اشتراک کاربر
    subscription = await check_and_reset_subscription(user_id)
    if not subscription:
        return JSONResponse(
            status_code=402,
            content={"error": "لطفا ابتدا اشتراک خود را انتخاب کنید"}
        )
    
    print(f"✅ اشتراک کاربر: {subscription.plan_type}")

    # 2. خواندن فایل و محاسبه تعداد صفحات
    content = await file.read()
    filename = file.filename.lower() if file.filename else ""

    # محاسبه تعداد صفحات
    pages_count = 1  # پیش‌فرض برای فایل‌های غیر PDF
    if filename.endswith(".pdf"):
        pages_count = count_pdf_pages(content)
        if pages_count == 0:
            return JSONResponse(
                status_code=400,
                content={"error": "فایل PDF نامعتبر است یا قابل خواندن نیست"}
            )
    
    print(f"📊 تعداد صفحات فایل: {pages_count}")

    # 3. بررسی آیا کاربر می‌تواند این فایل را آپلود کند
    can_upload, message = await can_upload_file(user_id, pages_count)
    if not can_upload:
        return JSONResponse(
            status_code=402,
            content={"error": message}
        )
    
    print(f"✅ کاربر مجاز به آپلود فایل است")

    # 4. پردازش فایل
    json_data = {}
    try:
        if filename.endswith(".json"):
            json_data = json.loads(content.decode("utf-8", errors="ignore"))

        elif filename.endswith(".pdf"):
            print(f"📄 شروع پردازش پیشرفته PDF...")
            
            # تعیین محدودیت صفحات برای کاربران رایگان
            max_pages = None
            if subscription.plan_type == "free":
                plan = PLANS.get("free")
                if plan and pages_count > plan.max_pages:
                    max_pages = plan.max_pages
                    print(f"⚠️ محدود کردن به {max_pages} صفحه اول (پلن رایگان)")
            
            # استفاده از پردازشگر پیشرفته
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
                    "extraction_quality": processed.get("quality", "unknown")
                }
            }

        elif filename.endswith(".txt"):
            detected = chardet.detect(content)
            encoding = detected.get("encoding") or "utf-8"
            raw_text = content.decode(encoding, errors="ignore")
            json_data = {"text": deep_clean_farsi_text(raw_text)}

        elif filename.endswith(".docx"):
            doc = Document(io.BytesIO(content))
            full_text = "\n".join([para.text for para in doc.paragraphs])
            json_data = {"text": deep_clean_farsi_text(full_text)}

        else:
            return JSONResponse(
                status_code=400,
                content={"error": "فرمت فایل پشتیبانی نمی‌شود. فقط JSON, PDF, TXT, DOCX."}
            )

        # 5. کسر صفحات از اشتراک (فقط برای کاربران پولی)
        if subscription.plan_type != "free":
            print(f"💰 کسر {pages_count} صفحه از اشتراک کاربر...")
            success, result = await deduct_pages(user_id, pages_count)
            if not success:
                print(f"⚠️ خطا در کسر صفحات: {result}")
            else:
                print(f"✅ {pages_count} صفحه کسر شد. صفحات باقیمانده: {result}")
        else:
            print(f"ℹ️ صفحات کسر نمی‌شود (پلن رایگان)")

        # 6. ذخیره داده‌ها در Supabase
        related_data = []
        existing = supabase.table("ai_assist").select("*").eq("user_id", user_id).execute()
        if existing.data:
            supabase.table("ai_assist").update({
                "category": category,
                "data": json_data,
                "related_sources": related_data
            }).eq("user_id", user_id).execute()
        else:
            supabase.table("ai_assist").insert({
                "user_id": user_id,
                "category": category,
                "data": json_data,
                "related_sources": related_data
            }).execute()

        plan = PLANS.get(subscription.plan_type)
        response = {
            "message": f"فایل '{file.filename}' با موفقیت آپلود شد ✅",
            "category": category,
            "file_type": filename.split('.')[-1],
            "subscription_info": {
                "plan": subscription.plan_type,
                "plan_name": plan.name if plan else "نامشخص",
                "pages_used": pages_count if subscription.plan_type != "free" else 0,
                "pages_remaining": subscription.pages_remaining - pages_count if subscription.plan_type != "free" else 0,
                "max_allowed_pages": plan.max_pages if plan else 0,
                "file_pages": pages_count,
                "upload_status": "موفق"
            },
            "extraction_summary": {
                "method": json_data.get("extraction_method", "unknown"),
                "quality": json_data.get("quality", "unknown"),
                "total_characters": json_data.get("total_characters", 0),
                "total_blocks": json_data.get("total_blocks", 0),
                "pages_processed": json_data.get("pages_processed", 0)
            },
            "json_data_preview": json.dumps(json_data, ensure_ascii=False)[:500] if isinstance(json_data, dict) else str(json_data)[:500],
        }

        print("✅ آپلود با موفقیت انجام شد")
        print("=" * 60)
        
        return response

    except Exception as e:
        print(f"❌ ERROR in upload_json: {str(e)}")
        traceback.print_exc()
        print("=" * 60)
        return JSONResponse(status_code=500, content={"error": f"Processing failed: {str(e)}"})