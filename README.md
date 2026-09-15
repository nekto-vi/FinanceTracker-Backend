# Finance Tracker — Backend API

REST API бэкенд для мобильного приложения учёта личных финансов [FinanceTracker](https://github.com/nekto-vi/FinanceTracker).

## Стек технологий

- **Язык**: Python 3.12+
- **Фреймворк**: FastAPI (Uvicorn, Starlette)
- **База данных**: PostgreSQL
- **ORM**: SQLAlchemy + Psycopg2
- **Валидация данных**: Pydantic
- **Безопасность**: JWT (python-jose, HS256), хеширование паролей (passlib, bcrypt)
- **AI / LLM**: Локальная нейросеть **Ollama (`qwen2.5:7b`)** для парсинга расходов из текста на естественном языке
- **Контейнеризация**: Docker & Docker Compose

## Быстрый запуск

### Вариант 1. Через Docker Compose (рекомендуется)
```bash
docker compose up -d --build
```
- API будет доступно по адресу: `http://localhost:8000`

### Вариант 2. Локальный запуск (Python)

1. Клонируйте репозиторий и создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Настройте файл `.env`:
```ini
DATABASE_URL=postgresql://user:password@localhost:5432/finance_db
SECRET_KEY=your-secret-key-for-jwt-signing
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

3. Запустите сервер:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Эндпоинты API

Все защищённые маршруты требуют передачи заголовка:  
`Authorization: Bearer <access_token>`

### 1. Авторизация (`/auth`)
- `POST /auth/register` — регистрация нового пользователя (`username`, `password`)
- `POST /auth/login` — вход в систему, возвращает JWT токен доступа

### 2. Счета (`/accounts`)
- `GET /accounts` — получение счетов пользователя («Карта», «Наличные») с текущим балансом

### 3. Категории (`/categories`)
- `GET /categories?month=9&year=2026` — список базовых и пользовательских категорий с суммами трат за месяц
- `POST /categories` — добавление новой категории (`name`, `emoji`, `color`)

### 4. Транзакции (`/transactions`)
- `POST /transactions` — создание транзакции (расход/доход), автопересчёт баланса счёта
- `GET /transactions/history?month=9` — история транзакций за указанный месяц

### 5. Аналитика (`/stats`)
- `GET /stats/weekly?start_date=YYYY-MM-DD` — статистика трат по дням недели для графиков
- `GET /stats/summary?month=9&year=2026` — финансовая сводка (доходы, расходы, прибыль)

### 6. AI-ассистент (`/ai`)
- `POST /ai/process` — автоматическое распознавание траты через Ollama (`qwen2.5:7b`) и добавление расхода
- `GET /ai/messages` — история диалога с ассистентом
- `POST /ai/messages` — сохранение сообщения в чат

## Связь с Frontend
Клиентская часть приложения находится в репозитории [nekto-vi/FinanceTracker](https://github.com/nekto-vi/FinanceTracker).
