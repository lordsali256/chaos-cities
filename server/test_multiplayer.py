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

    real_battle_story = main.battle_story
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
        db.execute("UPDATE cities SET goods=? WHERE id=?", (main.json.dumps({"ore": 4}), target_id))
        for index, city in enumerate(cities[:2]):
            db.execute("INSERT INTO trade_offers (id,sender_id,target_id,offer_hero_id,request_hero_id,offer_wealth,request_wealth,status,created_at,expires_at,resolved_at,request_good,request_good_amount) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (f"goods-{index}", city["city"]["id"], target_id, None, None, 0, 0,
                        "pending", now - 86401, now + 3600, 0, "ore", 3))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, f"/api/trades/goods-{index}/accept", headers=heads[2]) for index in range(2)]
        goods_results = [future.result() for future in futures]
    assert sorted(result.status_code for result in goods_results) == [200, 409], [result.text for result in goods_results]
    with main.database() as db:
        stocks = [main.json.loads(db.execute("SELECT goods FROM cities WHERE id=?", (city["city"]["id"],)).fetchone()[0]).get("ore", 0) for city in cities]
        assert sorted(stocks) == [0, 1, 3] and sum(stocks) == 4, stocks
        assert db.execute("SELECT COUNT(*) FROM trade_offers WHERE status='accepted' AND id LIKE 'goods-%'").fetchone()[0] == 1
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
            db.execute("INSERT INTO trade_offers (id,sender_id,target_id,offer_hero_id,request_hero_id,offer_wealth,request_wealth,status,created_at,expires_at,resolved_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (f"pair-{index}", first["city"]["id"], target_id, None, None, 0, 1,
                        "canceled", now, now + 3600, now))
    quota = client.get("/api/trades", headers=heads[0]).json()
    assert quota["pair_sent_today"][target_id] == main.TRADE_PAIR_DAILY_LIMIT
    assert client.post("/api/trades", json={"target_city_id": target_id, "request_wealth": 1}, headers=heads[0]).status_code == 429
    with main.database() as db:
        for index in range(main.TRADE_DAILY_LIMIT - main.TRADE_PAIR_DAILY_LIMIT):
            db.execute("INSERT INTO trade_offers (id,sender_id,target_id,offer_hero_id,request_hero_id,offer_wealth,request_wealth,status,created_at,expires_at,resolved_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (f"total-{index}", first["city"]["id"], second["city"]["id"], None, None, 0, 1,
                        "canceled", now, now + 3600, now))
    quota = client.get("/api/trades", headers=heads[0]).json()
    assert quota["sent_today"] == main.TRADE_DAILY_LIMIT
    assert client.post("/api/trades", json={"target_city_id": second["city"]["id"], "request_wealth": 1}, headers=heads[0]).status_code == 429

    for route in ("/api/me", "/api/trades", "/api/cities", "/api/feed"):
        assert client.get(route).status_code == 401
    private_feed = client.get("/api/feed", headers=heads[0]).json()["feed"]
    assert all(item["actor"] == "Alphaburg" or item["target"] == "Alphaburg" for item in private_feed)
    assert client.post("/api/battles", json={"target_city_id": target_id}).status_code == 401
    assert client.post("/api/trades", json={"target_city_id": target_id, "request_wealth": 1}).status_code == 401
    assert client.post(f"/api/trades/{offers[0].json()['id']}/accept", headers=heads[1]).status_code == 404

    underdog = client.post("/api/register", json={"player": "Underdog Mayor", "city": "Longshot"}).json()
    giant = client.post("/api/register", json={"player": "Giant Mayor", "city": "Talltown"}).json()
    underdog_id, giant_id = underdog["city"]["id"], giant["city"]["id"]
    underdog_head = {"Authorization": f"Bearer {underdog['city_key']}"}
    with main.database() as db:
        db.execute("UPDATE cities SET traits=?,created_at=?,wealth=200 WHERE id=?",
                   (main.json.dumps({trait: 0 for trait in main.TRAIT_NAMES}), now - 7200, underdog_id))
        db.execute("UPDATE cities SET traits=?,created_at=?,wealth=200 WHERE id=?",
                   (main.json.dumps({trait: 100 for trait in main.TRAIT_NAMES}), now - 7200, giant_id))
    original_roll = main.secrets.randbelow
    main.secrets.randbelow = lambda upper: 0
    try:
        upset = client.post("/api/battles", json={"target_city_id": giant_id}, headers=underdog_head)
    finally:
        main.secrets.randbelow = original_roll
    assert upset.status_code == 200 and upset.json()["success"], upset.text
    assert 35 <= upset.json()["chance"] <= 65
    assert 0 <= upset.json()["moved"] <= 6
    with main.database() as db:
        weak = main.json.loads(db.execute("SELECT traits FROM cities WHERE id=?", (underdog_id,)).fetchone()[0])
        strong = main.json.loads(db.execute("SELECT traits FROM cities WHERE id=?", (giant_id,)).fetchone()[0])
        assert all(weak[trait] + strong[trait] == 100 for trait in main.TRAIT_NAMES)
        assert all(0 <= score <= 100 for score in weak.values())
        assert all(0 <= score <= 100 for score in strong.values())

    class SpoilerStory:
        def __init__(self, scene="I am Talltown. The census was chaotic, but we settled it with a pretzel referendum."):
            self.scene = scene

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": main.json.dumps({
                "title": "The Great Pretzel Census",
                "story": self.scene,
                "beats": ["The pretzel commission is counting every twist.",
                          "We win because the other city forgot its paperwork.",
                          "The defenders lost the contest before lunch."]})}}

    original_post = main.httpx.post
    main.httpx.post = lambda *args, **kwargs: SpoilerStory()
    try:
        story = real_battle_story("Longshot", "Talltown", [
            {"name": "Pretzel Policy", "attacker": 1, "defender": 99},
            {"name": "Civic Humor", "attacker": 4, "defender": 96}], "Longshot", "2 trait points")
    finally:
        main.httpx.post = original_post
    assert story[2] == ["The pretzel commission is counting every twist."], story
    assert story[1].endswith("Longshot won and claimed 2 trait points."), story

    main.httpx.post = lambda *args, **kwargs: SpoilerStory("I am Talltown. Talltown won this battle already.")
    try:
        inaccurate = real_battle_story("Longshot", "Talltown", [
            {"name": "Pretzel Policy", "attacker": 1, "defender": 99},
            {"name": "Civic Humor", "attacker": 4, "defender": 96}], "Longshot", "2 trait points")
    finally:
        main.httpx.post = original_post
    assert "Talltown won" not in inaccurate[1] and "Longshot won" in inaccurate[1], inaccurate

    main.PUBLIC_REGISTRATION_LIMIT = 2
    main.TRUST_PROXY_CLIENT_IP = True
    shared_address = {"X-Game-Client-IP": "198.51.100.10"}
    for index in range(2):
        response = client.post("/api/register", json={"player": "Shared Mayor", "city": f"Sharedville {index}"}, headers=shared_address)
        assert response.status_code == 200, response.text
    assert client.post("/api/register", json={"player": "Shared Mayor", "city": "Sharedville 3"}, headers=shared_address).status_code == 429
    another_address = {"X-Game-Client-IP": "198.51.100.11"}
    assert client.post("/api/register", json={"player": "Other Mayor", "city": "Elsewhere"}, headers=another_address).status_code == 200
    with main.database() as db:
        assert db.execute("SELECT COUNT(*) FROM registration_log").fetchone()[0] == 3
        assert all(len(row[0]) == 64 for row in db.execute("SELECT DISTINCT client_hash FROM registration_log"))

    with main.database() as db:
        for index in range(110):
            db.execute("INSERT INTO heroes (id,city_id,name,title,tier,specialty,slot,joined_at) VALUES (?,?,?,?,?,?,?,?)",
                       (f"roster-{index}", target_id, f"Hero {index}", "Civic Tester", "white", "morale", None, now + index))
    roster = client.get(f"/api/cities/{target_id}/heroes", headers=heads[0])
    assert roster.status_code == 200 and len(roster.json()["heroes"]) == 110, roster.text
    assert {hero["id"] for hero in roster.json()["heroes"]} == {f"roster-{index}" for index in range(110)}
    assert client.get(f"/api/cities/{target_id}/heroes").status_code == 401
    assert client.get("/api/cities/no-such-city/heroes", headers=heads[0]).status_code == 404

    print("Concurrent PvP, trades, access control, underdog fairness, sign-up limits, and full rival rosters: PASS")
