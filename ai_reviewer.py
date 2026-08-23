import os
import requests
import google.generativeai as genai
import sys

try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Ошибка настройки ИИ: {e}")
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
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ Ошибка получения diff: {response.status_code}")
        return None
    return response.text

def post_comment(comment):
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    token = os.getenv("GH_TOKEN")
    
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {"Authorization": f"token {token}"}
    
    response = requests.post(url, json={"body": comment}, headers=headers)
    if response.status_code == 201:
        print("✅ Комментарий опубликован!")
    else:
        print(f"❌ Ошибка GitHub: {response.status_code}\n{response.text}")

def run():
    diff = get_pr_diff()
    if not diff:
        return

    prompt = f"""
    Ты — Senior Python Developer. Проведи Code Review изменений в Pull Request.
    
    Твоя задача:
    1. Резюмируй изменения.
    2. Найди баги или косяки в логике FastAPI.
    3. Проверь на соответствие PEP8.
    4. Предложи, как сделать код чище.
    
    Пиши на русском языке, используй Markdown.
    Если всё круто — похвали автора.

    ИЗМЕНЕНИЯ:
    {diff[:15000]} 
    """

    try:
        print("Отправляю запрос в Gemini...")
        response = model.generate_content(prompt)
        
        review_text = f"### 🤖 AI Code Review\n\n{response.text}"
        post_comment(review_text)
        
    except Exception as e:
        print(f"❌ Ошибка ИИ: {e}")

if __name__ == "__main__":
    run()