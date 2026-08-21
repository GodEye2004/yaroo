from sqlalchemy import Column, Integer, JSON, String

from db_config import Base


class TenantData(Base):
    __tablename__ = "ai_assist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    category = Column(String, nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    related_sources = Column(JSON, nullable=False, default=list)
