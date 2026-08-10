from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
import database

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
def get_categories(db: Session = Depends(get_db)):
    categories = db.query(database.Category).all()
    
    result = []
    for cat in categories:
        total_spent = db.query(func.sum(database.Transaction.amount))\
            .filter(database.Transaction.category_id == cat.id)\
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