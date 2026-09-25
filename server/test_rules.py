"""Run in the server container: python test_rules.py. Uses a temporary database."""
import os
import tempfile
import time

with tempfile.TemporaryDirectory() as folder:
    os.environ["DATABASE_PATH"] = f"{folder}/rules.db"
    os.environ["DAY_SECONDS"] = "60"
    os.environ["TOKEN_SECONDS"] = "3600"
    os.environ["DAILY_TOKENS"] = "1"
    import main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    def role_hero(role, tier):
        hero_id = next(f"ability-{role}-{index}" for index in range(100) if main.hero_role({"id": f"ability-{role}-{index}"}) == role)
        return {"id": hero_id, "name": role.title(), "title": f"{role.title()} of the Napkins",
                "tier": tier, "specialty": "wealth"}

    squad = [role_hero("guardian", "green"), role_hero("rallier", "blue"), role_hero("specialist", "purple")]
    selected = ["Market Courage", "Market Style", "Food Unity"]
    defense_power, defense_traits, defense_details = main.hero_battle_bonuses(squad, selected, True)
    attack_power, attack_traits, _ = main.hero_battle_bonuses(squad, selected, False)
    assert (defense_power, defense_traits, attack_power, attack_traits) == (10, 8, 6, 8)
    assert [item["role"] for item in defense_details] == list(main.HERO_ROLES)
    first = client.post("/api/register", json={"player": "First Mayor", "city": "Ruleville"}).json()
    second = client.post("/api/register", json={"player": "Second Mayor", "city": "Rivalton"}).json()
    key = first["city_key"]
    head = {"Authorization": f"Bearer {key}"}
    city_id = first["city"]["id"]
    rival_id = second["city"]["id"]
    now = int(time.time())
    assert first["city"]["hero_slots"] == first["city"]["building_slots"] == 1
    assert len(set(first["city"]["traits"])) == 320
    assert len(main.TECH_NODES) == 51
    with main.database() as db:
        db.execute("UPDATE cities SET tokens=1,last_token=?,last_income=?,last_day=? WHERE id=?", (now-7200, now-3600, now, city_id))
    view = client.get("/api/me", headers=head).json()
    assert len(view["residents"]) == 100 and len(view["races"]) == 36
    assert all(person["preferred_enemy"] in view["races"] for person in view["residents"])
    renamed = client.post("/api/city/rename", json={"name": "New Ruleville"}, headers=head)
    assert renamed.status_code == 200 and renamed.json()["city"]["name"] == "New Ruleville"
    assert client.post("/api/city/rename", json={"name": "Rivalton"}, headers=head).status_code == 409
    assert view["city"]["tokens"] == 3
    assert view["city"]["cash"] > 20
    assert view["city"]["growth_bank"]["food"] == .001
    assert not view["shop"][0]["unlocked"]
    assert len(view["specializations"]) == 5
    chosen = client.post("/api/specializations", json={"specialization_id": "coin_whisperers"}, headers=head)
    assert chosen.status_code == 200 and chosen.json()["city"]["cash_per_hour"] > view["city"]["cash_per_hour"]
    assert client.post("/api/specializations", json={"specialization_id": "roof_astronomers"}, headers=head).status_code == 409

    def finish_research():
        with main.database() as db:
            db.execute("UPDATE research_queue SET ready_at=? WHERE city_id=?", (int(time.time())-1, city_id))
        return client.get("/api/me", headers=head).json()

    assert client.post("/api/research", json={"node_id": "city_charter"}, headers=head).status_code == 200
    pending = client.get("/api/me", headers=head).json()
    assert pending["research"]["node_id"] == "city_charter"
    assert "city_charter" not in pending["city"]["tech_nodes"]
    assert client.post("/api/research", json={"node_id": "city_charter"}, headers=head).status_code == 409
    assert finish_research()["research"] is None
    assert client.post("/api/shop", json={"item_id": "income"}, headers=head).status_code == 200
    with main.database() as db:
        db.execute("UPDATE cities SET tech=65,cash=500,wealth=100,specialization_changed_at=? WHERE id=?", (now-86400, city_id))
    switched = client.post("/api/specializations", json={"specialization_id": "roof_astronomers"}, headers=head)
    assert switched.status_code == 200 and switched.json()["city"]["cash"] == 475
    assert switched.json()["city"]["growth_rates"]["tech"] == .005
    for node_id in ("soup_science", "pocket_parliament", "storytime_stool", "hero_hall", "plot_twist"):
        result = client.post("/api/research", json={"node_id": node_id}, headers=head)
        assert result.status_code == 200, result.text
        assert node_id in finish_research()["city"]["tech_nodes"]
    assert client.post("/api/shop", json={"item_id": "hero_slot"}, headers=head).json()["city"]["hero_slots"] == 2
    assert client.post("/api/shop", json={"item_id": "building_slot"}, headers=head).json()["city"]["building_slots"] == 2
    assert client.post("/api/shop", json={"item_id": "tech"}, headers=head).json()["city"]["upgrades"]["tech"] == 1
    with main.database() as db:
        db.execute("INSERT INTO prepared_buildings VALUES (?,?,?,?,?,?)", ("test-plan", city_id, "pantry", "The Soup Cathedral", "Its spoons wear tiny robes.", now))
        db.execute("INSERT INTO heroes (id,city_id,name,title,tier,specialty,slot,joined_at,race,ally_race) VALUES (?,?,?,?,?,?,?,?,?,?)", ("our-hero", city_id, "Mayor Noodle", "Ribbon Knight", "green", "food", None, now, "Human", "Goblin"))
        db.execute("INSERT INTO heroes (id,city_id,name,title,tier,specialty,slot,joined_at,race,ally_race) VALUES (?,?,?,?,?,?,?,?,?,?)", ("rival-hero", rival_id, "Professor Pickle", "Cabbage Oracle", "white", "tech", 0, now, "Goblin", "Human"))
    assert client.post("/api/buildings", json={"offer_id": "test-plan"}, headers=head).status_code == 200
    class DuplicateBuildings:
        def raise_for_status(self):
            pass
        def json(self):
            import json
            count = len(main.BUILDING_BLUEPRINTS) - 1
            return {"message": {"content": json.dumps({"buildings": [{"name": "The Soup Cathedral", "description": "A very serious city hall for soup ladles."} for _ in range(count)]})}}
    original_post = main.httpx.post
    main.httpx.post = lambda *args, **kwargs: DuplicateBuildings()
    try:
        main.fill_prepared_buildings(city_id)
    finally:
        main.httpx.post = original_post
    with main.database() as db:
        titles = [row[0] for row in db.execute("SELECT name FROM city_buildings WHERE city_id=? UNION ALL SELECT title FROM prepared_buildings WHERE city_id=?", (city_id, city_id))]
        assert len(titles) == len(set(name.casefold() for name in titles)) == len(main.BUILDING_BLUEPRINTS)
    assert client.post("/api/heroes/equip", json={"hero_id": "our-hero", "slot": 1}, headers=head).status_code == 200
    assert next(hero for hero in client.get("/api/me", headers=head).json()["heroes"] if hero["id"] == "our-hero")["ability"]["name"] == "Ribbon Knight"
    assert client.post("/api/errands", json={"task_id": "anything"}, headers=head).status_code == 410
    with main.database() as db:
        for index in range(13):
            db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (f"feed-{index}", city_id, city_id, "test", 1, "test", "{}", now + index, "ambient", "{}", f"Test {index}"))
        assert len([item for item in main.recent_feed(db, city_id) if item["kind"] == "ambient"]) == 10

    main.battle_story = lambda actor, target, sampled, winner, reward: ("The Grand Cabbage Contest", f"I am {target}. {winner} won a grand contest over {reward}.")
    main.secrets.randbelow = lambda n: 0
    with main.database() as db:
        db.execute("UPDATE cities SET created_at=? WHERE id=?", (now-3601, rival_id))
    win = client.post("/api/battles", json={"target_city_id": rival_id}, headers=head)
    assert win.status_code == 200, win.text
    outcome = win.json()
    assert outcome["success"] and len(outcome["sampled_traits"]) == 20
    assert len(outcome["changes"]["sampled_traits"]) == 20
    assert len(outcome["changes"]["race_duels"]) == 5
    assert len(outcome["changes"]["hero_abilities"]["attacker"]) == 1
    assert len(outcome["changes"]["hero_abilities"]["defender"]) == 1
    assert 35 <= outcome["chance"] <= 65
    defender_feed = client.get("/api/me", headers={"Authorization": f"Bearer {second['city_key']}"}).json()["feed"]
    assert any(item["kind"] == "battle" and len(item["changes"]["sampled_traits"]) == 20 for item in defender_feed)
    assert len(outcome["changes"]["attacker_traits"]) == 3
    assert outcome["stolen_hero"] == "Professor Pickle"
    assert all(value["delta"] >= 0 for value in outcome["changes"]["attacker_traits"].values())
    assert client.post("/api/battles", json={"target_city_id": rival_id}, headers=head).status_code == 409
    third = client.post("/api/register", json={"player": "Third Mayor", "city": "Thirdville"}).json()
    with main.database() as db:
        db.execute("UPDATE cities SET last_battle=0 WHERE id=?", (city_id,))
    assert client.post("/api/battles", json={"target_city_id": third["city"]["id"]}, headers=head).status_code == 409
    with main.database() as db:
        db.execute("UPDATE cities SET created_at=? WHERE id=?", (now-3601, third["city"]["id"]))
    main.secrets.randbelow = lambda n: n-1
    loss = client.post("/api/battles", json={"target_city_id": third["city"]["id"]}, headers=head)
    assert loss.status_code == 200 and not loss.json()["success"], loss.text
    assert all(value["delta"] <= 0 for value in loss.json()["changes"]["attacker_traits"].values())
    records = client.get("/api/cities", headers=head).json()["battle_records"]
    assert records[city_id] == {"wins": 1, "losses": 1}
    with main.database() as db:
        db.execute("UPDATE cities SET last_battle=0 WHERE id=?", (city_id,))
        db.execute("UPDATE cities SET last_attacked=0 WHERE id=?", (rival_id,))
        db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("pair-cap-test", city_id, rival_id, "trait_battle", 1, "test", "{}", now, "battle", "{}", "test"))
    pair_view = client.get("/api/cities", headers=head).json()
    assert pair_view["pair_attacks"][rival_id] == pair_view["pair_battle_limit"] == 2
    assert client.post("/api/battles", json={"target_city_id": rival_id}, headers=head).status_code == 409
    assert client.get("/api/me", headers=head).json()["city"]["tokens"] >= 3
    second_head = {"Authorization": f"Bearer {second['city_key']}"}
    trade = client.post("/api/trades", json={"target_city_id": rival_id, "offer_hero_id": "our-hero", "request_wealth": 3}, headers=head)
    assert trade.status_code == 200, trade.text
    offer_id = trade.json()["id"]
    assert any(item["id"] == offer_id for item in client.get("/api/trades", headers=second_head).json()["offers"])
    assert client.post(f"/api/trades/{offer_id}/accept", headers=head).status_code == 404
    main.trade_story = lambda sender, target, items, fallback: ("The Test Trade", fallback)
    accepted = client.post(f"/api/trades/{offer_id}/accept", headers=second_head)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["changes"]["sender_wallet"]["wealth"]["delta"] == 3
    assert accepted.json()["changes"]["target_wallet"]["wealth"]["delta"] == -3
    with main.database() as db:
        assert db.execute("SELECT city_id,slot FROM heroes WHERE id='our-hero'").fetchone()["city_id"] == rival_id
        assert db.execute("SELECT status FROM trade_offers WHERE id=?", (offer_id,)).fetchone()[0] == "accepted"
    assert client.post(f"/api/trades/{offer_id}/accept", headers=second_head).status_code == 409
    assert any(item["kind"] == "trade" for item in client.get("/api/me", headers=head).json()["feed"])
    with main.database() as db:
        db.execute("UPDATE trade_offers SET created_at=? WHERE id=?", (now-61, offer_id))
    assert client.post("/api/trades", json={"target_city_id": rival_id, "offer_hero_id": "our-hero"}, headers=head).status_code == 409
    expiring = client.post("/api/trades", json={"target_city_id": rival_id, "offer_wealth": 1}, headers=head)
    assert expiring.status_code == 200, expiring.text
    with main.database() as db:
        db.execute("UPDATE trade_offers SET expires_at=? WHERE id=?", (now-1, expiring.json()["id"]))
    assert client.post(f"/api/trades/{expiring.json()['id']}/accept", headers=second_head).status_code == 409
    assert any(item["id"] == expiring.json()["id"] and item["status"] == "expired" for item in client.get("/api/trades", headers=head).json()["offers"])
    fourth = client.post("/api/register", json={"player": "Fourth Mayor", "city": "Shieldton"}).json()
    fourth_id = fourth["city"]["id"]
    with main.database() as db:
        db.execute("UPDATE cities SET tokens=10,last_battle=0 WHERE id=?", (city_id,))
        for offer_id in ("shield-offer-one", "shield-offer-two"):
            db.execute("INSERT INTO chaos_offers (id,city_id,template_id,title,tagline,created_at) VALUES (?,?,?,?,?,?)", (offer_id, city_id, "flyer_mixup", "Flyer Mix-Up", "A civic mistake", now))
    first_attack = {"event_id": "shield-offer-one", "target_city_id": fourth_id}
    assert client.post("/api/events", json=first_attack, headers=head).status_code == 409
    with main.database() as db:
        db.execute("UPDATE cities SET created_at=? WHERE id=?", (now-3601, fourth_id))
    main.llm_story = lambda *args: "The flyers took a very scenic route."
    assert client.post("/api/events", json=first_attack, headers=head).status_code == 200
    assert client.post("/api/events", json={"event_id": "shield-offer-two", "target_city_id": fourth_id}, headers=head).status_code == 409
    assert client.post("/api/battles", json={"target_city_id": fourth_id}, headers=head).status_code == 409
    original_verify = main.google_id_token.verify_oauth2_token
    main.google_id_token.verify_oauth2_token = lambda token, request, audience: {"sub": "fixed-google-subject", "given_name": "Test"}
    main.GOOGLE_CLIENT_ID = "test-web-client"
    main.INVITE_CODE = "friends-only"
    credential = {"credential": "x" * 100}
    try:
        assert client.post("/api/auth/google", json=credential).status_code == 403
        sign_in = client.post("/api/auth/google", json={**credential, "invite_code": "friends-only"})
        assert sign_in.status_code == 200, sign_in.text
        session_head = {"Authorization": f"Bearer {sign_in.json()['session_key']}"}
        assert client.get("/api/me", headers=session_head).json()["city"]["id"] == sign_in.json()["city"]["id"]
        again = client.post("/api/auth/google", json=credential)
        assert again.status_code == 200 and again.json()["city"]["id"] == sign_in.json()["city"]["id"]
    finally:
        main.google_id_token.verify_oauth2_token = original_verify
    print("Economy, PvP, trades, named residents, renaming, and Google account sessions: PASS")
