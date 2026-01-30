from typing import Optional, List

from pydantic import BaseModel

class YuqueBookItem(BaseModel):
    book_slug: Optional[str] = None
    book_slug_name: Optional[str] = None

    @staticmethod
    def from_dict(data: dict):
        return YuqueBookItem(**data)

class YuqueResourceSchema(BaseModel):
    token: Optional[str] = None
    group_login: Optional[str] = None
    book_slug_details: Optional[List[YuqueBookItem]] = None

    @staticmethod
    def from_dict(data: dict):
        return YuqueBookItem(**data)
