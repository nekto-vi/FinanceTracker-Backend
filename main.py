import logging
import bcrypt
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, extract 
from datetime import date, datetime, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError
from typing import List, Optional
from pydantic import BaseModel

from config import settings
import database

# --- КОСТЫЛИ И ЛОГИ ---
# Исправляем баг bcrypt в Python 3.12
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

# --- СХЕМЫ ДАННЫХ (Pydantic) ---

class UserAuth(BaseModel):
    username: str
    password: str

class SyncData(BaseModel):
    accounts: List[dict]
    categories: List[dict]
    transactions: List[dict]

# --- ЛОГИКА АВТОРИЗАЦИИ ---

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user_id(authorization: str = Header(None)):
    """Извлекает ID пользователя из JWT токена в заголовке Authorization"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Отсутствует заголовок авторизации")
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Невалидный токен")
        return user_id
    except (JWTError, IndexError):
        raise HTTPException(status_code=401, detail="Ошибка авторизации")

# --- ИНИЦИАЛИЗАЦИЯ (SEEDING) ---

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
        for cat in default_categories:
            db_cat = database.Category(name=cat["name"], emoji=cat["emoji"], color=cat["color"])
            db.add(db_cat)
        db.commit()
        logger.info("✅ Системные категории созданы")

@app.on_event("startup")
def startup_event():
    db = database.SessionLocal()
    try:
        seed_db(db)
    finally:
        db.close()

# --- ЭНДПОИНТЫ АВТОРИЗАЦИИ ---

@app.post("/auth/register")
def register(user: UserAuth, db: Session = Depends(get_db)):
    existing_user = db.query(database.User).filter(database.User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Этот логин уже занят")
    
    new_user = database.User(
        username=user.username,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    db.add_all([
        database.Account(name="Карта", balance=0.0, user_id=new_user.id),
        database.Account(name="Наличные", balance=0.0, user_id=new_user.id)
    ])
    db.commit()
    
    token = create_access_token({"user_id": new_user.id})
    return {"access_token": token, "token_type": "bearer", "username": new_user.username}

@app.post("/auth/login")
def login(user_data: UserAuth, db: Session = Depends(get_db)):
    user = db.query(database.User).filter(database.User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    
    token = create_access_token({"user_id": user.id})
    return {"access_token": token, "token_type": "bearer", "username": user.username}

@app.post("/auth/sync")
def sync_data(data: SyncData, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    for local_acc in data.accounts:
        db_acc = db.query(database.Account).filter(
            database.Account.user_id == user_id, 
            database.Account.name == local_acc['name']
        ).first()
        if db_acc:
            db_acc.balance += local_acc['balance']
    
    for local_tx in data.transactions:
        db_cat = db.query(database.Category).filter(database.Category.name == local_tx.get('category_name')).first()
        db_acc = db.query(database.Account).filter(database.Account.user_id == user_id, database.Account.name == local_tx.get('account_name')).first()
        
        if db_acc:
            new_tx = database.Transaction(
                amount=local_tx['amount'],
                type=local_tx.get('type', 'expense'),
                note=local_tx.get('note'),
                account_id=db_acc.id,
                category_id=db_cat.id if db_cat else None,
                created_at=datetime.utcnow()
            )
            db.add(new_tx)
    
    db.commit()
    return {"status": "success"}

@app.get("/accounts")
def get_accounts(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(database.Account).filter(database.Account.user_id == user_id).all()

@app.get("/categories")
def get_categories(month: int = None, year: int = None, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    m = month or date.today().month
    y = year or date.today().year

    categories = db.query(database.Category).all()
    user_acc_ids = [a.id for a in db.query(database.Account.id).filter(database.Account.user_id == user_id).all()]
    
    result = []
    for cat in categories:
        total_spent = db.query(func.sum(database.Transaction.amount))\
            .filter(database.Transaction.category_id == cat.id)\
            .filter(database.Transaction.account_id.in_(user_acc_ids))\
            .filter(extract('month', database.Transaction.created_at) == m)\
            .filter(extract('year', database.Transaction.created_at) == y)\
            .filter(database.Transaction.type == "expense")\
            .scalar() or 0.0
        
        result.append({
            "id": cat.id, "name": cat.name, "emoji": cat.emoji, "color": cat.color, "amount": total_spent
        })
    return result

@app.post("/transactions")
def create_transaction(tx: database.TransactionCreate, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    account = db.query(database.Account).filter(database.Account.id == tx.account_id, database.Account.user_id == user_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Счет не найден")

    tx_date = datetime.strptime(tx.date, '%Y-%m-%d') if tx.date else datetime.utcnow()

    if tx.type == "expense":
        account.balance -= tx.amount
    else:
        account.balance += tx.amount

    db_tx = database.Transaction(
        amount=tx.amount, account_id=tx.account_id, category_id=tx.category_id,
        type=tx.type, note=tx.note, created_at=tx_date
    )
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)
    return {"status": "success", "new_balance": account.balance}

@app.get("/stats/weekly")
def get_weekly_stats(start_date: str = None, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    if start_date:
        dt = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        dt = date.today()
    
    monday = dt - timedelta(days=dt.weekday())
    user_acc_ids = [a.id for a in db.query(database.Account.id).filter(database.Account.user_id == user_id).all()]
    
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    result = []

    for i in range(7):
        current_day = monday + timedelta(days=i)
        txs = db.query(database.Transaction).filter(
            func.date(database.Transaction.created_at) == current_day,
            database.Transaction.account_id.in_(user_acc_ids),
            database.Transaction.type == "expense"
        ).all()

        segments_map = {}
        for t in txs:
            color = t.category.color if t.category else "#CCC"
            if t.category_id not in segments_map:
                segments_map[t.category_id] = {"amount": 0, "color": color}
            segments_map[t.category_id]["amount"] += t.amount

        result.append({
            "label": day_names[i],
            "date": current_day.strftime("%d.%m"),
            "segments": [{"categoryId": str(cid), "amount": d["amount"], "color": d["color"]} for cid, d in segments_map.items()],
            "transactions": [{
                "id": str(t.id),
                "categoryName": t.category.name if t.category else "Без категории",
                "amount": t.amount,
                "color": t.category.color if t.category else "#8E8E93",
                "note": t.note,
                "time": t.created_at.strftime("%H:%M")
            } for t in txs]
        })
    return result

@app.get("/stats/summary")
def get_monthly_summary(month: int = None, year: int = None, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    m = month or date.today().month
    y = year or date.today().year
    user_acc_ids = [a.id for a in db.query(database.Account.id).filter(database.Account.user_id == user_id).all()]

    inc = db.query(func.sum(database.Transaction.amount)).filter(
        extract('month', database.Transaction.created_at) == m,
        extract('year', database.Transaction.created_at) == y,
        database.Transaction.account_id.in_(user_acc_ids),
        database.Transaction.type == "income"
    ).scalar() or 0.0

    exp = db.query(func.sum(database.Transaction.amount)).filter(
        extract('month', database.Transaction.created_at) == m,
        extract('year', database.Transaction.created_at) == y,
        database.Transaction.account_id.in_(user_acc_ids),
        database.Transaction.type == "expense"
    ).scalar() or 0.0

    return {"profit": inc - exp, "total_income": inc, "total_expense": exp}

@app.get("/transactions/history")
def get_transactions_history(month: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user_acc_ids = [a.id for a in db.query(database.Account.id).filter(database.Account.user_id == user_id).all()]
    return db.query(database.Transaction).filter(
        extract('month', database.Transaction.created_at) == month,
        database.Transaction.account_id.in_(user_acc_ids)
    ).order_by(database.Transaction.created_at.desc()).all()
