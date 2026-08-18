from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class BundleBookResponse(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    cover_path: Optional[str] = None

    class Config:
        from_attributes = True


class BundleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    long_description: Optional[str] = None
    price_cents: int = Field(..., ge=0)
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    bundle_type: str = "curated"


class BundleCreate(BundleBase):
    book_ids: List[int]
    cover_image_path: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class BundleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    long_description: Optional[str] = None
    price_cents: Optional[int] = Field(None, ge=0)
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    active: Optional[bool] = None
    featured: Optional[bool] = None
    book_ids: Optional[List[int]] = None


class BundleResponse(BundleBase):
    id: int
    cover_image_path: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    active: bool
    featured: bool
    created_at: datetime
    updated_at: datetime
    books: List[BundleBookResponse] = []

    class Config:
        from_attributes = True


class BundleListResponse(BaseModel):
    items: List[BundleResponse]
    total: int
    page: int
    page_size: int