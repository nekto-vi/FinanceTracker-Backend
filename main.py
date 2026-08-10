from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
import database

from datetime import date, datetime, timedelta

app = FastAPI(title="Finance Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/users")
def create_user(name: str, db: Session = Depends(get_db)):
    db_user = database.User(name=name)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/accounts")
def create_account(name: str, balance: float, user_id: int, db: Session = Depends(get_db)):
    db_account = database.Account(name=name, balance=balance, user_id=user_id)
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@app.get("/accounts")
def get_accounts(db: Session = Depends(get_db)):
    return db.query(database.Account).all()

@app.post("/categories")
def create_category(cat: database.CategoryCreate, db: Session = Depends(get_db)):
    db_cat = database.Category(
        name=cat.name,
        emoji=cat.icon, 
        color=cat.color
    )
    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)
    return db_cat

@app.get("/categories")
def get_categories(month: int = None, db: Session = Depends(get_db)):
    categories = db.query(database.Category).all()
    
    if month is None:
        month = date.today().month
    
    result = []
    for cat in categories:
        total_spent = db.query(func.sum(database.Transaction.amount))\
            .filter(database.Transaction.category_id == cat.id)\
            .filter(func.strftime('%m', database.Transaction.created_at) == f"{month:02d}")\
            .filter(database.Transaction.type == "expense")\
            .scalar() or 0.0
        
        result.append({
            "id": cat.id,
            "name": cat.name,
            "emoji": cat.emoji,
            "color": cat.color,
            "amount": total_spent
        })
    return result

@app.post("/transactions")
def create_transaction(tx: database.TransactionCreate, db: Session = Depends(get_db)):
    account = db.query(database.Account).filter(database.Account.id == tx.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if tx.type == "expense":
        account.balance -= tx.amount
    else:
        account.balance += tx.amount

    db_tx = database.Transaction(
        amount=tx.amount,
        account_id=tx.account_id,
        category_id=tx.category_id,
        type=tx.type
    )
    
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)
    
    return {
        "status": "success",
        "transaction_id": db_tx.id,
        "new_balance": account.balance
    }

@app.get("/stats/weekly")
def get_weekly_stats(db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())
    
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    result = []

    for i in range(7):
        current_day = start_of_week + timedelta(days=i)

        txs = db.query(database.Transaction).filter(
            func.date(database.Transaction.created_at) == current_day,
            database.Transaction.type == "expense"
        ).all()

        segments_map = {}
        for t in txs:
            cat_color = t.category.color if t.category else "#D1D1D6"
            cat_id = t.category_id
            
            if cat_id not in segments_map:
                segments_map[cat_id] = {"amount": 0, "color": cat_color}
            
            segments_map[cat_id]["amount"] += t.amount

        segments = [
            {"categoryId": str(cid), "amount": data["amount"], "color": data["color"]}
            for cid, data in segments_map.items()
        ]

        transactions_list = [{
            "id": str(t.id),
            "categoryId": str(t.category_id),
            "categoryName": t.category.name if t.category else "Без категории",
            "amount": t.amount,
            "color": t.category.color if t.category else "#8E8E93",
            "note": f"Трата №{t.id}", 
            "time": t.created_at.strftime("%H:%M")
        } for t in txs]

        result.append({
            "label": day_names[i],
            "segments": segments,
            "transactions": transactions_list
        })
        
    return result

@app.get("/stats/summary")
def get_monthly_summary(month: int = None, db: Session = Depends(get_db)):
    if month is None:
        month = date.today().month

    total_income = db.query(func.sum(database.Transaction.amount))\
        .filter(func.strftime('%m', database.Transaction.created_at) == f"{month:02d}")\
        .filter(database.Transaction.type == "income")\
        .scalar() or 0.0

    total_expense = db.query(func.sum(database.Transaction.amount))\
        .filter(func.strftime('%m', database.Transaction.created_at) == f"{month:02d}")\
        .filter(database.Transaction.type == "expense")\
        .scalar() or 0.0

    return {
        "profit": total_income - total_expense,
        "total_income": total_income,
        "total_expense": total_expense
    }