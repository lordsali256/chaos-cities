"""Repeated battle and trade playtest in a temporary database."""

import json
import os
import tempfile
import time

with tempfile.TemporaryDirectory() as folder:
    os.environ["DATABASE_PATH"] = f"{folder}/balance.db"
    os.environ["INVITE_CODE"] = ""
    import main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    mayors = [client.post("/api/register", json={"player": f"Mayor {label}", "city": f"{label}town"}).json()
              for label in ("Low", "High", "Trade", "Swap")]
    ids = [item["city"]["id"] for item in mayors]
    heads = [{"Authorization": f"Bearer {item['city_key']}"} for item in mayors]
    now = int(time.time())
    main.battle_story = lambda actor, target, sampled, winner, reward: ("The Test Contest", f"I am {target}. {winner} received {reward}.", [])
    main.trade_story = lambda sender, target, items, fallback: ("The Test Receipt", fallback)

    with main.database() as db:
        db.execute("UPDATE cities SET traits=?,created_at=?,wealth=1000 WHERE id=?",
                   (json.dumps({trait: 0 for trait in main.TRAIT_NAMES}), now - 7200, ids[0]))
        db.execute("UPDATE cities SET traits=?,created_at=?,wealth=1000 WHERE id=?",
                   (json.dumps({trait: 100 for trait in main.TRAIT_NAMES}), now - 7200, ids[1]))
        for index, city_id in enumerate(ids[:2]):
            db.execute("INSERT INTO heroes (id,city_id,name,title,tier,specialty,slot,joined_at,race,ally_race) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (f"fighter-{index}", city_id, f"Fighter {index}", "Paper Shield", "white", "food", 0, now, "Human", "Goblin"))
    wins, thefts, chances = 0, 0, []
    for round_number in range(40):
        with main.database() as db:
            db.execute("UPDATE cities SET last_battle=0 WHERE id=?", (ids[0],))
            db.execute("UPDATE cities SET last_attacked=0 WHERE id=?", (ids[1],))
            db.execute("UPDATE event_log SET created_at=? WHERE kind='battle'", (now - 90000,))
            before_wealth = db.execute("SELECT wealth FROM cities WHERE id=?", (ids[0],)).fetchone()[0]
        response = client.post("/api/battles", json={"target_city_id": ids[1]}, headers=heads[0])
        assert response.status_code == 200, (round_number, response.text)
        result = response.json()
        wins += int(result["success"])
        thefts += bool(result["stolen_hero"])
        chances.append(result["chance"])
        assert len({item["name"] for item in result["sampled_traits"]}) == 20
        assert 35 <= result["chance"] <= 65 and 0 <= result["moved"] <= 6
        with main.database() as db:
            low = db.execute("SELECT traits,wealth FROM cities WHERE id=?", (ids[0],)).fetchone()
            high = db.execute("SELECT traits FROM cities WHERE id=?", (ids[1],)).fetchone()
            assert low["wealth"] == before_wealth - main.BATTLE_COST
            low_traits, high_traits = json.loads(low["traits"]), json.loads(high["traits"])
            assert all(low_traits[trait] + high_traits[trait] == 100 for trait in main.TRAIT_NAMES)
            assert all(0 <= score <= 100 for score in low_traits.values())
            assert all(0 <= score <= 100 for score in high_traits.values())
            fighters = db.execute("SELECT name,city_id,slot FROM heroes WHERE id IN ('fighter-0','fighter-1')").fetchall()
            assert len(fighters) == 2 and all(hero["city_id"] in ids[:2] for hero in fighters)
            if result["stolen_hero"]:
                moved = next(hero for hero in fighters if hero["name"] == result["stolen_hero"])
                assert moved["city_id"] == ids[0 if result["success"] else 1] and moved["slot"] is None

    total = sum(item["city"]["wealth"] for item in mayors[2:])
    for round_number in range(4):
        for sender, receiver in ((2, 3), (3, 2)):
            with main.database() as db:
                db.execute("UPDATE trade_offers SET created_at=? WHERE sender_id=?", (now - 61, ids[sender]))
            offer = client.post("/api/trades", json={"target_city_id": ids[receiver], "offer_wealth": 20}, headers=heads[sender])
            assert offer.status_code == 200, offer.text
            accepted = client.post(f"/api/trades/{offer.json()['id']}/accept", headers=heads[receiver])
            assert accepted.status_code == 200, accepted.text
            with main.database() as db:
                assert sum(db.execute("SELECT wealth FROM cities WHERE id=?", (city_id,)).fetchone()[0]
                           for city_id in ids[2:]) == total
    assert client.post("/api/trades", json={"target_city_id": ids[3], "offer_wealth": 1}, headers=heads[2]).status_code == 429
    print(f"40 battles: {wins} underdog wins, {thefts} citizen transfers, chances {min(chances)}–{max(chances)}%; eight trades conserved Wealth: PASS")
