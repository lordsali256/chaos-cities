"""Goods persistence, expiring services, recipe ownership, and alien learning."""
import json
import os
import tempfile
import time

with tempfile.TemporaryDirectory() as folder:
    os.environ["DATABASE_PATH"] = f"{folder}/economy.db"
    import main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    first = client.post("/api/register", json={"player": "Maker One", "city": "Workshop One"}).json()
    second = client.post("/api/register", json={"player": "Maker Two", "city": "Workshop Two"}).json()
    headers = {"Authorization": f"Bearer {first['city_key']}"}
    other_headers = {"Authorization": f"Bearer {second['city_key']}"}
    city_id = first["city"]["id"]
    assert client.post("/api/economy/use", json={"recipe_id": "cook_meals"}).status_code == 401
    assert client.post("/api/economy/use", json={"recipe_id": "invalid"}, headers=headers).status_code == 404
    with main.database() as db:
        db.execute("UPDATE cities SET last_income=last_income-7200 WHERE id=?", (city_id,))
    mine = client.get("/api/me", headers=headers).json()
    assert mine["economy"]["goods"]["grain"] >= 4
    assert mine["economy"]["goods"]["timber"] >= 2
    assert mine["economy"]["services"]["care"] >= 1
    before_other = client.get("/api/me", headers=other_headers).json()["economy"]
    cooked = client.post("/api/economy/use", json={"recipe_id": "cook_meals"}, headers=headers)
    assert cooked.status_code == 200, cooked.text
    assert cooked.json()["economy"]["goods"]["meals"] == 2
    assert cooked.json()["economy"]["services"]["care"] == mine["economy"]["services"]["care"] - 1
    fed = client.post("/api/economy/use", json={"recipe_id": "share_meal"}, headers=headers)
    assert fed.status_code == 200, fed.text
    assert fed.json()["economy"]["goods"]["meals"] == 1
    assert fed.json()["economy"]["services"]["care"] == mine["economy"]["services"]["care"]
    assert client.get("/api/me", headers=other_headers).json()["economy"] == before_other
    with main.database() as db:
        row = db.execute("SELECT goods FROM cities WHERE id=?", (city_id,)).fetchone()
        assert json.loads(row["goods"])["meals"] == 1
        db.execute("UPDATE city_services SET period=period-1,care=0,craft=0,insight=0 WHERE city_id=?", (city_id,))
    refreshed = client.get("/api/me", headers=headers).json()["economy"]
    assert refreshed["services"] == main.service_allowance(client.get("/api/me", headers=headers).json()["city"])
    assert refreshed["goods"]["meals"] == 1
    with main.database() as db:
        db.execute("INSERT INTO alien_knowledge VALUES (?,?)", (city_id, "Zhaaru"))
    assert client.get("/api/me", headers=headers).json()["alien_words"]["Zhaaru"] == "neighbor"
    assert "Zhaaru" not in client.get("/api/me", headers=other_headers).json()["alien_words"]
    main.llm_story = lambda event, actor, target, success, deltas, actor_traits, target_traits: "The city celebrated its new word."
    with main.database() as db:
        db.execute("INSERT INTO chaos_offers (id,city_id,template_id,title,tagline,created_at,alien_word) VALUES (?,?,?,?,?,?,?)", ("alien-offer", city_id, "library_swap", "The Library Shuffle", "Books switched shelves without permission.", int(time.time()), "Vektil"))
    offer = client.get("/api/me", headers=headers).json()["events"]
    assert any(item["id"] == "alien-offer" and item["name"].startswith("Vektil ") for item in offer)
    result = client.post("/api/events", json={"event_id": "alien-offer"}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["learned_word"] == {"Vektil": "festival"}
    assert client.get("/api/me", headers=headers).json()["alien_words"]["Vektil"] == "festival"
    assert "Vektil" not in client.get("/api/me", headers=other_headers).json()["alien_words"]

print("Economy and alien language checks passed")
