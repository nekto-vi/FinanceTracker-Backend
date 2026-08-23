import os
import requests
import google.generativeai as genai

# Настройка ИИ
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

def get_pr_diff():
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {"Authorization": f"token {os.getenv('GH_TOKEN')}", "Accept": "application/vnd.github.v3.diff"}
    response = requests.get(url, headers=headers)
    return response.text

def post_comment(comment):
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {"Authorization": f"token {os.getenv('GH_TOKEN')}"}
    requests.post(url, json={"body": comment}, headers=headers)

diff = get_pr_diff()

prompt = f"""
Ты — опытный Python разработчик и эксперт по FastAPI. 
Проведи Code Review этого Pull Request. 
1. Напиши краткое резюме изменений.
2. Найди потенциальные баги или плохие практики.
3. Предложи улучшения (Clean Code, DRY, PEP8).
Отвечай на русском языке в стиле Markdown.

ИЗМЕНЕНИЯ (DIFF):
{diff}
"""

response = model.generate_content(prompt)
post_comment(f"## 🤖 AI Code Review\n\n{response.text}")