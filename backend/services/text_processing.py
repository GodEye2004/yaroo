import unicodedata
import re
from hazm import Normalizer

normalizer = Normalizer()

def deep_clean_farsi_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("‌", " ").replace("\u200c", " ")
    text = normalizer.normalize(text)
    return text.strip()

def looks_garbled(text: str) -> bool:
    bad_patterns = [
        r"[اآبپتثجچحخدذرزسشصضطظعغفقکگلمنوهی]{1,2}\s[اآبپتثجچحخدذرزسشصضطظعغفقکگلمنوهی]{1,2}",
        r"[ﮐﻟﻣﻧﻫﻳﺍﺏﺕﺩﺭﺯﺱﺵﺹﺿﻁﻅﻉﻍﻑﻕﻙﻙﻝﻡﻥﻩﻱ]",
    ]
    for pattern in bad_patterns:
        if re.search(pattern, text):
            return True
    return False