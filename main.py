from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timedelta
from passlib.context import CryptContext
from jose import jwt

from config import settings
import database

app = FastAPI(title="Finance Tracker API")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def seed_db(db: Session):
    user = db.query(database.User).filter(database.User.username == "violetta").first()
    if not user:
        user = database.User(
            username="violetta", 
            hashed_password=pwd_context.hash("12345")
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print("✅ Пользователь Violetta создан")

    if db.query(database.Account).count() == 0:
        card = database.Account(name="Карта", balance=5000.0, user_id=user.id)
        cash = database.Account(name="Наличные", balance=1000.0, user_id=user.id)
        db.add_all([card, cash])
        db.commit()
        print("✅ Дефолтные счета созданы")

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
        print("✅ Базовые категории созданы")

@app.on_event("startup")
def startup_event():
    db = database.SessionLocal()
    try:
        seed_db(db)
    finally:
        db.close()

@app.get("/accounts")
def get_accounts(db: Session = Depends(get_db)):
    return db.query(database.Account).all()

@app.post("/categories")
def create_category(cat: database.CategoryCreate, db: Session = Depends(get_db)):
    db_cat = database.Category(name=cat.name, emoji=cat.icon, color=cat.color)
    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)
    return db_cat

@app.get("/categories")
def get_categories(month: int = None, year: int = None, db: Session = Depends(get_db)):
    today = date.today()
    month = month or today.month
    year = year or today.year
    
    month_str = f"{month:02d}"
    year_str = str(year)

    categories = db.query(database.Category).all()
    result = []
    for cat in categories:
        total_spent = db.query(func.sum(database.Transaction.amount))\
            .filter(database.Transaction.category_id == cat.id)\
            .filter(func.strftime('%m', database.Transaction.created_at) == month_str)\
            .filter(func.strftime('%Y', database.Transaction.created_at) == year_str)\
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
        raise HTTPException(status_code=404, detail="Счет не найден")

    tx_date = datetime.strptime(tx.date, '%Y-%m-%d') if tx.date else datetime.utcnow()

    if tx.type == "expense":
        account.balance -= tx.amount
    else:
        account.balance += tx.amount

    db_tx = database.Transaction(
        amount=tx.amount,
        account_id=tx.account_id,
        category_id=tx.category_id,
        type=tx.type,
        note=tx.note,
        created_at=tx_date
    )
    
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)
    return {"status": "success", "new_balance": account.balance}

@app.get("/stats/weekly")
def get_weekly_stats(start_date: str = None, db: Session = Depends(get_db)):
    if start_date:
        dt = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        dt = datetime.utcnow().date()
    
    monday = dt - timedelta(days=dt.weekday())
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    result = []

    for i in range(7):
        current_day = monday + timedelta(days=i)
        txs = db.query(database.Transaction).filter(
            func.date(database.Transaction.created_at) == current_day,
            database.Transaction.type == "expense"
        ).all()

        segments = []
        segments_map = {}
        for t in txs:
            if t.category_id not in segments_map:
                segments_map[t.category_id] = {"amount": 0, "color": t.category.color if t.category else "#CCC"}
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
def get_monthly_summary(month: int = None, year: int = None, db: Session = Depends(get_db)):
    today = date.today()
    m = f"{(month or today.month):02d}"
    y = str(year or today.year)

    inc = db.query(func.sum(database.Transaction.amount)).filter(func.strftime('%m', database.Transaction.created_at) == m, func.strftime('%Y', database.Transaction.created_at) == y, database.Transaction.type == "income").scalar() or 0.0
    exp = db.query(func.sum(database.Transaction.amount)).filter(func.strftime('%m', database.Transaction.created_at) == m, func.strftime('%Y', database.Transaction.created_at) == y, database.Transaction.type == "expense").scalar() or 0.0

    return {"profit": inc - exp, "total_income": inc, "total_expense": exp}

@app.get("/transactions/history")
def get_transactions_history(month: int, db: Session = Depends(get_db)):
    month_str = f"{month:02d}"
    return db.query(database.Transaction).filter(func.strftime('%m', database.Transaction.created_at) == month_str).order_by(database.Transaction.created_at.desc()).all()