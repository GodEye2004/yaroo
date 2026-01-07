import io
import tempfile
import os
import re
import fitz  # PyMuPDF
import pdfplumber
from services.text_processing import deep_clean_farsi_text
import arabic_reshaper
from bidi.algorithm import get_display

# Try to import RapidOCR, handle case if not installed yet
try:
    from rapidocr_onnxruntime import RapidOCR
    ocr_engine = RapidOCR()
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("⚠️ RapidOCR not installed. OCR fallback will be disabled.")

def extract_with_pymupdf(pdf_path: str, max_pages: int = None) -> dict:
    """استخراج متن با PyMuPDF - بهترین روش برای فارسی"""
    context = ""
    context_blocks = []
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        page_range = range(min(max_pages, total_pages)) if max_pages else range(total_pages)
        
        for page_num in page_range:
            page = doc.load_page(page_num)
            
            # روش 1: استخراج با حفظ layout
            text = page.get_text("text", sort=True)
            
            # روش 2: استخراج پیشرفته با تحلیل فونت
            if not text or len(text.strip()) < 50:
                text_dict = page.get_text("dict")
                blocks_text = []
                
                for block in text_dict.get("blocks", []):
                    if block.get("type") == 0:  # text block
                        block_lines = []
                        
                        for line in block.get("lines", []):
                            line_text = []
                            
                            for span in line.get("spans", []):
                                text_content = span.get("text", "").strip()
                                
                                if text_content:
                                    # تشخیص و اصلاح متن فارسی
                                    if contains_farsi(text_content):
                                        try:
                                            reshaped = arabic_reshaper.reshape(text_content)
                                            text_content = get_display(reshaped)
                                        except:
                                            pass
                                    
                                    line_text.append(text_content)
                            
                            if line_text:
                                block_lines.append(" ".join(line_text))
                        
                        if block_lines:
                            blocks_text.append("\n".join(block_lines))
                
                text = "\n\n".join(blocks_text)
            
            # روش 3: استخراج با rawdict برای دقت بیشتر
            if not text or len(text.strip()) < 50:
                raw_dict = page.get_text("rawdict")
                raw_blocks = []
                
                for block in raw_dict.get("blocks", []):
                    if block.get("type") == 0:
                        for line in block.get("lines", []):
                            line_chars = []
                            for span in line.get("spans", []):
                                chars = span.get("chars", [])
                                for char_info in chars:
                                    c = char_info.get("c", "")
                                    if c and c.strip():
                                        line_chars.append(c)
                            
                            if line_chars:
                                line_text = "".join(line_chars)
                                if contains_farsi(line_text):
                                    try:
                                        reshaped = arabic_reshaper.reshape(line_text)
                                        line_text = get_display(reshaped)
                                    except:
                                        pass
                                raw_blocks.append(line_text)
                
                text = "\n".join(raw_blocks)
            
            if text:
                # اصلاح و پاکسازی متن
                text = fix_farsi_text_issues(text)
                text = normalize_farsi_text(text)
                cleaned_text = deep_clean_farsi_text(text)
                
                if cleaned_text and len(cleaned_text.strip()) > 10:
                    context += cleaned_text + "\n\n"
                    context_blocks.append({
                        "page": page_num + 1,
                        "text": cleaned_text,
                        "char_count": len(cleaned_text),
                        "word_count": len(cleaned_text.split()),
                        "method": "pymupdf_advanced"
                    })
        
        doc.close()
        
        return {
            "success": True,
            "text": context,
            "blocks": context_blocks,
            "method": "pymupdf",
            "total_chars": len(context),
            "total_pages": len(context_blocks)
        }
        
    except Exception as e:
        print(f"❌ خطا در PyMuPDF: {str(e)}")
        return {"success": False, "error": str(e)}

def extract_with_pdfplumber(pdf_path: str, max_pages: int = None) -> dict:
    """استخراج با pdfplumber - دقیق برای layout"""
    context = ""
    context_blocks = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            pages_to_process = min(max_pages, total_pages) if max_pages else total_pages
            
            for page_num in range(pages_to_process):
                page = pdf.pages[page_num]
                
                # استخراج با تنظیمات بهینه برای فارسی
                text = page.extract_text(
                    x_tolerance=2,
                    y_tolerance=2,
                    layout=True,
                    x_density=7.25,
                    y_density=13
                )
                
                # اگر نتیجه خوب نبود، از روش دیگر استفاده کن
                if not text or len(text.strip()) < 50:
                    text = page.extract_text()
                
                # استخراج جداول هم اگر وجود داشت
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        table_text = "\n".join([" | ".join([str(cell) if cell else "" for cell in row]) for row in table])
                        text += f"\n\n{table_text}"
                
                if text:
                    text = fix_farsi_text_issues(text)
                    text = normalize_farsi_text(text)
                    cleaned_text = deep_clean_farsi_text(text)
                    
                    if cleaned_text and len(cleaned_text.strip()) > 10:
                        context += cleaned_text + "\n\n"
                        context_blocks.append({
                            "page": page_num + 1,
                            "text": cleaned_text,
                            "char_count": len(cleaned_text),
                            "word_count": len(cleaned_text.split()),
                            "method": "pdfplumber"
                        })
        
        return {
            "success": True,
            "text": context,
            "blocks": context_blocks,
            "method": "pdfplumber",
            "total_chars": len(context),
            "total_pages": len(context_blocks)
        }
        
    except Exception as e:
        print(f"❌ خطا در pdfplumber: {str(e)}")
        return {"success": False, "error": str(e)}

