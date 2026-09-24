"""Reset one playtest city while preserving its identity and owner key."""

import argparse
import json
import random
import secrets
import time

import main


def reset_city(name, owner):
    now = int(time.time())
    with main.LOCK, main.database() as db:
        city = db.execute("SELECT * FROM cities WHERE name=? AND owner_name=? COLLATE NOCASE", (name, owner)).fetchone()
        if city is None:
            raise ValueError("Exact city and owner pair not found")
        city_id = city["id"]
        traits = {trait: random.SystemRandom().randint(20, 80) for trait in main.TRAIT_NAMES}
        db.execute("""UPDATE cities SET tokens=12, last_day=?, population=100, wealth=60,
                   food=60, morale=60, tech=20, weirdness=2, traits=?, created_at=?,
                   shards=0, cores=0, errand_progress=0, shards_earned=0,
                   last_errand=0, last_ambient=?, weirdness_exposure=0,
                   last_battle=0, last_attacked=0, last_token=?, last_income=?,
                   cash=20, upgrades='{}', tech_nodes='[]', growth_bank='{}',
                   hero_slots=1, building_slots=1, specialization='',
                   specialization_changed_at=0 WHERE id=?""",
                   (now, json.dumps(traits), now, now, now, now, city_id))
        for table in ("chaos_offers", "heroes", "prepared_heroes", "prepared_jobs",
                      "city_buildings", "prepared_buildings"):
            db.execute(f"DELETE FROM {table} WHERE city_id=?", (city_id,))
        db.execute("DELETE FROM event_log WHERE actor_id=? AND target_id=?", (city_id, city_id))
    return city_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--owner", required=True)
    args = parser.parse_args()
    print(f"Reset {args.city} ({reset_city(args.city, args.owner)}); city key retained")
