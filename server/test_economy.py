"""Automatic production and safe spending against an isolated database."""
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
    city_id, other_id = first["city"]["id"], second["city"]["id"]

    assert client.post("/api/economy/use", json={"recipe_id": "cook_meals"}, headers=headers).status_code == 410
    with main.database() as db:
        db.execute("UPDATE cities SET last_income=last_income-21600,goods=? WHERE id=?", (json.dumps({"meals": 7}), city_id))
    mine = client.get("/api/me", headers=headers).json()
    goods = mine["economy"]["goods"]
    assert goods["meals"] > 7 and goods["tools"] + goods["planks"] > 0 and goods["notes"] > 0
    assert mine["economy"]["last_production"]["hours"] == 6
    assert mine["economy"]["last_production"]["services_used"]["care"] > 0
    assert mine["economy"]["last_production"]["services_expired"]["care"] > 0
    assert "recipes" not in mine["economy"] and "services" not in mine["economy"]
    assert client.get("/api/me", headers=headers).json()["economy"]["goods"] == goods
    assert client.get("/api/me", headers=other_headers).json()["economy"]["goods"]["meals"] == 0

    # Building and research costs are charged once and only to the owner.
    main.llm_story = lambda event, actor, target, success, deltas, actor_traits, target_traits: "The city celebrated its new word."
    with main.database() as db:
        db.execute("INSERT INTO prepared_buildings VALUES (?,?,?,?,?,?)", ("plan", city_id, "pantry", "Soup House", "A very sturdy kitchen.", int(time.time())))
        db.execute("UPDATE cities SET goods=? WHERE id=?", (json.dumps({**goods, "meals": 3, "notes": 3}), city_id))
        db.execute("UPDATE cities SET tech=30,cash=100,tech_nodes=? WHERE id=?", (json.dumps(["city_charter"]), city_id))
    assert client.post("/api/buildings", json={"offer_id": "plan"}, headers=other_headers).status_code == 404
    assert client.post("/api/buildings", json={"offer_id": "plan"}, headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).json()["economy"]["goods"]["meals"] == 1
    researched = client.post("/api/research", json={"node_id": "coin_counter"}, headers=headers)
    assert researched.status_code == 200, researched.text
    assert client.get("/api/me", headers=headers).json()["economy"]["goods"]["notes"] == 2

    # A goods-only trade moves inventory atomically and cannot overdraw either city.
    with main.database() as db:
        db.execute("UPDATE cities SET goods=? WHERE id=?", (json.dumps({"ore": 3}), other_id))
    trade = client.post("/api/trades", json={"target_city_id": other_id, "offer_good": "meals", "offer_good_amount": 1,
                                                "request_good": "ore", "request_good_amount": 2}, headers=headers)
    assert trade.status_code == 200, trade.text
    accepted = client.post(f"/api/trades/{trade.json()['id']}/accept", headers=other_headers)
    assert accepted.status_code == 200, accepted.text
    assert client.get("/api/me", headers=headers).json()["economy"]["goods"]["ore"] == goods["ore"] + 2
    assert client.get("/api/me", headers=other_headers).json()["economy"]["goods"]["meals"] == 1
    with main.database() as db:
        db.execute("UPDATE trade_offers SET created_at=created_at-61 WHERE id=?", (trade.json()["id"],))
    assert client.post("/api/trades", json={"target_city_id": other_id, "offer_good": "ore", "offer_good_amount": 100}, headers=headers).status_code == 409
    before_sender = client.get("/api/me", headers=headers).json()["economy"]["goods"]
    before_target = client.get("/api/me", headers=other_headers).json()["economy"]["goods"]
    impossible = client.post("/api/trades", json={"target_city_id": other_id, "request_good": "ore", "request_good_amount": 100}, headers=headers)
    assert impossible.status_code == 200, impossible.text
    refused = client.post(f"/api/trades/{impossible.json()['id']}/accept", headers=other_headers)
    assert refused.status_code == 409
    assert client.get("/api/me", headers=headers).json()["economy"]["goods"] == before_sender
    assert client.get("/api/me", headers=other_headers).json()["economy"]["goods"] == before_target

    with main.database() as db:
        db.execute("INSERT INTO alien_knowledge VALUES (?,?)", (city_id, "Zhaaru"))
        db.execute("INSERT INTO chaos_offers (id,city_id,template_id,title,tagline,created_at,alien_word) VALUES (?,?,?,?,?,?,?)", ("alien-offer", city_id, "library_swap", "The Library Shuffle", "Books switched shelves without permission.", int(time.time()), "Vektil"))
    assert "Zhaaru" not in client.get("/api/me", headers=other_headers).json()["alien_words"]
    result = client.post("/api/events", json={"event_id": "alien-offer"}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["learned_word"] == {"Vektil": "festival"}

print("Automatic production, costs, trade conservation, and alien language: PASS")
