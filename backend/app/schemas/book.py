from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class BookStatusEnum(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class BookBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    author: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    isbn: Optional[str] = None

    source: str
    source_id: Optional[str] = None
    source_url: Optional[str] = None

    license_type: str
    license_url: Optional[str] = None

    category: Optional[str] = None
    tags: Optional[List[str]] = None
    language: str = "en"
    page_count: Optional[int] = None
    publication_year: Optional[int] = None


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[BookStatusEnum] = None
    license_verified: Optional[bool] = None


class BookResponse(BookBase):
    id: int
    license_verified: bool
    cover_path: Optional[str] = None
    pdf_path: Optional[str] = None
    epub_path: Optional[str] = None
    status: BookStatusEnum
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookListResponse(BaseModel):
    items: List[BookResponse]
    total: int
    page: int
    page_size: int