import os
import requests
from google import genai
import sys

try:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    MODEL_ID = 'gemini-1.5-flash' 
except Exception as e:
    print(f"Ошибка инициализации клиента ИИ: {e}")
    sys.exit(1)

def get_pr_diff():
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    token = os.getenv("GH_TOKEN")
    
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff"
    }
    
    print(f"Запрашиваю diff для PR #{pr_number} в репозитории {repo}...")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Ошибка GitHub API при получении diff: {response.status_code}")
        print(response.text)
        return None
    return response.text

def post_comment(comment):
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    token = os.getenv("GH_TOKEN")
    
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json"
    }
    
    print(f"Отправляю комментарий в GitHub...")
    response = requests.post(url, json={"body": comment}, headers=headers)
    
    if response.status_code == 201:
        print("✅ Ревью успешно опубликовано в Пул-реквесте!")
    else:
        print(f"❌ Ошибка публикации комментария ({response.status_code}):")
        print(response.text)

def run_review():
    diff = get_pr_diff()
    if not diff:
        return

    if len(diff) > 20000:
        diff = diff[:20000] + "\n... (дифф слишком большой, часть обрезана)"

    prompt = f"""
    Ты — Senior Backend Developer. Проведи ревью кода (Python/FastAPI) на основе этого diff.
    
    Твои задачи:
    1. Кратко опиши, что изменилось.
    2. Найди баги, ошибки в логике или безопасности.
    3. Укажи на нарушения PEP8 или плохую типизацию.
    4. Предложи улучшения для производительности.
    
    Пиши на русском языке. Используй Markdown (списки, жирный текст).

    ИЗМЕНЕНИЯ:
    {diff}
    """

    try:
        print(f"Запрашиваю анализ у Gemini ({MODEL_ID})...")
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        
        review_text = f"### 🤖 AI Code Review\n\n{response.text}"
        post_comment(review_text)
        
    except Exception as e:
        print(f"❌ Ошибка при работе с Gemini: {e}")

if __name__ == "__main__":
    run_review()