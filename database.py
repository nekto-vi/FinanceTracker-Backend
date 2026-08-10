from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel

SQLALCHEMY_DATABASE_URL = "sqlite:///./finance.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель для SQLAlchemy (База данных)
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    emoji = Column(String)
    color = Column(String)

# Схема для Pydantic (чтобы FastAPI принимал данные из мобилки)
class CategoryCreate(BaseModel):
    name: str
    icon: str # Мобилка присылает icon
    color: str

Base.metadata.create_all(bind=engine)