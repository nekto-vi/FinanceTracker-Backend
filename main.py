from fastapi import FastAPI

# Создаем само приложение
app = FastAPI(
    title="Finance Tracker API",
    description="Бэкенд для управления финансами с ИИ-ассистентом",
    version="0.1.0"
)

# 1. Простая проверка: работает ли сервер?
@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Welcome to Finance Tracker API",
        "docs": "/docs"
    }

# 2. Пример "ручки" для получения списка категорий (пока просто мок-данные)
@app.get("/categories")
async def get_categories():
    return [
        {"id": 1, "name": "Еда", "emoji": "🍔", "color": "#FF9500"},
        {"id": 2, "name": "Транспорт", "emoji": "🚗", "color": "#FF3B30"},
    ]

# 3. Будущая логика для твоего ИИ-агента
@app.post("/ai/process-voice")
async def process_voice_input(text: str):
    # Здесь в будущем будет вызов нейросети
    return {
        "original_text": text,
        "recognized_amount": 500,
        "suggested_category": "Еда",
        "confidence": 0.98
    }