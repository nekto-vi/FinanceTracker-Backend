from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func 
import database

app = FastAPI()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/categories")
def read_categories(db: Session = Depends(get_db)):
    categories = db.query(database.Category).all()
    result = []
    for cat in categories:
        total_amount = db.query(func.sum(database.Transaction.amount))\
            .filter(database.Transaction.category_id == cat.id).scalar() or 0
        
        result.append({
            "id": cat.id,
            "name": cat.name,
            "emoji": cat.emoji,
            "color": cat.color,
            "amount": total_amount
        })
    return result

@app.post("/categories")
def create_category(cat: database.CategoryCreate, db: Session = Depends(get_db)):
    db_cat = database.Category(name=cat.name, emoji=cat.icon, color=cat.color)
    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)
    return db_cat

@app.post("/transactions")
def create_transaction(tx: database.TransactionCreate, db: Session = Depends(get_db)):
    db_tx = database.Transaction(amount=tx.amount, category_id=tx.category_id)
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)
    return db_tx