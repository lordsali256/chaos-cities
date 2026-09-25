"""A defender cannot lose multiple Heroes to coordinated attackers in one day."""
import os
import tempfile
import time

with tempfile.TemporaryDirectory() as folder:
    os.environ["DATABASE_PATH"] = f"{folder}/hero-protection.db"
    import main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    players = [client.post("/api/register", json={"player": f"Mayor {name}", "city": f"{name}ville"}).json()
               for name in ("Aster", "Birch", "Cedar")]
    headers = [{"Authorization": f"Bearer {player['city_key']}"} for player in players]
    city_ids = [player["city"]["id"] for player in players]
    now = int(time.time())
    with main.database() as db:
        for city_id in city_ids:
            db.execute("UPDATE cities SET created_at=?,wealth=100 WHERE id=?", (now - 7200, city_id))
        for index in range(3):
            db.execute("INSERT INTO heroes (id,city_id,name,title,tier,specialty,slot,joined_at,race,ally_race) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (f"cedar-hero-{index}", city_ids[2], f"Cedar Hero {index}", "Pillow Marshal", "green", "food", None, now, "Human", "Goblin"))

    main.battle_story = lambda actor, target, sampled, winner, reward: ("The Test Contest", f"I am {target}. {winner} claimed {reward}.", [])
    roll = main.secrets.randbelow
    main.secrets.randbelow = lambda upper: 0
    try:
        first = client.post("/api/battles", json={"target_city_id": city_ids[2]}, headers=headers[0])
        assert first.status_code == 200 and first.json()["stolen_hero"], first.text
        protected = next(city for city in client.get("/api/cities", headers=headers[0]).json()["cities"] if city["id"] == city_ids[2])
        assert protected["hero_loss_protection_until"] > now
        assert client.get("/api/me", headers=headers[2]).json()["city"]["hero_loss_protection_until"] == protected["hero_loss_protection_until"]
        with main.database() as db:
            db.execute("UPDATE cities SET last_attacked=0 WHERE id=?", (city_ids[2],))
        second = client.post("/api/battles", json={"target_city_id": city_ids[2]}, headers=headers[1])
        assert second.status_code == 200 and second.json()["success"] and not second.json()["stolen_hero"], second.text
        with main.database() as db:
            assert db.execute("SELECT COUNT(*) FROM heroes WHERE city_id=?", (city_ids[2],)).fetchone()[0] == 2
            db.execute("UPDATE event_log SET created_at=? WHERE kind='battle' AND actor_id=?", (now - 90000, city_ids[0]))
            db.execute("UPDATE cities SET last_attacked=0,last_battle=0 WHERE id IN (?,?)", (city_ids[1], city_ids[2]))
        exposed = next(city for city in client.get("/api/cities", headers=headers[0]).json()["cities"] if city["id"] == city_ids[2])
        assert exposed["hero_loss_protection_until"] == 0
        third = client.post("/api/battles", json={"target_city_id": city_ids[2]}, headers=headers[1])
        assert third.status_code == 200 and third.json()["stolen_hero"], third.text
    finally:
        main.secrets.randbelow = roll

print("One Hero loss per defender per 24 hours, with normal theft afterward: PASS")
