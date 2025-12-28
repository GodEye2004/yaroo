def truncate_text(text: str, max_chars: int = 3000) -> str:
    """محدود کردن متن به تعداد کاراکتر مشخص"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [ادامه متن حذف شد]"

def estimate_tokens(text: str) -> int:
    """تخمین تعداد توکن‌ها (تقریباً 1 توکن = 4 کاراکتر برای فارسی)"""
    return len(text) // 4