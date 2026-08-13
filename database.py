from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from config import settings

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True) 
    hashed_password = Column(String, nullable=True) 
    accounts = relationship("Account", back_populates="owner")

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    balance = Column(Float, default=0.0)
    
    owner = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    emoji = Column(String)
    color = Column(String)
    transactions = relationship("Transaction", back_populates="category")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float)
    type = Column(String) 
    created_at = Column(DateTime, default=datetime.utcnow)
    note = Column(String, nullable=True)
    
    account_id = Column(Integer, ForeignKey("accounts.id"))
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")

class CategoryCreate(BaseModel):
    name: str
    icon: str
    color: str

class TransactionCreate(BaseModel):
    amount: float
    account_id: int
    category_id: int
    type: str = "expense"
    note: Optional[str] = None 
    date: Optional[str] = None 

Base.metadata.create_all(bind=engine)