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
    
    # Пытаемся войти
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