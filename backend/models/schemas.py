from pydantic import BaseModel, Field
from typing import List, Dict

# Pydantic models by category
class Contract(BaseModel):
    parties: List[str] = Field(description="اسامی طرفین قرارداد")
    subject: str = Field(description="موضوع قرارداد")
    duration: str = Field(description="مدت قرارداد")
    conditions: List[str] = Field(description="شرایط و تعهدات")
    penalties: str = Field(description="جریمه‌ها و ضمانت‌ها")
    signatures: List[str] = Field(description="امضاها")


class Resume(BaseModel):
    name: str = Field(description="نام و نام خانوادگی")
    contact: dict = Field(description="اطلاعات تماس (ایمیل، تلفن)")
    education: List[dict] = Field(description="تحصیلات")
    experience: List[dict] = Field(description="تجربیات کاری")
    skills: List[str] = Field(description="مهارت‌ها")


class Will(BaseModel):
    testator: str = Field(description="نام وصیت‌کننده")
    beneficiaries: List[str] = Field(description="وارثان و ذی‌نفعان")
    assets: List[dict] = Field(description="دارایی‌ها و نحوه تقسیم")
    conditions: List[str] = Field(description="شرایط وصیت")
    executor: str = Field(description="مجری وصیت")


CATEGORY_MODELS = {
    "contract": Contract,
    "resume": Resume,
    "will": Will,
}


class Person(BaseModel):
    id: str
    name: str
    source_ids: List[int] = Field(..., description="IDs بلوک‌های منبع")


class Relation(BaseModel):
    from_id: str
    to_id: str
    type: str
    source_ids: List[int]


class FamilyTree(BaseModel):
    persons: List[Person]
    relations: List[Relation]
    other_data: Dict[str, str] = {}