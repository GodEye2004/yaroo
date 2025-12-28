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
from langchain_community.document_loaders import PyPDFLoader

from services.subscribtion_service import (
    check_and_reset_subscription, 
    deduct_pages
)
from services.text_processing import deep_clean_farsi_text, looks_garbled
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
    print("UPLOAD_JSON RECEIVED CATEGORY:", repr(category))

    # 1. بررسی اشتراک کاربر
    subscription = await check_and_reset_subscription(user_id)
    if not subscription:
        return JSONResponse(
            status_code=402,  # Payment Required
            content={"error": "لطفا ابتدا اشتراک خود را انتخاب کنید"}
        )

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

    # 3. اعمال محدودیت‌های اشتراک
    if subscription.plan_type == "free":
        # برای کاربران رایگان، فقط 3 صفحه اول
        max_pages = 3
        if pages_count > max_pages:
            # فقط 3 صفحه اول را پردازش کن
            pages_to_process = max_pages
            pages_to_deduct = 0  # کاربران رایگان صفحات کسر نمی‌شود
            warning = f"توجه: در پلن رایگان فقط {max_pages} صفحه اول پردازش می‌شود (از {pages_count} صفحه)"
        else:
            pages_to_process = pages_count
            pages_to_deduct = pages_count
            warning = None
    else:
        # برای کاربران پرداخت‌کننده
        if pages_count > subscription.pages_remaining:
            return JSONResponse(
                status_code=402,
                content={
                    "error": f"صفحات کافی در اشتراک شما وجود ندارد",
                    "details": {
                        "required_pages": pages_count,
                        "available_pages": subscription.pages_remaining,
                        "plan": subscription.plan_type
                    }
                }
            )
        pages_to_process = pages_count
        pages_to_deduct = pages_count
        warning = None

    # 4. پردازش فایل (با محدودیت صفحات برای کاربران رایگان)
    json_data = {}
    try:
        if filename.endswith(".json"):
            json_data = json.loads(content.decode("utf-8", errors="ignore"))

        elif filename.endswith(".pdf"):
            print(f"📄 شروع پردازش PDF: {file.filename}")
            print(f"📦 صفحات کل: {pages_count}")
            print(f"📄 صفحات قابل پردازش: {pages_to_process}")

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                tmp_pdf.write(content)
                pdf_path = tmp_pdf.name

            context = ""
            context_blocks = []
            use_ocr = False

            # پردازش PDF با محدودیت صفحات
            try:
                reader = PyPDFLoader(pdf_path)
                pages = reader.load()

                # محدود کردن صفحات برای کاربران رایگان
                if subscription.plan_type == "free" and len(pages) > pages_to_process:
                    pages = pages[:pages_to_process]

                print(f"✅ تعداد صفحات پردازش شده: {len(pages)}")

                for page_num, page in enumerate(pages, 1):
                    page_text = page.page_content
                    cleaned_text = deep_clean_farsi_text(page_text)
                    if cleaned_text:
                        context += cleaned_text + "\n\n"
                        context_blocks.append({
                            "page": page_num,
                            "text": cleaned_text,
                            "char_count": len(cleaned_text)
                        })

                if len(context.strip()) < 50 or looks_garbled(context):
                    use_ocr = True

            except Exception as e:
                print(f"❌ خطا در PyPDFLoader: {str(e)}")
                use_ocr = True

            # مرحله 2: اگر نیاز به OCR بود، از PyMuPDF استفاده می‌کنیم
            if use_ocr:
                print("🔍 نیاز به OCR تشخیص داده شد...")
                try:
                    # تلاش با PyMuPDF اگر نصب باشد
                    try:
                        import fitz  # PyMuPDF
                        print("استفاده از PyMuPDF برای استخراج متن...")
                        doc = fitz.open(pdf_path)
                        
                        # محدود کردن صفحات برای کاربران رایگان
                        if subscription.plan_type == "free" and pages_count > 3:
                            page_range = range(min(3, len(doc)))
                        else:
                            page_range = range(len(doc))
                            
                        for page_num in page_range:
                            page = doc.load_page(page_num)
                            text = page.get_text()
                            if text:
                                cleaned_text = deep_clean_farsi_text(text)
                                context += cleaned_text + "\n\n"
                                context_blocks.append({
                                    "page": page_num + 1,
                                    "text": cleaned_text,
                                    "char_count": len(cleaned_text),
                                    "method": "pymupdf"
                                })
                        doc.close()
                    except ImportError:
                        print("PyMuPDF نصب نیست، ادامه با متن استخراج شده...")
                except Exception as e:
                    print(f"❌ خطا در استخراج OCR: {str(e)}")

            # حذف فایل موقت
            try:
                os.unlink(pdf_path)
            except Exception as e:
                print(f"⚠️ خطا در حذف فایل موقت: {str(e)}")

            json_data = {
                "filename": file.filename,
                "category": category.strip().lower(),
                "extraction_method": "ocr" if use_ocr else "text",
                "total_characters": len(context),
                "total_blocks": len(context_blocks),
                "pages_total": pages_count,
                "pages_processed": pages_to_process,
                "full_text": context,
                "blocks": context_blocks,
                "metadata": {
                    "file_size_bytes": len(content)
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

        # 5. کسر صفحات از اشتراک (به جز کاربران رایگان)
        if subscription.plan_type != "free" and pages_to_deduct > 0:
            success, result = await deduct_pages(user_id, pages_to_deduct)
            if not success:
                print(f"⚠️ خطا در کسر صفحات: {result}")

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

        response = {
            "message": f"File '{file.filename}' processed successfully ✅",
            "category": category,
            "file_type": filename.split('.')[-1],
            "subscription_info": {
                "plan": subscription.plan_type,
                "pages_used": pages_to_deduct,
                "pages_remaining": subscription.pages_remaining - pages_to_deduct if subscription.plan_type != "free" else "unlimited",
                "pages_processed": pages_to_process,
                "pages_total": pages_count
            },
            "extraction_summary": {
                "method": json_data.get("extraction_method", "unknown"),
                "total_characters": json_data.get("total_characters", 0),
                "total_blocks": json_data.get("total_blocks", 0)
            },
            "json_data_preview": json.dumps(json_data, ensure_ascii=False)[:500],
        }

        if warning:
            response["warning"] = warning

        return response

    except Exception as e:
        print(f"ERROR in upload_json: {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Processing failed: {str(e)}"})