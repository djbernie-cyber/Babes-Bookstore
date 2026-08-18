from sqlalchemy import Column, String, Boolean, DateTime, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=True)
    hashed_password = Column(String(255), nullable=True)
    google_id = Column(String(100), unique=True, nullable=True, index=True)
    paypal_customer_id = Column(String(100), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)
    square_customer_id = Column(String(100), nullable=True)
    is_admin = Column(Boolean, default=False)
    free_downloads = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    purchases = relationship("Purchase", back_populates="user")

    def __repr__(self):
        return f"<User {self.id}: {self.email}>"