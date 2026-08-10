from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
import database # Импортируем наш файл с БД

app = FastAPI()

# Зависимость для подключения к БД
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/categories")
def read_categories(db: Session = Depends(get_db)):
    # Берем данные из реальной базы
    return db.query(database.Category).all()

@app.post("/categories")
def create_category(cat: database.CategoryCreate, db: Session = Depends(get_db)):
    # Превращаем данные из мобилки в модель базы данных
    db_cat = database.Category(
        name=cat.name,
        emoji=cat.icon, # Сохраняем icon как emoji
        color=cat.color
    )
    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)
    return db_cat