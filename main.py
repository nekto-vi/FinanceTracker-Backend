import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any

import bcrypt
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import BaseModel

import database
from config import settings

if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type('About', (object,), {'__version__': bcrypt.__version__})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Finance Tracker API")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserAuth(BaseModel):
    username: str
    password: str


class SyncData(BaseModel):
    accounts: List[Dict[str, Any]]
    categories: List[Dict[str, Any]]
    transactions: List[Dict[str, Any]]


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user_id(authorization: str = Header(None)) -> int:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Authorization header missing"
        )
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user_id
    except (JWTError, IndexError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")


def get_user_account_ids(db: Session, user_id: int) -> List[int]:
    accounts = db.query(database.Account.id).filter(database.Account.user_id == user_id).all()
    return [acc.id for acc in accounts]


def seed_db(db: Session):
    if db.query(database.Category).count() == 0:
        default_categories = [
            {"name": "Еда", "emoji": "🍔", "color": "#FF9500"},
            {"name": "Транспорт", "emoji": "🚗", "color": "#FF3B30"},
            {"name": "Связь", "emoji": "📱", "color": "#5856D6"},
            {"name": "Здоровье", "emoji": "💊", "color": "#34C759"},
            {"name": "Продукты", "emoji": "🛒", "color": "#FFCC00"},
            {"name": "Развлечения", "emoji": "🍿", "color": "#AF52DE"},
            {"name": "Одежда", "emoji": "👕", "color": "#FF2D55"},
        ]
        for category_data in default_categories:
            category = database.Category(**category_data)
            db.add(category)
        db.commit()


@app.on_event("startup")
def startup_event():
    db = database.SessionLocal()
    try:
        seed_db(db)
    finally:
        db.close()


@app.post("/auth/register")
def register(user: UserAuth, db: Session = Depends(get_db)):
    user_exists = db.query(database.User).filter(database.User.username == user.username).first()
    if user_exists:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = database.User(
        username=user.username,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    default_accounts = [
        database.Account(name="Карта", balance=0.0, user_id=new_user.id),
        database.Account(name="Наличные", balance=0.0, user_id=new_user.id)
    ]
    db.add_all(default_accounts)
    db.commit()
    
    token = create_access_token({"user_id": new_user.id})
    return {"access_token": token, "token_type": "bearer", "username": new_user.username}


@app.post("/auth/login")
def login(user_data: UserAuth, db: Session = Depends(get_db)):
    user = db.query(database.User).filter(database.User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    token = create_access_token({"user_id": user.id})
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@app.post("/auth/sync")
def sync_data(data: SyncData, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    for local_account in data.accounts:
        db_account = db.query(database.Account).filter(
            database.Account.user_id == user_id, 
            database.Account.name == local_account['name']
        ).first()
        if db_account:
            db_account.balance += local_account['balance']
    
    for local_transaction in data.transactions:
        category = db.query(database.Category).filter(
            database.Category.name == local_transaction.get('category_name')
        ).first()
        
        account = db.query(database.Account).filter(
            database.Account.user_id == user_id, 
            database.Account.name == local_transaction.get('account_name')
        ).first()
        
        if account:
            new_transaction = database.Transaction(
                amount=local_transaction['amount'],
                type=local_transaction.get('type', 'expense'),
                note=local_transaction.get('note'),
                account_id=account.id,
                category_id=category.id if category else None,
                created_at=datetime.utcnow()
            )
            db.add(new_transaction)
    
    db.commit()
    return {"status": "success"}


@app.get("/accounts")
def get_accounts(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(database.Account).filter(database.Account.user_id == user_id).all()


@app.get("/categories")
def get_categories(
    month: Optional[int] = None, 
    year: Optional[int] = None, 
    user_id: int = Depends(get_current_user_id), 
    db: Session = Depends(get_db)
):
    target_month = month or date.today().month
    target_year = year or date.today().year
    
    categories = db.query(database.Category).all()
    user_account_ids = get_user_account_ids(db, user_id)
    
    response = []
    for category in categories:
        total_spent = db.query(func.sum(database.Transaction.amount))\
            .filter(database.Transaction.category_id == category.id)\
            .filter(database.Transaction.account_id.in_(user_account_ids))\
            .filter(extract('month', database.Transaction.created_at) == target_month)\
            .filter(extract('year', database.Transaction.created_at) == target_year)\
            .filter(database.Transaction.type == "expense")\
            .scalar() or 0.0
        
        response.append({
            "id": category.id,
            "name": category.name,
            "emoji": category.emoji,
            "color": category.color,
            "amount": total_spent
        })
    return response


@app.post("/transactions")
def create_transaction(
    transaction_data: database.TransactionCreate, 
    user_id: int = Depends(get_current_user_id), 
    db: Session = Depends(get_db)
):
    account = db.query(database.Account).filter(
        database.Account.id == transaction_data.account_id, 
        database.Account.user_id == user_id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if transaction_data.date:
        transaction_date = datetime.strptime(transaction_data.date, '%Y-%m-%d')
    else:
        transaction_date = datetime.utcnow()

    if transaction_data.type == "expense":
        account.balance -= transaction_data.amount
    else:
        account.balance += transaction_data.amount

    new_transaction = database.Transaction(
        amount=transaction_data.amount,
        account_id=transaction_data.account_id,
        category_id=transaction_data.category_id,
        type=transaction_data.type,
        note=transaction_data.note,
        created_at=transaction_date
    )
    db.add(new_transaction)
    db.commit()
    db.refresh(new_transaction)
    
    return {"status": "success", "new_balance": account.balance}


@app.get("/stats/weekly")
def get_weekly_stats(
    start_date: Optional[str] = None, 
    user_id: int = Depends(get_current_user_id), 
    db: Session = Depends(get_db)
):
    if start_date:
        base_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        base_date = date.today()
    
    monday = base_date - timedelta(days=base_date.weekday())
    user_account_ids = get_user_account_ids(db, user_id)
    
    day_labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    weekly_data = []

    for i in range(7):
        current_day = monday + timedelta(days=i)
        transactions = db.query(database.Transaction).filter(
            func.date(database.Transaction.created_at) == current_day,
            database.Transaction.account_id.in_(user_account_ids),
            database.Transaction.type == "expense"
        ).all()

        segments = {}
        for tx in transactions:
            color = tx.category.color if tx.category else "#CCC"
            if tx.category_id not in segments:
                segments[tx.category_id] = {"amount": 0, "color": color}
            segments[tx.category_id]["amount"] += tx.amount

        weekly_data.append({
            "label": day_labels[i],
            "date": current_day.strftime("%d.%m"),
            "segments": [
                {"categoryId": str(cid), "amount": val["amount"], "color": val["color"]} 
                for cid, val in segments.items()
            ],
            "transactions": [
                {
                    "id": str(tx.id),
                    "categoryName": tx.category.name if tx.category else "Без категории",
                    "amount": tx.amount,
                    "color": tx.category.color if tx.category else "#8E8E93",
                    "note": tx.note,
                    "time": tx.created_at.strftime("%H:%M")
                } for tx in transactions
            ]
        })
    return weekly_data


@app.get("/stats/summary")
def get_monthly_summary(
    month: Optional[int] = None, 
    year: Optional[int] = None, 
    user_id: int = Depends(get_current_user_id), 
    db: Session = Depends(get_db)
):
    target_month = month or date.today().month
    target_year = year or date.today().year
    user_account_ids = get_user_account_ids(db, user_id)

    income = db.query(func.sum(database.Transaction.amount)).filter(
        extract('month', database.Transaction.created_at) == target_month,
        extract('year', database.Transaction.created_at) == target_year,
        database.Transaction.account_id.in_(user_account_ids),
        database.Transaction.type == "income"
    ).scalar() or 0.0

    expenses = db.query(func.sum(database.Transaction.amount)).filter(
        extract('month', database.Transaction.created_at) == target_month,
        extract('year', database.Transaction.created_at) == target_year,
        database.Transaction.account_id.in_(user_account_ids),
        database.Transaction.type == "expense"
    ).scalar() or 0.0

    return {
        "profit": income - expenses,
        "total_income": income,
        "total_expense": expenses
    }


@app.get("/transactions/history")
def get_transactions_history(
    month: int, 
    user_id: int = Depends(get_current_user_id), 
    db: Session = Depends(get_db)
):
    user_account_ids = get_user_account_ids(db, user_id)
    return db.query(database.Transaction).filter(
        extract('month', database.Transaction.created_at) == month,
        database.Transaction.account_id.in_(user_account_ids)
    ).order_by(database.Transaction.created_at.desc()).all()