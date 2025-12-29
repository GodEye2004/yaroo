import io
import tempfile
import os
import traceback
import fitz  # PyMuPDF
import pdfplumber
from services.text_processing import deep_clean_farsi_text
import arabic_reshaper
from bidi.algorithm import get_display
import re

def extract_with_pymupdf(pdf_path: str, max_pages: int = None) -> dict:
    """استخراج متن با PyMuPDF (بهترین برای فارسی)"""
    context = ""
    context_blocks = []
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        if max_pages and total_pages > max_pages:
            page_range = range(min(max_pages, total_pages))
        else:
            page_range = range(total_pages)
        
        for page_num in page_range:
            page = doc.load_page(page_num)
            
            # روش 1: استخراج متن ساده
            text = page.get_text()
            
            # روش 2: اگر متن کافی نبود، از استخراج پیشرفته استفاده کن
            if not text or len(text.strip()) < 50:
                text_dict = page.get_text("dict")
                
                # استخراج متن از ساختار dict
                blocks_text = []
                for block in text_dict.get("blocks", []):
                    if block.get("type") == 0:  # نوع text
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                font = span.get("font", "").lower()
                                text_content = span.get("text", "")
                                
                                # بررسی فونت فارسی
                                if any(font_keyword in font for font_keyword in ['arial', 'tahoma', 'nazanin', 'lotus', 'iran', 'persian']):
                                    # reshape برای فارسی
                                    try:
                                        reshaped_text = arabic_reshaper.reshape(text_content)
                                        bidi_text = get_display(reshaped_text)
                                        blocks_text.append(bidi_text)
                                    except:
                                        blocks_text.append(text_content)
                                else:
                                    blocks_text.append(text_content)
                
                text = " ".join(blocks_text)
            
            if text:
                # اصلاح مشکلات رایج در استخراج فارسی
                text = fix_farsi_text_issues(text)
                cleaned_text = deep_clean_farsi_text(text)
                
                context += cleaned_text + "\n\n"
                context_blocks.append({
                    "page": page_num + 1,
                    "text": cleaned_text,
                    "char_count": len(cleaned_text),
                    "method": "pymupdf_advanced"
                })
        
        doc.close()
        return {
            "success": True,
            "text": context,
            "blocks": context_blocks,
            "method": "pymupdf"
        }
        
    except Exception as e:
        print(f"❌ خطا در PyMuPDF: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def extract_with_pdfplumber(pdf_path: str, max_pages: int = None) -> dict:
    """استخراج متن با pdfplumber (برای PDFهای با کیفیت)"""
    context = ""
    context_blocks = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            
            if max_pages and total_pages > max_pages:
                pages_to_process = min(max_pages, total_pages)
            else:
                pages_to_process = total_pages
            
            for page_num in range(pages_to_process):
                page = pdf.pages[page_num]
                
                # استخراج متن
                text = page.extract_text()
                
                # اگر متن استخراج نشد، از استخراج جداول هم استفاده کن
                if not text or len(text.strip()) < 50:
                    text = page.extract_text(x_tolerance=1, y_tolerance=1)
                
                if text:
                    text = fix_farsi_text_issues(text)
                    cleaned_text = deep_clean_farsi_text(text)
                    
                    context += cleaned_text + "\n\n"
                    context_blocks.append({
                        "page": page_num + 1,
                        "text": cleaned_text,
                        "char_count": len(cleaned_text),
                        "method": "pdfplumber"
                    })
        
        return {
            "success": True,
            "text": context,
            "blocks": context_blocks,
            "method": "pdfplumber"
        }
        
    except Exception as e:
        print(f"❌ خطا در pdfplumber: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def extract_with_pypdfloader(pdf_path: str, max_pages: int = None) -> dict:
    """استخراج متن با PyPDFLoader (روش قدیمی)"""
    try:
        from langchain_community.document_loaders import PyPDFLoader
        
        context = ""
        context_blocks = []
        
        reader = PyPDFLoader(pdf_path)
        pages = reader.load()
        
        if max_pages and len(pages) > max_pages:
            pages = pages[:max_pages]
        
        for page_num, page in enumerate(pages, 1):
            page_text = page.page_content
            if page_text:
                page_text = fix_farsi_text_issues(page_text)
                cleaned_text = deep_clean_farsi_text(page_text)
                
                context += cleaned_text + "\n\n"
                context_blocks.append({
                    "page": page_num,
                    "text": cleaned_text,
                    "char_count": len(cleaned_text),
                    "method": "pypdfloader"
                })
        
        return {
            "success": True,
            "text": context,
            "blocks": context_blocks,
            "method": "pypdfloader"
        }
        
    except Exception as e:
        print(f"❌ خطا در PyPDFLoader: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def fix_farsi_text_issues(text: str) -> str:
    """اصلاح مشکلات رایج در متن فارسی استخراج شده"""
    if not text:
        return ""
    
    # 1. جایگزینی کاراکترهای معیوب
    replacements = {
        'ك': 'ک',
        'ي': 'ی',
        'ة': 'ه',
        'ؤ': 'و',
        'إ': 'ا',
        'أ': 'ا',
        'آ': 'آ',
        '٠': '۰',
        '١': '۱',
        '٢': '۲',
        '٣': '۳',
        '٤': '۴',
        '٥': '۵',
        '٦': '۶',
        '٧': '۷',
        '٨': '۸',
        '٩': '۹',
        'ققی': 'قرارداد',
        'صی': 'سرمایه',
        'قیی': 'شرکت',
        'هرمی': 'هرمی',
        'خ صی': 'خصوصی',
        'هوم': 'هوم',
        'نگر': 'نگار',
        'پی': 'پذیر',
        'قیبوس': 'قیبوس',
        'داود': 'داود',
        'دا رودی': 'داوردی',
    }
    
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    
    # 2. اصلاح فاصله‌ها
    text = re.sub(r'\s+', ' ', text)
    
    # 3. اصلاح حروف چسبیده
    farsi_chars = 'ابپتثجچحخدذرزسشصضطظعغفقکگلمنوهی'
    text = re.sub(f'([{farsi_chars}])([{farsi_chars}])', r'\1 \2', text)
    
    # 4. حذف کاراکترهای کنترل
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
    
    return text

async def process_pdf_advanced(content: bytes, max_pages: int = None) -> dict:
    """پردازش پیشرفته PDF با چندین روش"""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(content)
        pdf_path = tmp_pdf.name
    
    result = None
    methods = [
        ("pymupdf", extract_with_pymupdf),
        ("pdfplumber", extract_with_pdfplumber),
        ("pypdfloader", extract_with_pypdfloader),
    ]
    
    for method_name, extractor in methods:
        print(f"🔍 آزمایش روش {method_name}...")
        result = extractor(pdf_path, max_pages)
        
        if result["success"]:
            text_length = len(result["text"].strip())
            print(f"✅ روش {method_name} موفق: {text_length} کاراکتر")
            
            # بررسی کیفیت متن استخراج شده
            if text_length > 100:
                break
            else:
                print(f"⚠️ متن استخراج شده توسط {method_name} کافی نیست")
        else:
            print(f"❌ روش {method_name} ناموفق")
    
    # حذف فایل موقت
    try:
        os.unlink(pdf_path)
    except:
        pass
    
    if result and result["success"]:
        return {
            "extraction_method": result["method"],
            "total_characters": len(result["text"]),
            "total_blocks": len(result["blocks"]),
            "full_text": result["text"],
            "blocks": result["blocks"],
            "quality": "good" if len(result["text"].strip()) > 100 else "poor"
        }
    else:
        raise Exception("هیچ یک از روش‌های استخراج متن موفق نبودند")