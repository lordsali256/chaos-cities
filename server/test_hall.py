"""Town Hall rewards and limits against an isolated temporary database."""
import os
import tempfile
import time
import json

with tempfile.TemporaryDirectory() as folder:
    os.environ["DATABASE_PATH"] = f"{folder}/hall.db"
    import main
    from fastapi.testclient import TestClient

    main.hall_story = lambda city, target, title, story, changes: (title, story)
    client = TestClient(main.app)
    first = client.post("/api/register", json={"player": "Mayor One", "city": "Halltown"}).json()
    second = client.post("/api/register", json={"player": "Mayor Two", "city": "Neighborville"}).json()
    headers = {"Authorization": f"Bearer {first['city_key']}"}
    rival_headers = {"Authorization": f"Bearer {second['city_key']}"}
    city_id, rival_id = first["city"]["id"], second["city"]["id"]
    day = int(time.time()) // main.DAY_SECONDS
    assert client.get("/api/hall").status_code == 401
    hall = client.get("/api/hall", headers=headers).json()
    assert len(hall["goals"]) == 3 and len(hall["achievements"]) == 7
    assert hall["weather"] == main.hall_weather(city_id, day, first["city"]["weirdness"])
    assert hall["my_rank"] in (1, 2) and len(hall["rankings"]) == 2

    def action(name, **details):
        return client.post("/api/hall/actions", json={"action": name, **details}, headers=headers)

    assert action("unknown").status_code == 400
    assert action("checkin").status_code == 200
    assert action("checkin").status_code == 409
    checked = client.get("/api/hall", headers=headers).json()
    assert checked["streak"] == 1 and not checked["checkin_available"]
    assert checked["goals"][0]["done"]
    assert action("goal", goal_id="checkin").status_code == 200
    assert action("goal", goal_id="checkin").status_code == 409
    with main.database() as db:
        db.execute("UPDATE hall_state SET checkin_day=?,streak=3 WHERE city_id=?", (day - 1, city_id))
    assert action("checkin").json()["hall"]["streak"] == 4

    assert action("decree", choice="invalid").status_code == 400
    decree = action("decree", choice="pantry")
    assert decree.status_code == 200 and decree.json()["changes"]["stats"]["food"]["delta"] == 3
    assert action("decree", choice="parade").status_code == 409
    with main.database() as db:
        db.execute("UPDATE hall_state SET decree_day=? WHERE city_id=?", (day - 1, city_id))
        db.execute("UPDATE cities SET food=200 WHERE id=?", (city_id,))
    assert action("decree", choice="pantry").status_code == 409
    assert action("festival").status_code == 200
    assert action("festival").status_code == 409
    with main.database() as db:
        db.execute("UPDATE cities SET shards=1 WHERE id=?", (city_id,))
        db.execute("INSERT INTO heroes (id,city_id,name,title,tier,specialty,slot,joined_at,race,ally_race) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   ("trainee", city_id, "Citizen Spoon", "Napkin Captain", "green", "food", 0, int(time.time()), "Human", "Goblin"))
    original_choice = main.secrets.choice
    main.secrets.choice = lambda items: items[-1]
    try:
        crate = action("crate")
    finally:
        main.secrets.choice = original_choice
    assert crate.status_code == 200 and crate.json()["changes"]["wallet"]["core"]["delta"] == 1
    assert action("crate").status_code == 409
    with main.database() as db:
        db.execute("UPDATE hall_state SET crate_day=? WHERE city_id=?", (day - 1, city_id))
        db.execute("UPDATE cities SET shards=1,food=200,wealth=200,morale=100,cores=999,cash=100 WHERE id=?", (city_id,))
    capped_crate = action("crate")
    assert capped_crate.status_code == 200 and capped_crate.json()["changes"]["wallet"]["cash"]["delta"] == 8
    assert action("train", hero_id="missing").status_code == 404
    assert action("train", hero_id="trainee").status_code == 200
    assert action("train", hero_id="trainee").status_code == 409
    with main.database() as db:
        assert db.execute("SELECT training FROM heroes WHERE id='trainee'").fetchone()[0] == 1
    assert client.post("/api/hall/actions", json={"action": "train", "hero_id": "trainee"}, headers=rival_headers).status_code == 404
    assert action("gift", target_city_id=city_id).status_code == 400
    before = client.get("/api/me", headers=rival_headers).json()["city"]["morale"]
    gift = action("gift", target_city_id=rival_id)
    assert gift.status_code == 200 and gift.json()["changes"]["wallet"]["wealth"]["delta"] == -2
    assert client.get("/api/me", headers=rival_headers).json()["city"]["morale"] == min(100, before + 2)
    assert action("gift", target_city_id=rival_id).status_code == 409
    with main.database() as db:
        db.execute("UPDATE hall_state SET gift_day=? WHERE city_id=?", (day - 1, city_id))
        db.execute("UPDATE cities SET morale=100,food=50 WHERE id=?", (rival_id,))
    food_gift = action("gift", target_city_id=rival_id)
    assert food_gift.status_code == 200 and food_gift.json()["changes"]["stats"]["food"]["delta"] == 2
    with main.database() as db:
        db.execute("UPDATE cities SET population=111 WHERE id=?", (city_id,))
    assert action("achievement", achievement_id="population").status_code == 200
    assert action("achievement", achievement_id="population").status_code == 409
    assert action("achievement", achievement_id="weirdness").status_code == 409
    assert client.get("/api/hall", headers=headers).json()["my_rank"] == 1
    assert client.get("/api/me", headers=headers).json()["city"]["population"] == 111
    with main.database() as db:
        city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        traits = json.loads(city["traits"])
        food_skill = round(sum(traits[f"Food {facet.title()}"] for facet in main.FACETS) / len(main.FACETS))
        current_weather = main.hall_weather(city_id, int(time.time()) // main.DAY_SECONDS, city["weirdness"])
        expected_food = 100 + 5 + food_skill // 12 + 20 // 35 + 2 + current_weather["food"] - max(4, 111 // 12)
        db.execute("UPDATE cities SET last_day=?,food=100,tech=20,population=111 WHERE id=?", (int(time.time()) - main.DAY_SECONDS, city_id))
    assert client.get("/api/me", headers=headers).json()["city"]["food"] == expected_food
    print("Town Hall weather, check-in streaks, goals, achievements, decrees, festivals, crates, training, gifts, rankings, and abuse limits: PASS")