def extract_with_ocr(pdf_path: str, max_pages: int = None) -> dict:
    """استخراج متن با OCR - برای فایل‌های اسکن شده"""
    if not HAS_OCR:
        return {"success": False, "error": "Library rapidocr-onnxruntime not installed"}
        
    context = ""
    context_blocks = []
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        pages_to_process = min(max_pages, total_pages) if max_pages else total_pages
        
        print(f"📷 شروع پردازش OCR برای {pages_to_process} صفحه...")
        
        for page_num in range(pages_to_process):
            page = doc.load_page(page_num)
            
            # تبدیل صفحه به تصویر با کیفیت بالا (zoom=2)
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            
            # اجرای OCR
            result, elapse = ocr_engine(img_bytes)
            
            if result:
                # نتیجه لیست شامل [تخت، جعبه، امتیاز] است
                page_text = "\n".join([line[1] for line in result])
                
                if page_text:
                    # اصلاح و پاکسازی
                    text = fix_farsi_text_issues(page_text)
                    text = normalize_farsi_text(text)
                    cleaned_text = deep_clean_farsi_text(text)
                    
                    if cleaned_text and len(cleaned_text.strip()) > 10:
                        context += cleaned_text + "\n\n"
                        context_blocks.append({
                            "page": page_num + 1,
                            "text": cleaned_text,
                            "char_count": len(cleaned_text),
                            "word_count": len(cleaned_text.split()),
                            "method": "rapidocr"
                        })
        
        doc.close()
        
        return {
            "success": True,
            "text": context,
            "blocks": context_blocks,
            "method": "rapidocr",
            "total_chars": len(context),
            "total_pages": len(context_blocks)
        }
        
    except Exception as e:
        print(f"❌ خطا در OCR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

def contains_farsi(text: str) -> bool:
    """بررسی اینکه آیا متن شامل حروف فارسی است"""
    farsi_pattern = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    return bool(farsi_pattern.search(text))

def normalize_farsi_text(text: str) -> str:
    """نرمال‌سازی پیشرفته متن فارسی"""
    if not text:
        return ""
    
    # 1. تبدیل حروف عربی به فارسی
    arabic_to_farsi = {
        'ك': 'ک', 'ي': 'ی', 'ى': 'ی',
        'ة': 'ه', 'ؤ': 'و', 'إ': 'ا',
        'أ': 'ا', 'ٱ': 'ا', 'ء': ''
    }
    
    for arabic, farsi in arabic_to_farsi.items():
        text = text.replace(arabic, farsi)
    
    # 2. تبدیل اعداد عربی به فارسی
    arabic_numbers = '٠١٢٣٤٥٦٧٨٩'
    farsi_numbers = '۰۱۲۳۴۵۶۷۸۹'
    trans_table = str.maketrans(arabic_numbers, farsi_numbers)
    text = text.translate(trans_table)
    
    # 3. حذف کاراکترهای کنترل و نامرئی
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    
    # 4. اصلاح فاصله‌های متعدد
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n\n+', '\n\n', text)
    
    # 5. اصلاح نیم‌فاصله
    text = text.replace('\u200c', ' ')  # حذف نیم‌فاصله نامرئی
    
    return text.strip()

def fix_farsi_text_issues(text: str) -> str:
    """اصلاح مشکلات خاص استخراج PDF فارسی"""
    if not text:
        return ""
    
    # 1. اصلاح کلمات معیوب رایج
    common_fixes = {
        'ققی': 'قرارداد',
        'صی': 'سرمایه',
        'قیی': 'شرکت',
        'هرمی': 'سهامی',
        'خ صی': 'خصوصی',
        'پی': 'پذیر',
        'مسو': 'مسئول',
        'تمی': 'تمام',
        'قعفه': 'قطعه',
        'نگر': 'نگار',
        'هوم': 'عموم',
        'مدی': 'مدیر',
        'عمل': 'عامل',
        'دا رودی': 'داوردی',
    }
    
    for wrong, correct in common_fixes.items():
        text = text.replace(wrong, correct)
    
    # 2. اصلاح شماره‌های تلفن معیوب
    text = re.sub(r'(\d{2,3})\s+(\d{3,4})\s+(\d{4})', r'\1-\2-\3', text)
    
    # 3. اصلاح ایمیل‌های معیوب
    text = re.sub(r'(\w+)\s*@\s*(\w+)\s*\.\s*(\w+)', r'\1@\2.\3', text)
    
    # 4. حذف کاراکترهای اضافی بین کلمات
    text = re.sub(r'([آ-ی])\s+([آ-ی])', r'\1\2', text)
    
    # 5. اصلاح نقطه‌گذاری
    text = re.sub(r'\s*\.\s*', '. ', text)
    text = re.sub(r'\s*،\s*', '، ', text)

    # 6. اصلاح پیشوندها و پسوندهای جدا افتاده (Heuristics)
    # اتصال "می" و "نمی" به فعل بعدی
    # Note: (?<=^|\s) is invalid in Python because ^ is zero-width and \s is not.
    # We use capturing group (^|\s) instead.
    # IMPORTANT: Replacement string must NOT be raw string if we use \u escape
    text = re.sub(r'(^|\s)(می|نمی)\s+(?=[آ-ی])', '\\1\\2\u200c', text)
    
    # اتصال "ها" و "های" به کلمه قبلی
    text = re.sub(r'(?<=[آ-ی])\s+(ها|های)(?=\s|$|\.|،)', '\u200c\\1', text)
    
    # اتصال "تر" و "ترین"
    text = re.sub(r'(?<=[آ-ی])\s+(تر|ترین)(?=\s|$|\.|،)', '\u200c\\1', text)
    
    return text

async def process_pdf_advanced(content: bytes, max_pages: int = None) -> dict:
    """پردازش چندمرحله‌ای PDF با انتخاب بهترین روش"""
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(content)
        pdf_path = tmp_pdf.name
    
    results = []
    methods = [
        ("PyMuPDF", extract_with_pymupdf),
        ("PDFPlumber", extract_with_pdfplumber),
    ]
    
    best_result = None
    max_quality_score = 0
    
    for method_name, extractor in methods:
        print(f"🔍 تست روش {method_name}...")
        
        try:
            result = extractor(pdf_path, max_pages)
            
            if result["success"]:
                text_length = len(result["text"].strip())
                word_count = len(result["text"].split())
                
                # محاسبه امتیاز کیفیت
                # فرمول: طول متن + امتیاز کلمات
                # اگر متن خیلی کوتاه باشد، امتیاز منفی می‌گیرد
                if text_length < 50:
                    quality_score = 0
                else:
                    quality_score = text_length + (word_count * 2)
                
                results.append({
                    "method": method_name,
                    "chars": text_length,
                    "words": word_count,
                    "score": quality_score
                })
                
                print(f"✅ {method_name}: {text_length} کاراکتر، {word_count} کلمه (امتیاز: {quality_score})")
                
                if quality_score > max_quality_score:
                    max_quality_score = quality_score
                    best_result = result
            else:
                print(f"❌ {method_name} ناموفق: {result.get('error', 'خطای ناشناخته')}")
                
        except Exception as e:
            print(f"❌ خطا در {method_name}: {str(e)}")
            
    # اگر نتیجه ضعیف بود و OCR داریم، OCR را تست کن
    if (not best_result or max_quality_score < 200) and HAS_OCR:
        print("⚠️ کیفیت استخراج پایین بود. تلاش با OCR...")
        try:
            ocr_result = extract_with_ocr(pdf_path, max_pages)
            if ocr_result["success"]:
                text_length = len(ocr_result["text"].strip())
                # OCR معمولاً دقیق‌تر است برای اسکن، پس ضریب بالاتر
                quality_score = text_length * 3 
                
                results.append({
                    "method": "RapidOCR",
                    "chars": text_length,
                    "words": len(ocr_result["text"].split()),
                    "score": quality_score
                })
                
                if quality_score > max_quality_score:
                    print(f"✅ OCR نتیجه بهتری داد: {text_length} کاراکتر")
                    best_result = ocr_result
                else:
                     print(f"ℹ️ OCR هم نتیجه بهتری نداشت ({text_length} کاراکتر)")
        except Exception as e:
             print(f"❌ خطا در اجرای OCR: {e}")
    
    # حذف فایل موقت
    try:
        os.unlink(pdf_path)
    except:
        pass
    
    if not best_result:
        raise Exception("❌ هیچ روشی نتوانست متن را استخراج کند")
    
    # ارزیابی کیفیت نهایی
    total_chars = len(best_result["text"])
    total_words = len(best_result["text"].split())
    
    quality = "عالی" if total_chars > 1000 else "خوب" if total_chars > 500 else "متوسط" if total_chars > 100 else "ضعیف"
    
    print(f"\n{'='*60}")
    print(f"📊 بهترین روش: {best_result['method']}")
    print(f"📝 کل کاراکترها: {total_chars:,}")
    print(f"📝 کل کلمات: {total_words:,}")
    print(f"📄 تعداد صفحات: {len(best_result['blocks'])}")
    print(f"⭐ کیفیت: {quality}")
    print(f"{'='*60}\n")
    
    return {
        "extraction_method": best_result["method"],
        "total_characters": total_chars,
        "total_words": total_words,
        "total_blocks": len(best_result["blocks"]),
        "full_text": best_result["text"],
        "blocks": best_result["blocks"],
        "quality": quality,
        "all_methods_tested": results
    }




