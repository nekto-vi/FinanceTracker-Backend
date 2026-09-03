import pytest

def test_register_user(client):
    response = client.post(
        "/auth/register",
        json={"username": "testuser", "password": "password123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["username"] == "testuser"

def test_login_user(client):
    client.post("/auth/register", json={"username": "loginuser", "password": "password123"})
    
    response = client.post("/auth/login", json={"username": "loginuser", "password": "password123"})
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_create_category(client):
    reg_res = client.post("/auth/register", json={"username": "category_user", "password": "123"})
    headers = {"Authorization": f"Bearer {reg_res.json()['access_token']}"}

    response = client.post(
        "/categories",
        headers=headers,
        json={"name": "Собака", "emoji": "🐶", "color": "#D1D1D1"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Собака"
    assert response.json()["emoji"] == "🐶"

def test_transaction_updates_balance(client):
    reg_res = client.post("/auth/register", json={"username": "wallet_user", "password": "123"})
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    accs_res = client.get("/accounts", headers=headers)
    account_id = accs_res.json()[0]["id"]
    
    client.post("/transactions", headers=headers, json={
        "amount": 1000,
        "account_id": account_id,
        "category_id": 1,
        "type": "income",
        "date": "2026-08-17"
    })

    client.post("/transactions", headers=headers, json={
        "amount": 400,
        "account_id": account_id,
        "category_id": 1,
        "type": "expense",
        "date": "2026-08-17"
    })

    final_accs = client.get("/accounts", headers=headers)
    assert final_accs.json()[0]["balance"] == 600.0


def test_expense_updates_category_total_and_account_balance(client):
    reg_res = client.post("/auth/register", json={"username": "expense_total_user", "password": "123"})
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    account_id = client.get("/accounts", headers=headers).json()[0]["id"]
    category = client.post(
        "/categories",
        headers=headers,
        json={"name": "Связь", "emoji": "📱", "color": "#5856D6"}
    ).json()

    client.post(
        "/transactions",
        headers=headers,
        json={
            "amount": 10,
            "account_id": account_id,
            "category_id": category["id"],
            "type": "expense",
            "date": "2026-09-02"
        }
    )

    account = client.get("/accounts", headers=headers).json()[0]
    categories = client.get("/categories", params={"month": 9, "year": 2026}, headers=headers).json()

    assert account["balance"] == -10.0
    assert any(cat["name"] == "Связь" and cat["amount"] == 10.0 for cat in categories)


def test_categories_are_user_scoped_but_defaults_are_shared(client):
    first = client.post("/auth/register", json={"username": "alice_cat", "password": "123"})
    second = client.post("/auth/register", json={"username": "bob_cat", "password": "123"})

    first_headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}

    client.post("/categories", headers=first_headers, json={"name": "Собака", "emoji": "🐶", "color": "#D1D1D1"})

    first_categories = client.get("/categories", headers=first_headers).json()
    second_categories = client.get("/categories", headers=second_headers).json()

    assert any(cat["name"] == "Собака" for cat in first_categories)
    assert not any(cat["name"] == "Собака" for cat in second_categories)
    assert any(cat["name"] == "Продукты" for cat in first_categories)
    assert any(cat["name"] == "Продукты" for cat in second_categories)