"""Run in the server container: python test_multiplayer.py. Uses a temporary database."""
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

with tempfile.TemporaryDirectory() as folder:
    os.environ["DATABASE_PATH"] = f"{folder}/multiplayer.db"
    os.environ["INVITE_CODE"] = ""
    import main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    cities = [client.post("/api/register", json={"player": f"Mayor {name}", "city": f"{name}burg"}).json()
              for name in ("Alpha", "Beta", "Gamma")]
    first, second, defender = cities
    heads = [{"Authorization": f"Bearer {city['city_key']}"} for city in cities]
    now = int(time.time())
    with main.database() as db:
        for city in cities:
            db.execute("UPDATE cities SET created_at=?,wealth=60,last_battle=0,last_attacked=0 WHERE id=?",
                       (now - 7200, city["city"]["id"]))

    main.battle_story = lambda actor, target, sampled, winner, reward: (
        "The Concurrent Cabbage Cup", f"I am {target}. {winner} won the contest and received {reward}.", [])
    target_id = defender["city"]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, "/api/battles", json={"target_city_id": target_id}, headers=head)
                   for head in heads[:2]]
        battle_results = [future.result() for future in futures]
    assert sorted(result.status_code for result in battle_results) == [200, 409], [result.text for result in battle_results]
    with main.database() as db:
        assert db.execute("SELECT COUNT(*) FROM event_log WHERE kind='battle' AND target_id=?", (target_id,)).fetchone()[0] == 1
        assert db.execute("SELECT last_attacked FROM cities WHERE id=?", (target_id,)).fetchone()[0] > 0
        spent = sum(60 - db.execute("SELECT wealth FROM cities WHERE id=?", (city["city"]["id"],)).fetchone()[0]
                    for city in cities[:2])
        assert spent == main.BATTLE_COST, spent
        db.execute("UPDATE cities SET wealth=20 WHERE id=?", (target_id,))

    offers = [client.post("/api/trades", json={"target_city_id": target_id, "request_wealth": 15}, headers=head)
              for head in heads[:2]]
    assert all(result.status_code == 200 for result in offers), [result.text for result in offers]
    main.trade_story = lambda sender, target, items, fallback: ("The Concurrent Napkin Trade", fallback)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, f"/api/trades/{offer.json()['id']}/accept", headers=heads[2])
                   for offer in offers]
        trade_results = [future.result() for future in futures]
    assert sorted(result.status_code for result in trade_results) == [200, 409], [result.text for result in trade_results]
    with main.database() as db:
        assert db.execute("SELECT wealth FROM cities WHERE id=?", (target_id,)).fetchone()[0] == 5
        assert db.execute("SELECT COUNT(*) FROM trade_offers WHERE status='accepted'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM event_log WHERE kind='trade'").fetchone()[0] == 1
        for index in range(main.INCOMING_ATTACK_LIMIT - 1):
            db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (f"cap-{index}", first["city"]["id"], target_id, "flyer_mixup", 1, "test", "{}", now, "cast", "{}", "test"))
        db.execute("UPDATE cities SET last_attacked=0 WHERE id=?", (target_id,))
        db.execute("UPDATE cities SET last_battle=0,tokens=10 WHERE id IN (?,?)", (first["city"]["id"], second["city"]["id"]))
        db.execute("INSERT INTO chaos_offers (id,city_id,template_id,title,tagline,created_at) VALUES (?,?,?,?,?,?)",
                   ("daily-cap-offer", second["city"]["id"], "flyer_mixup", "Flyer Mix-Up", "test", now))
    public = client.get("/api/cities", headers=heads[0]).json()
    protected = next(city for city in public["cities"] if city["id"] == target_id)
    assert protected["incoming_attacks_24h"] == protected["incoming_attack_limit"] == main.INCOMING_ATTACK_LIMIT
    assert client.post("/api/battles", json={"target_city_id": target_id}, headers=heads[0]).status_code == 409
    assert client.post("/api/events", json={"event_id": "daily-cap-offer", "target_city_id": target_id}, headers=heads[1]).status_code == 409
    with main.database() as db:
        for index in range(main.TRADE_PAIR_DAILY_LIMIT - 1):
            db.execute("INSERT INTO trade_offers VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (f"pair-{index}", first["city"]["id"], target_id, None, None, 0, 1,
                        "canceled", now, now + 3600, now))
    quota = client.get("/api/trades", headers=heads[0]).json()
    assert quota["pair_sent_today"][target_id] == main.TRADE_PAIR_DAILY_LIMIT
    assert client.post("/api/trades", json={"target_city_id": target_id, "request_wealth": 1}, headers=heads[0]).status_code == 429
    with main.database() as db:
        for index in range(main.TRADE_DAILY_LIMIT - main.TRADE_PAIR_DAILY_LIMIT):
            db.execute("INSERT INTO trade_offers VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (f"total-{index}", first["city"]["id"], second["city"]["id"], None, None, 0, 1,
                        "canceled", now, now + 3600, now))
    quota = client.get("/api/trades", headers=heads[0]).json()
    assert quota["sent_today"] == main.TRADE_DAILY_LIMIT
    assert client.post("/api/trades", json={"target_city_id": second["city"]["id"], "request_wealth": 1}, headers=heads[0]).status_code == 429

    print("Concurrent PvP shield, trade spending, daily defense and proposal limits: PASS")
