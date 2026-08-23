import os
import requests
from google import genai 

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_pr_diff():
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {os.getenv('GH_TOKEN')}",
        "Accept": "application/vnd.github.v3.diff"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Не удалось получить diff: {response.status_code}")
    return response.text

def post_comment(comment):
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {"Authorization": f"token {os.getenv('GH_TOKEN')}"}
    
    response = requests.post(url, json={"body": comment}, headers=headers)
    
    print(f"Попытка отправить комментарий на {url}")
    print(f"Статус ответа GitHub: {response.status_code}")
    if response.status_code != 201:
        print(f"Ошибка от GitHub: {response.text}")
    else:
        print("✅ Комментарий успешно опубликован!")

try:
    diff = get_pr_diff()

    if not diff.strip():
        print("Изменений не найдено.")
        exit(0)

    prompt = f"""
    Ты — Senior Python разработчик. Проведи ревью кода (diff) ниже.
    Твоя задача:
    1. Найди критические ошибки или баги.
    2. Укажи на нарушение PEP8 или плохую типизацию.
    3. Предложи, как сделать код короче и понятнее.
    
    Пиши кратко и по делу. Используй Markdown (заголовки, списки).
    Отвечай на русском языке.

    ИЗМЕНЕНИЯ В КОДЕ:
    {diff}
    """

    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=prompt
    )

    review_text = f"### 🤖 AI Code Review\n\n{response.text}"
    post_comment(review_text)
    print("✅ Ревью успешно опубликовано.")

except Exception as e:
    print(f"❌ Ошибка: {e}")