import io
import json
import chardet
import tempfile
import os
import traceback
from docx import Document
from langchain_community.document_loaders import PyPDFLoader
from services.text_processing import deep_clean_farsi_text, looks_garbled

async def process_pdf(content: bytes, pages_to_process: int = None) -> dict:
    """پردازش فایل PDF با پشتیبانی از OCR"""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(content)
        pdf_path = tmp_pdf.name

    context = ""
    context_blocks = []
    use_ocr = False

    try:
        # مرحله 1: استخراج متن با PyPDFLoader
        try:
            reader = PyPDFLoader(pdf_path)
            pages = reader.load()
            
            if pages_to_process and len(pages) > pages_to_process:
                pages = pages[:pages_to_process]
                print(f"⚠️ محدود کردن صفحات به {pages_to_process} صفحه اول")

            print(f"✅ تعداد صفحات پیدا شده: {len(pages)}")
            
            for page_num, page in enumerate(pages, 1):
                page_text = page.page_content
                cleaned_text = deep_clean_farsi_text(page_text)
                if cleaned_text:
                    context += cleaned_text + "\n\n"
                    context_blocks.append({
                        "page": page_num,
                        "text": cleaned_text,
                        "char_count": len(cleaned_text),
                        "method": "pypdfloader"
                    })
            
            # بررسی کیفیت متن استخراج شده
            total_chars = len(context.strip())
            print(f"📊 تعداد کاراکترهای استخراج شده: {total_chars}")
            
            if total_chars < 100 or looks_garbled(context):
                print(f"⚠️ متن استخراج شده ناکافی یا نامناسب است")
                use_ocr = True
                
        except Exception as e:
            print(f"❌ خطا در PyPDFLoader: {str(e)}")
            use_ocr = True

        # مرحله 2: اگر نیاز به OCR بود، از PyMuPDF استفاده می‌کنیم
        if use_ocr:
            print("🔍 استفاده از PyMuPDF برای استخراج متن...")
            try:
                import fitz  # PyMuPDF
                
                doc = fitz.open(pdf_path)
                print(f"📄 تعداد صفحات در PyMuPDF: {len(doc)}")
                
                # تعیین محدوده صفحات
                if pages_to_process and len(doc) > pages_to_process:
                    page_range = range(min(pages_to_process, len(doc)))
                else:
                    page_range = range(len(doc))
                
                # ریست کردن context
                context = ""
                context_blocks = []
                
                for page_num in page_range:
                    page = doc.load_page(page_num)
                    
                    # روش 1: استخراج متن ساده
                    text = page.get_text()
                    
                    # روش 2: اگر متن کافی نبود، از استخراج پیشرفته استفاده کن
                    if not text or len(text.strip()) < 50:
                        text = page.get_text("dict")
                        # استخراج متن از dict
                        blocks_text = []
                        for block in text.get("blocks", []):
                            if block.get("type") == 0:  # نوع text
                                for line in block.get("lines", []):
                                    for span in line.get("spans", []):
                                        blocks_text.append(span.get("text", ""))
                        text = " ".join(blocks_text)
                    
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
                print(f"✅ PyMuPDF: {len(context_blocks)} صفحه پردازش شد")
                
            except ImportError:
                print("❌ PyMuPDF نصب نیست! لطفا آن را نصب کنید:")
                print("   pip install pymupdf")
                raise Exception("PyMuPDF نصب نیست. لطفا آن را نصب کنید.")
            except Exception as e:
                print(f"❌ خطا در PyMuPDF: {str(e)}")
                traceback.print_exc()
                raise Exception(f"خطا در استخراج متن از PDF: {str(e)}")

    finally:
        # حذف فایل موقت
        try:
            os.unlink(pdf_path)
        except Exception as e:
            print(f"⚠️ خطا در حذف فایل موقت: {str(e)}")

    return {
        "extraction_method": "ocr" if use_ocr else "text",
        "total_characters": len(context),
        "total_blocks": len(context_blocks),
        "full_text": context,
        "blocks": context_blocks,
    }

def process_txt(content: bytes) -> dict:
    detected = chardet.detect(content)
    encoding = detected.get("encoding") or "utf-8"
    raw_text = content.decode(encoding, errors="ignore")
    return {"text": deep_clean_farsi_text(raw_text)}

def process_docx(content: bytes) -> dict:
    doc = Document(io.BytesIO(content))
    full_text = "\n".join([para.text for para in doc.paragraphs])
    return {"text": deep_clean_farsi_text(full_text)}

def process_json(content: bytes) -> dict:
    return json.loads(content.decode("utf-8", errors="ignore"))