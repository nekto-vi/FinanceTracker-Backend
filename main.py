import logging
import bcrypt
import json
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, extract 
from datetime import date, datetime, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import inspect, text
import requests

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from config import settings
import database

# Исправление бага bcrypt
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type('About', (object,), {'__version__': bcrypt.__version__})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Finance Tracker API")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
client_ai = None
if settings.GEMINI_API_KEY and genai is not None:
    client_ai = genai.Client(api_key=settings.GEMINI_API_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- СХЕМЫ ДАННЫХ ---
class UserAuth(BaseModel):
    username: str
    password: str

class AIRequest(BaseModel):
    text: str

# --- ЛОГИКА АВТОРИЗАЦИИ ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user_id(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Отсутствует заголовок Authorization")
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Невалидный токен")
        return user_id
    except (JWTError, IndexError):
        raise HTTPException(status_code=401, detail="Ошибка авторизации")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def ensure_default_categories(db: Session):
    default_categories = [
        {"name": "Еда", "emoji": "🍔", "color": "#FF9500"},
        {"name": "Транспорт", "emoji": "🚗", "color": "#FF3B30"},
        {"name": "Связь", "emoji": "📱", "color": "#5856D6"},
        {"name": "Здоровье", "emoji": "💊", "color": "#34C759"},
        {"name": "Продукты", "emoji": "🛒", "color": "#FFCC00"},
        {"name": "Развлечения", "emoji": "🍿", "color": "#AF52DE"},
        {"name": "Одежда", "emoji": "👕", "color": "#FF2D55"},
    ]

    existing_global = db.query(database.Category).filter(database.Category.user_id.is_(None)).all()
    existing_names = {cat.name for cat in existing_global}

    for cat in default_categories:
        if cat["name"] not in existing_names:
            db.add(database.Category(name=cat["name"], emoji=cat["emoji"], color=cat["color"], user_id=None))

    db.commit()


# --- ИИ АГЕНТ ---

def parse_ai_json_response(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        if "```json" in text:
            text = text.split("```json", 1)[1]
        elif "```" in text:
            text = text.split("```", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


def call_ollama(prompt: str) -> str:
    if not settings.OLLAMA_ENABLED:
        raise RuntimeError("Ollama отключён в настройках")

    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    response = requests.post(
        url,
        json={
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        },
        timeout=120,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"Ollama API error: {response.status_code} {response.text}")

    data = response.json()
    if "response" not in data:
        raise RuntimeError(f"Неверный ответ Ollama: {data}")

    return data["response"]


def generate_ai_json(prompt: str) -> str:
    if settings.OLLAMA_ENABLED:
        try:
            return call_ollama(prompt)
        except Exception as exc:
            logger.warning(f"Ollama не отвечает, пробуем fallback на Gemini: {exc}")

    if client_ai is not None:
        response = client_ai.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json'
            )
        )
        return response.text

    raise RuntimeError("Нет доступного ИИ провайдера. Подключите Ollama или GEMINI_API_KEY.")


@app.post("/ai/process")
async def process_ai_transaction(req: AIRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    # 1. Получаем текущие категории и счета юзера
    categories = db.query(database.Category).filter(
        (database.Category.user_id == user_id) | (database.Category.user_id.is_(None))
    ).all()
    accounts = db.query(database.Account).filter(database.Account.user_id == user_id).all()

    if not accounts:
        raise HTTPException(status_code=400, detail="У вас нет активных счетов для записи трат")

    cat_list = ", ".join([f"{c.name} (id:{c.id})" for c in categories])
    acc_list = ", ".join([f"{a.name} (id:{a.id})" for a in accounts])

    prompt = f"""
    Ты — финансовый ассистент. Извлеки данные о транзакции из текста пользователя.
    Текст: "{req.text}"
    
    Доступные категории: {cat_list}
    Доступные счета пользователя: {acc_list}
    Сегодня: {date.today().isoformat()}

    Верни JSON в формате:
    {{
        "amount": float,
        "category_id": int,
        "account_id": int,
        "note": "краткое описание",
        "date": "YYYY-MM-DD"
    }}
    Правила:
    - Если категория не указана точно, выбери самую близкую.
    - Если счет не указан, используй id счета "Карта".
    """

    try:
        ai_response = generate_ai_json(prompt)
        ai_data = parse_ai_json_response(ai_response)

        category = db.query(database.Category).filter(
            database.Category.id == ai_data["category_id"],
            (database.Category.user_id == user_id) | (database.Category.user_id.is_(None))
        ).first()

        if category is None:
            category = categories[0] if categories else None

        # 3. Валидация счета и списание
        account = db.query(database.Account).filter(
            database.Account.id == ai_data["account_id"],
            database.Account.user_id == user_id
        ).first()

        if not account:
            account = accounts[0]

        account.balance -= ai_data["amount"]

        db_tx = database.Transaction(
            amount=ai_data["amount"],
            account_id=account.id,
            category_id=category.id if category else None,
            type="expense",
            note=ai_data["note"],
            created_at=datetime.strptime(ai_data["date"], '%Y-%m-%d')
        )
        db.add(db_tx)
        db.commit()
        
        return {"status": "success", "data": ai_data}

    except Exception as e:
        logger.error(f"AI error: {e}")
        raise HTTPException(status_code=500, detail="ИИ не смог распознать запрос. Попробуйте проще.")

@app.on_event("startup")
def startup_event():
    db = database.SessionLocal()
    try:
        columns = inspect(db.bind).get_columns("categories")
        if not any(column["name"] == "user_id" for column in columns):
            db.execute(text("ALTER TABLE categories ADD COLUMN user_id INTEGER"))
            db.commit()

        ensure_default_categories(db)
    finally:
        db.close()

@app.post("/auth/register")
def register(user: UserAuth, db: Session = Depends(get_db)):
    if db.query(database.User).filter(database.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Этот логин уже занят")
    new_user = database.User(username=user.username, hashed_password=hash_password(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    db.add_all([
        database.Account(name="Карта", balance=0.0, user_id=new_user.id),
        database.Account(name="Наличные", balance=0.0, user_id=new_user.id)
    ])
    db.commit()
    return {"access_token": create_access_token({"user_id": new_user.id}), "token_type": "bearer", "username": new_user.username}

@app.post("/auth/login")
def login(user_data: UserAuth, db: Session = Depends(get_db)):
    user = db.query(database.User).filter(database.User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    return {"access_token": create_access_token({"user_id": user.id}), "token_type": "bearer", "username": user.username}

@app.get("/accounts")
def get_accounts(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(database.Account).filter(database.Account.user_id == user_id).all()

@app.post("/categories")
def create_category(cat: database.CategoryCreate, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    existing = db.query(database.Category).filter(
        database.Category.name == cat.name,
        (database.Category.user_id == user_id) | (database.Category.user_id.is_(None))
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Такая категория уже существует")

    new_category = database.Category(name=cat.name, emoji=cat.emoji, color=cat.color, user_id=user_id)
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    return new_category


@app.get("/categories")
def get_categories(month: int = None, year: int = None, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    ensure_default_categories(db)
    m, y = month or date.today().month, year or date.today().year
    categories = db.query(database.Category).filter(
        (database.Category.user_id == user_id) | (database.Category.user_id.is_(None))
    ).all()
    user_acc_ids = [a.id for a in db.query(database.Account.id).filter(database.Account.user_id == user_id).all()]
    result = []
    for cat in categories:
        total = 0.0
        if user_acc_ids:
            total = db.query(func.sum(database.Transaction.amount)).filter(
                database.Transaction.category_id == cat.id,
                database.Transaction.account_id.in_(user_acc_ids),
                extract('month', database.Transaction.created_at) == m,
                extract('year', database.Transaction.created_at) == y,
                database.Transaction.type == "expense"
            ).scalar() or 0.0
        result.append({"id": cat.id, "name": cat.name, "emoji": cat.emoji, "color": cat.color, "amount": total})
    return result

@app.post("/transactions")
def create_transaction(tx: database.TransactionCreate, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    if tx.amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть больше нуля")

    if tx.type not in ("expense", "income"):
        raise HTTPException(status_code=400, detail="Неверный тип операции")

    account = db.query(database.Account).filter(database.Account.id == tx.account_id, database.Account.user_id == user_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Счет не найден")

    if tx.type == "expense":
        if tx.category_id is None:
            raise HTTPException(status_code=400, detail="Для расхода нужна категория")
        category = db.query(database.Category).filter(
            database.Category.id == tx.category_id,
            (database.Category.user_id == user_id) | (database.Category.user_id.is_(None))
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Категория не найдена")
        account.balance -= tx.amount
    else:
        account.balance += tx.amount

    tx_date = datetime.strptime(tx.date, '%Y-%m-%d') if tx.date else datetime.utcnow()
    db_tx = database.Transaction(amount=tx.amount, account_id=tx.account_id, category_id=tx.category_id, type=tx.type, note=tx.note, created_at=tx_date)
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)
    return {"status": "success", "new_balance": account.balance}

@app.get("/stats/weekly")
def get_weekly_stats(start_date: str = None, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    dt = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else date.today()
    monday = dt - timedelta(days=dt.weekday())
    user_acc_ids = [a.id for a in db.query(database.Account.id).filter(database.Account.user_id == user_id).all()]
    day_names, result = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], []
    for i in range(7):
        current_day = monday + timedelta(days=i)
        txs = db.query(database.Transaction).filter(func.date(database.Transaction.created_at) == current_day, database.Transaction.account_id.in_(user_acc_ids), database.Transaction.type == "expense").all() if user_acc_ids else []
        sm = {}
        for t in txs:
            c = t.category.color if t.category else "#CCC"
            if t.category_id not in sm: sm[t.category_id] = {"amount": 0, "color": c}
            sm[t.category_id]["amount"] += t.amount
        result.append({
            "label": day_names[i], "date": current_day.strftime("%d.%m"),
            "segments": [{"categoryId": str(cid), "amount": d["amount"], "color": d["color"]} for cid, d in sm.items()],
            "transactions": [{"id": str(t.id), "categoryName": t.category.name if t.category else "---", "amount": t.amount, "color": t.category.color if t.category else "#8E8E93", "note": t.note, "time": t.created_at.strftime("%H:%M")} for t in txs]
        })
    return result

@app.get("/stats/summary")
def get_monthly_summary(month: int = None, year: int = None, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    m, y = month or date.today().month, year or date.today().year
    user_acc_ids = [a.id for a in db.query(database.Account.id).filter(database.Account.user_id == user_id).all()]
    if not user_acc_ids: return {"profit": 0.0, "total_income": 0.0, "total_expense": 0.0}
    inc = db.query(func.sum(database.Transaction.amount)).filter(extract('month', database.Transaction.created_at) == m, extract('year', database.Transaction.created_at) == y, database.Transaction.account_id.in_(user_acc_ids), database.Transaction.type == "income").scalar() or 0.0
    exp = db.query(func.sum(database.Transaction.amount)).filter(extract('month', database.Transaction.created_at) == m, extract('year', database.Transaction.created_at) == y, database.Transaction.account_id.in_(user_acc_ids), database.Transaction.type == "expense").scalar() or 0.0
    return {"profit": inc - exp, "total_income": inc, "total_expense": exp}

@app.get("/transactions/history")
def get_transactions_history(month: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user_acc_ids = [a.id for a in db.query(database.Account.id).filter(database.Account.user_id == user_id).all()]
    if not user_acc_ids: return []
    return db.query(database.Transaction).filter(extract('month', database.Transaction.created_at) == month, database.Transaction.account_id.in_(user_acc_ids)).order_by(database.Transaction.created_at.desc()).all()