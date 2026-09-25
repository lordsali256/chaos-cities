import hashlib
import ipaddress
import json
import os
import random
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import httpx
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from trait_labels import ALL_LABELS
from tech_tree import TECH_NODES, TECH_BY_ID, tech_bonuses
from specializations import SPECIALIZATIONS, SPECIALIZATION_BY_ID, specialization_bonus
from citizens import RACES, PREFERRED_ENEMY, citizen_identity

DB = Path(os.getenv("DATABASE_PATH", "/data/chaos.db"))
DAY_SECONDS = max(60, int(os.getenv("DAY_SECONDS", "86400")))
DAILY_TOKENS = max(1, int(os.getenv("DAILY_TOKENS", "1")))
TOKEN_SECONDS = max(60, int(os.getenv("TOKEN_SECONDS", "3600")))
INVITE_CODE = os.getenv("INVITE_CODE", "").strip()
PUBLIC_REGISTRATION_LIMIT = max(0, int(os.getenv("PUBLIC_REGISTRATION_LIMIT", "0")))
TRUST_PROXY_CLIENT_IP = os.getenv("TRUST_PROXY_CLIENT_IP", "0") == "1"
if PUBLIC_REGISTRATION_LIMIT and len(INVITE_CODE) < 20:
    raise RuntimeError("Public hosting needs an INVITE_CODE of at least 20 characters")
PHONE_SERVER_URL = os.getenv("PHONE_SERVER_URL", "").strip().rstrip("/")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://free-llm-ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
MAX_TOKENS = 30
AMBIENT_SECONDS = max(60, int(os.getenv("AMBIENT_SECONDS", "600")))
ERRAND_SECONDS = max(30, int(os.getenv("ERRAND_SECONDS", "120")))
LOCK = threading.RLock()
app = FastAPI(title="Chaos Cities")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

DOMAINS = ["civic", "market", "science", "food", "weather", "cosmic", "magic", "ecology", "architecture", "fashion", "transport", "diplomacy", "defense", "dream", "animal", "bureaucracy", "festival", "memory", "machinery", "mystery"]
FACETS = ["curiosity", "courage", "chaos", "creativity", "generosity", "stubbornness", "suspicion", "resilience", "ambition", "harmony", "mischief", "patience", "absurdity", "cleverness", "style", "unity"]
TRAIT_NAMES = [f"{domain.title()} {facet.title()}" for domain in DOMAINS for facet in FACETS]
assert len(TRAIT_NAMES) == 320
DISPLAY_NAME = dict(zip(TRAIT_NAMES, ALL_LABELS))
CATEGORIES = {
    "People & politics": ["civic", "bureaucracy"], "Trade & money": ["market", "diplomacy"],
    "Science & machines": ["science", "machinery"], "Food & nature": ["food", "ecology"],
    "Sky & space": ["weather", "cosmic"], "Magic & dreams": ["magic", "dream"],
    "Streets & travel": ["architecture", "transport"], "Style & celebrations": ["fashion", "festival"],
    "Safety & secrets": ["defense", "mystery"], "Creatures & history": ["animal", "memory"],
}
TRAIT_CATEGORIES = {DISPLAY_NAME[f"{domain.title()} {facet.title()}"]: category for category, domains in CATEGORIES.items() for domain in domains for facet in FACETS}
RAMP_DAYS = 90
HERO_SLOTS = 3
BUILDING_SLOTS = 5
BATTLE_COST = 8
BATTLE_COOLDOWN = 4 * 3600
DEFENSE_COOLDOWN = 3600
NEW_CITY_SHIELD = 3600
PAIR_BATTLE_LIMIT = 2
INCOMING_ATTACK_LIMIT = 6
TRADE_DAILY_LIMIT = 10
TRADE_PAIR_DAILY_LIMIT = 4
TIERS = ("white", "green", "blue", "purple", "orange")
RARITY_LABELS = dict(zip(TIERS, ("Common", "Uncommon", "Rare", "Epic", "Legendary")))
HERO_ROLES = ("guardian", "rallier", "specialist")
HERO_TRAIT_DOMAIN = {"food": "Food", "wealth": "Market", "morale": "Civic", "tech": "Science"}
OFFER_SECONDS = 6 * 3600
UNSAFE_CONTENT = re.compile(r"\b(?:whack[ -]?off|fuck\w*|shit\w*|bitch\w*|dick\w*|cock\w*|porn\w*|rape\w*|suicid\w*|kill\s+yourself)\b", re.I)


def safe_content(*values):
    return not any(UNSAFE_CONTENT.search(str(value)) for value in values)

# Fixed mechanics. The LLM only writes flavor text after a result is committed.
EVENTS = [
    dict(id="library_swap", name="Library Book Swap", kind="self", cost=2, icon="📚", tagline="Neighbors exchange books and argue about bookmarks.", domain="civic", facet="curiosity", effects={"morale": 4, "tech": 1, "weirdness": 1}, trait=4),
    dict(id="garden_day", name="Community Garden Day", kind="self", cost=3, icon="🌱", tagline="Volunteers discover the tomatoes have excellent opinions.", domain="food", facet="generosity", effects={"food": 6, "morale": 2, "weirdness": 1}, trait=5),
    dict(id="market_fair", name="Neighborhood Market Fair", kind="self", cost=4, icon="🛍️", tagline="Local shops compete for the town's least useful ribbon.", domain="market", facet="creativity", effects={"wealth": 6, "morale": 2, "weirdness": 1}, trait=5),
    dict(id="flyer_mixup", name="Flyer Delivery Mix-Up", kind="attack", cost=2, icon="📬", tagline="The rival city gets invitations to the wrong meeting.", domain="bureaucracy", facet="mischief", effects={"morale": -2, "wealth": -2, "weirdness": 1}, trait=4),
    dict(id="parking_panic", name="Parking Sign Confusion", kind="attack", cost=3, icon="🚗", tagline="Their parking signs disagree for one afternoon.", domain="transport", facet="mischief", effects={"wealth": -4, "morale": -2, "weirdness": 1}, trait=4),
    dict(id="hive_mind", name="Mandatory Hive Mind", kind="self", cost=5, icon="🧠", tagline="The whole city shares one thought. It is about soup.", domain="civic", facet="harmony", effects={"morale": 8, "food": -5, "weirdness": 14, "population": 2}, trait=12),
    dict(id="alien_relic", name="Alien Yard Sale", kind="self", cost=8, icon="👽", tagline="Ancient tech falls from orbit with no instruction manual.", domain="cosmic", facet="cleverness", effects={"tech": 16, "wealth": 5, "weirdness": 12}, trait=14),
    dict(id="pigeon_union", name="Pigeons Unionize", kind="self", cost=3, icon="🐦", tagline="Feathered workers negotiate better breadcrumbs.", domain="animal", facet="curiosity", effects={"food": 8, "morale": 5, "weirdness": 5}, trait=10),
    dict(id="moon_cheese", name="The Moon Is Cheese", kind="self", cost=6, icon="🧀", tagline="A lunar mining startup gets suspiciously delicious.", domain="food", facet="ambition", effects={"food": 16, "wealth": 4, "weirdness": 8}, trait=12),
    dict(id="sentient_roads", name="Roads Become Sentient", kind="self", cost=4, icon="🛣️", tagline="The streets choose shorter routes and demand compliments.", domain="architecture", facet="curiosity", effects={"wealth": 7, "morale": 4, "weirdness": 9}, trait=11),
    dict(id="mayor_clone", name="Clone the Mayor", kind="self", cost=5, icon="🧪", tagline="The copy is better at paperwork and worse at secrets.", domain="bureaucracy", facet="cleverness", effects={"tech": 6, "wealth": 7, "weirdness": 10}, trait=12),
    dict(id="dream_power", name="Harvest Dream Energy", kind="self", cost=7, icon="🌙", tagline="Bedtime becomes the power grid's busiest shift.", domain="dream", facet="unity", effects={"tech": 11, "wealth": 8, "morale": -3, "weirdness": 12}, trait=12),
    dict(id="dragon_audit", name="Dragon Tax Audit", kind="attack", cost=6, icon="🐉", tagline="A dragon examines your rival's receipts, then their roof.", domain="bureaucracy", facet="mischief", effects={"wealth": -12, "morale": -5, "weirdness": 7}, trait=10),
    dict(id="reverse_gravity", name="Gravity Takes Lunch", kind="attack", cost=7, icon="🪐", tagline="Their furniture applies for pilot licenses.", domain="cosmic", facet="chaos", effects={"food": -9, "wealth": -7, "weirdness": 13}, trait=12),
    dict(id="meme_plague", name="Unstoppable Meme Plague", kind="attack", cost=4, icon="🌀", tagline="Every speech is interrupted by the same terrible joke.", domain="festival", facet="mischief", effects={"morale": -10, "wealth": -4, "weirdness": 8}, trait=9),
    dict(id="bureaucratic_fog", name="Forms Fall from Sky", kind="attack", cost=3, icon="📄", tagline="Even the clouds need permits to rain.", domain="bureaucracy", facet="absurdity", effects={"wealth": -5, "tech": -3, "weirdness": 6}, trait=8),
    dict(id="raccoon_coup", name="Raccoon Cabinet Coup", kind="attack", cost=5, icon="🦝", tagline="Masked ministers reorganize city hall by smell.", domain="animal", facet="courage", effects={"food": -7, "morale": -6, "weirdness": 11}, trait=10),
    dict(id="mirror_tourists", name="Mirror Dimension Tourists", kind="attack", cost=6, icon="🪞", tagline="Visitors arrive, spend nothing, and critique every reflection.", domain="mystery", facet="chaos", effects={"wealth": -9, "morale": -6, "weirdness": 12}, trait=11),
    dict(id="alien_coronation", name="Alien Coronation Machine", kind="self", cost=12, shard_cost=2, icon="🛸", tagline="Ancient extraterrestrial tech crowns every toaster a duke.", domain="cosmic", facet="courage", effects={"tech": 25, "wealth": 12, "morale": -4, "weirdness": 24}, trait=16),
    dict(id="hive_ascension", name="Hive Mind Ascension", kind="self", cost=15, shard_cost=3, core_cost=1, icon="🧠", tagline="Everyone becomes one mind, which immediately demands a bigger hat.", domain="civic", facet="harmony", effects={"population": 15, "morale": 16, "tech": 10, "weirdness": 35}, trait=20),
    dict(id="moon_repossession", name="Repossess Their Moon", kind="attack", cost=12, shard_cost=2, icon="🌔", tagline="A celestial tow truck removes the rival city's favorite moon.", domain="cosmic", facet="mischief", effects={"wealth": -20, "food": -12, "weirdness": 20}, trait=16),
    dict(id="reality_auction", name="Auction Their Reality", kind="attack", cost=15, shard_cost=3, core_cost=1, icon="🔨", tagline="Reality is sold to the lowest bidder. It is a goose.", domain="mystery", facet="chaos", effects={"morale": -18, "tech": -15, "wealth": -15, "weirdness": 35}, trait=20),
]
for event in EVENTS:
    event.setdefault("shard_cost", 0)
    event.setdefault("core_cost", 0)
EVENT_BY_ID = {event["id"]: event for event in EVENTS}

# The AI selects among these bounded incidents. Their effects remain server-owned.
AMBIENT = [
    dict(id="umbrella_monopoly", name="The Umbrella Monopoly", icon="☂️", premise="Strangers rent out umbrellas during a rainstorm made of tiny spoons.", effects={"wealth": 2, "morale": -2, "weirdness": 3}),
    dict(id="pigeon_opera", name="Pigeon Opera", icon="🐦", premise="A flock stages a three-act opera outside the library.", effects={"morale": 4, "food": -2, "weirdness": 3}),
    dict(id="sentient_loaf", name="The Loaf Critiques Zoning", icon="🍞", premise="A sentient loaf of bread starts giving architecture reviews.", effects={"morale": 3, "wealth": -2, "weirdness": 4}),
    dict(id="mayor_shadow", name="The Mayor's Shadow Resigns", icon="👤", premise="A shadow requests paid leave and a window office.", effects={"wealth": -2, "morale": 2, "weirdness": 4}),
    dict(id="singing_sewers", name="The Sewers Sing Jazz", icon="🎷", premise="The drains form a band with troublingly good rhythm.", effects={"morale": 3, "tech": 1, "weirdness": 4}),
    dict(id="invisible_parade", name="Invisible Parade", icon="🎉", premise="An unseen marching band blocks traffic for an hour.", effects={"wealth": -3, "morale": 3, "weirdness": 5}),
    dict(id="tax_frogs", name="Frogs Demand Tax Exemption", icon="🐸", premise="The pond sends legal counsel and a damp petition.", effects={"wealth": -2, "food": 2, "weirdness": 4}),
    dict(id="moon_postcard", name="Postcard from the Moon", icon="📮", premise="A postcard arrives from a crater nobody remembers mailing.", effects={"tech": 2, "morale": 2, "weirdness": 3}),
    dict(id="raccoon_railway", name="Raccoons Open a Railway", icon="🦝", premise="Masked conductors offer midnight service to nowhere.", effects={"wealth": 2, "food": -2, "weirdness": 4}),
    dict(id="meteor_lost_found", name="Meteor in Lost and Found", icon="☄️", premise="A tiny meteor insists it belongs to the city library.", effects={"tech": 3, "weirdness": 5}, shard_chance=15),
    dict(id="sock_eclipse", name="The Sock Eclipse", icon="🧦", premise="Every left sock briefly blocks the sun.", effects={"morale": 2, "food": -1, "weirdness": 5}),
    dict(id="clock_strike", name="Clocks Go on Strike", icon="⏰", premise="Every clock refuses to reveal the time until offered coffee.", effects={"wealth": -2, "morale": -1, "weirdness": 4}),
]
AMBIENT_BY_ID = {event["id"]: event for event in AMBIENT}

ERRANDS = [
    dict(id="scavenge", name="Rummage the Odd Market", icon="🛒", tagline="Trade one hour of dignity for questionable groceries.", effects={"food": 3, "weirdness": 1}),
    dict(id="town_meeting", name="Hold a Town Meeting", icon="📣", tagline="Let citizens vote on the most important imaginary problem.", effects={"morale": 3, "wealth": -1}),
    dict(id="repair", name="Repair a Suspicious Machine", icon="🔧", tagline="Tighten bolts while avoiding the one that whispers.", effects={"tech": 2, "wealth": -1}),
    dict(id="investigate", name="Investigate a Rumor", icon="🔎", tagline="Follow clues that may be leading themselves.", effects={"weirdness": 2, "morale": 1}),
]
ERRAND_BY_ID = {task["id"]: task for task in ERRANDS}

BUILDING_BLUEPRINTS = [
    dict(id="pantry", name="Soup Parliament", icon="🥕", cost=18, daily={"food": 3}, defense=0, theme="a quirky food pantry and garden"),
    dict(id="bazaar", name="Cash Cow Convention", icon="🪙", cost=22, daily={"wealth": 3}, defense=0, theme="a local market that helps shops trade"),
    dict(id="workshop", name="Left-Handed Lightbulb Lab", icon="🔧", cost=24, daily={"tech": 2}, defense=0, theme="a small workshop for useful inventions"),
    dict(id="theater", name="Extremely Serious Puppet Office", icon="🎭", cost=20, daily={"morale": 2}, defense=0, theme="a community stage and gathering place"),
    dict(id="bastion", name="Pillow Patrol Headquarters", icon="🛡️", cost=26, daily={}, defense=8, theme="a watchtower that protects the city in battles"),
]
BUILDING_BY_ID = {building["id"]: building for building in BUILDING_BLUEPRINTS}

SHOP = [
    dict(id="income", name="Cash Register With Ambition", tech=0, requires="city_charter", base=8, effect="+15% Cash income per level", icon="💵"),
    dict(id="food", name="Self Stirring Soup Pot", tech=25, requires="soup_science", base=7, effect="+0.001 Food per hour per level", icon="🥣"),
    dict(id="tech", name="Overthinking Machine", tech=25, requires="soup_science", base=9, effect="+0.001 Tech per hour per level", icon="🧠"),
    dict(id="morale", name="Compliment Cannon", tech=25, requires="pocket_parliament", base=7, effect="+0.001 Morale per hour per level", icon="🎉"),
    dict(id="wealth", name="Tiny Gold Fountain", tech=20, requires="coin_counter", base=8, effect="+0.001 Wealth per hour per level", icon="🪙"),
    dict(id="hero_slot", name="Extra Hero Chair", tech=35, requires="hero_hall", base=30, effect="+1 equipped citizen slot", icon="🪑"),
    dict(id="building_slot", name="Additional Questionable Plot", tech=35, requires="plot_twist", base=30, effect="+1 building plot", icon="🏗️"),
]
SHOP_BY_ID = {item["id"]: item for item in SHOP}


@contextmanager
def database():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with database() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS cities (
          id TEXT PRIMARY KEY, owner_hash TEXT UNIQUE NOT NULL, owner_name TEXT NOT NULL,
          name TEXT UNIQUE NOT NULL, tokens INTEGER NOT NULL, last_day INTEGER NOT NULL,
          population INTEGER NOT NULL, wealth INTEGER NOT NULL, food INTEGER NOT NULL,
          morale INTEGER NOT NULL, tech INTEGER NOT NULL, weirdness INTEGER NOT NULL,
          traits TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS event_log (
          id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, target_id TEXT NOT NULL,
          event_id TEXT NOT NULL, success INTEGER NOT NULL, story TEXT NOT NULL,
          deltas TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS event_target_time ON event_log(target_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS chaos_offers (
          id TEXT PRIMARY KEY, city_id TEXT NOT NULL, template_id TEXT NOT NULL,
          title TEXT NOT NULL, tagline TEXT NOT NULL, created_at INTEGER NOT NULL,
          bonus_stat TEXT, trait_domain TEXT, trait_facet TEXT,
          FOREIGN KEY(city_id) REFERENCES cities(id));
        CREATE INDEX IF NOT EXISTS offers_city ON chaos_offers(city_id, created_at);
        CREATE TABLE IF NOT EXISTS used_content (
          content_hash TEXT PRIMARY KEY, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS heroes (
          id TEXT PRIMARY KEY, city_id TEXT NOT NULL, name TEXT NOT NULL,
          title TEXT NOT NULL, tier TEXT NOT NULL, specialty TEXT NOT NULL,
          slot INTEGER, joined_at INTEGER NOT NULL,
          FOREIGN KEY(city_id) REFERENCES cities(id));
        CREATE INDEX IF NOT EXISTS heroes_city ON heroes(city_id);
        CREATE TABLE IF NOT EXISTS google_accounts (
          subject TEXT PRIMARY KEY, city_id TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS google_sessions (
          session_hash TEXT PRIMARY KEY, city_id TEXT NOT NULL, expires_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS google_sessions_city ON google_sessions(city_id);
        CREATE TABLE IF NOT EXISTS registration_log (
          id TEXT PRIMARY KEY, client_hash TEXT NOT NULL, city_id TEXT NOT NULL,
          created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS registration_client_time ON registration_log(client_hash, created_at DESC);
        CREATE TABLE IF NOT EXISTS residents (
          city_id TEXT NOT NULL, ordinal INTEGER NOT NULL, name TEXT NOT NULL,
          race TEXT NOT NULL, ai_named INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(city_id,ordinal));
        CREATE TABLE IF NOT EXISTS prepared_heroes (
          id TEXT PRIMARY KEY, city_id TEXT NOT NULL, name TEXT NOT NULL,
          title TEXT NOT NULL, tier TEXT NOT NULL, specialty TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          FOREIGN KEY(city_id) REFERENCES cities(id));
        CREATE INDEX IF NOT EXISTS prepared_heroes_city ON prepared_heroes(city_id);
        CREATE TABLE IF NOT EXISTS prepared_jobs (
          id TEXT PRIMARY KEY, city_id TEXT NOT NULL, template_id TEXT NOT NULL,
          title TEXT NOT NULL, tagline TEXT NOT NULL, created_at INTEGER NOT NULL,
          FOREIGN KEY(city_id) REFERENCES cities(id));
        CREATE INDEX IF NOT EXISTS prepared_jobs_city ON prepared_jobs(city_id);
        CREATE TABLE IF NOT EXISTS city_buildings (
          id TEXT PRIMARY KEY, city_id TEXT NOT NULL, blueprint_id TEXT NOT NULL,
          name TEXT NOT NULL, description TEXT NOT NULL, built_at INTEGER NOT NULL,
          UNIQUE(city_id,blueprint_id), FOREIGN KEY(city_id) REFERENCES cities(id));
        CREATE INDEX IF NOT EXISTS city_buildings_city ON city_buildings(city_id);
        CREATE TABLE IF NOT EXISTS prepared_buildings (
          id TEXT PRIMARY KEY, city_id TEXT NOT NULL, blueprint_id TEXT NOT NULL,
          title TEXT NOT NULL, tagline TEXT NOT NULL, created_at INTEGER NOT NULL,
          UNIQUE(city_id,blueprint_id), FOREIGN KEY(city_id) REFERENCES cities(id));
        CREATE INDEX IF NOT EXISTS prepared_buildings_city ON prepared_buildings(city_id);
        CREATE TABLE IF NOT EXISTS trade_offers (
          id TEXT PRIMARY KEY, sender_id TEXT NOT NULL, target_id TEXT NOT NULL,
          offer_hero_id TEXT, request_hero_id TEXT,
          offer_wealth INTEGER NOT NULL DEFAULT 0, request_wealth INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL,
          expires_at INTEGER NOT NULL, resolved_at INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(sender_id) REFERENCES cities(id), FOREIGN KEY(target_id) REFERENCES cities(id));
        CREATE INDEX IF NOT EXISTS trade_sender ON trade_offers(sender_id,status,created_at DESC);
        CREATE INDEX IF NOT EXISTS trade_target ON trade_offers(target_id,status,created_at DESC);
        CREATE TABLE IF NOT EXISTS research_queue (
          city_id TEXT PRIMARY KEY, node_id TEXT NOT NULL, started_at INTEGER NOT NULL,
          ready_at INTEGER NOT NULL, FOREIGN KEY(city_id) REFERENCES cities(id));
        CREATE TABLE IF NOT EXISTS daily_taglines (
          city_id TEXT NOT NULL, day INTEGER NOT NULL, tagline TEXT NOT NULL,
          PRIMARY KEY(city_id,day));
        """)
        city_columns = {row[1] for row in db.execute("PRAGMA table_info(cities)")}
        for name, definition in {
            "shards": "INTEGER NOT NULL DEFAULT 0",
            "cores": "INTEGER NOT NULL DEFAULT 0",
            "errand_progress": "INTEGER NOT NULL DEFAULT 0",
            "shards_earned": "INTEGER NOT NULL DEFAULT 0",
            "last_errand": "INTEGER NOT NULL DEFAULT 0",
            "last_ambient": "INTEGER NOT NULL DEFAULT 0",
            "weirdness_exposure": "INTEGER NOT NULL DEFAULT 0",
            "last_battle": "INTEGER NOT NULL DEFAULT 0",
            "last_attacked": "INTEGER NOT NULL DEFAULT 0",
            "last_token": "INTEGER NOT NULL DEFAULT 0",
            "last_income": "INTEGER NOT NULL DEFAULT 0",
            "cash": "REAL NOT NULL DEFAULT 20",
            "upgrades": "TEXT NOT NULL DEFAULT '{}'",
            "tech_nodes": "TEXT NOT NULL DEFAULT '[]'",
            "growth_bank": "TEXT NOT NULL DEFAULT '{}'",
            "hero_slots": "INTEGER NOT NULL DEFAULT 1",
            "building_slots": "INTEGER NOT NULL DEFAULT 1",
            "specialization": "TEXT NOT NULL DEFAULT ''",
            "specialization_changed_at": "INTEGER NOT NULL DEFAULT 0",
            "renamed_at": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in city_columns:
                db.execute(f"ALTER TABLE cities ADD COLUMN {name} {definition}")
        now = int(time.time())
        db.execute("UPDATE cities SET last_token=? WHERE last_token=0", (now,))
        db.execute("UPDATE cities SET last_income=? WHERE last_income=0", (now,))
        db.execute("UPDATE cities SET hero_slots=MAX(hero_slots,COALESCE((SELECT MAX(slot)+1 FROM heroes WHERE heroes.city_id=cities.id),1))")
        db.execute("UPDATE cities SET building_slots=MAX(building_slots,(SELECT COUNT(*) FROM city_buildings WHERE city_buildings.city_id=cities.id))")
        # Existing high weirdness remains as history; visible reality drift follows city age.
        db.execute("UPDATE cities SET weirdness_exposure=weirdness WHERE weirdness_exposure=0 AND weirdness>0")
        db.execute("UPDATE cities SET weirdness=MIN(weirdness, 5 + CAST(MAX(0, (strftime('%s','now')-created_at)/86400)*95/90 AS INTEGER)) WHERE weirdness>5")
        log_columns = {row[1] for row in db.execute("PRAGMA table_info(event_log)")}
        if "kind" not in log_columns:
            db.execute("ALTER TABLE event_log ADD COLUMN kind TEXT NOT NULL DEFAULT 'cast'")
        if "changes" not in log_columns:
            db.execute("ALTER TABLE event_log ADD COLUMN changes TEXT NOT NULL DEFAULT '{}'")
        if "title" not in log_columns:
            db.execute("ALTER TABLE event_log ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE INDEX IF NOT EXISTS event_kind_time ON event_log(kind, created_at DESC)")
        offer_columns = {row[1] for row in db.execute("PRAGMA table_info(chaos_offers)")}
        for name in ("bonus_stat", "trait_domain", "trait_facet"):
            if name not in offer_columns:
                db.execute(f"ALTER TABLE chaos_offers ADD COLUMN {name} TEXT")
        hero_columns = {row[1] for row in db.execute("PRAGMA table_info(heroes)")}
        for name in ("race", "ally_race"):
            if name not in hero_columns:
                db.execute(f"ALTER TABLE heroes ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        for hero in db.execute("SELECT id FROM heroes WHERE race='' OR ally_race=''").fetchall():
            race = secrets.choice(RACES)
            ally = secrets.choice([item for item in RACES if item != race])
            db.execute("UPDATE heroes SET race=?,ally_race=? WHERE id=?", (race, ally, hero["id"]))
        if "ai_named" not in {row[1] for row in db.execute("PRAGMA table_info(residents)")}:
            db.execute("ALTER TABLE residents ADD COLUMN ai_named INTEGER NOT NULL DEFAULT 0")


init_db()


class Register(BaseModel):
    player: str = Field(min_length=2, max_length=24)
    city: str = Field(min_length=3, max_length=28)
    invite_code: str = ""


class RenameRequest(BaseModel):
    name: str = Field(min_length=3, max_length=28)


class GoogleCredential(BaseModel):
    credential: str = Field(min_length=100, max_length=8192)
    invite_code: str = ""


class Cast(BaseModel):
    event_id: str
    target_city_id: str | None = None


class ErrandRequest(BaseModel):
    task_id: str


class EquipRequest(BaseModel):
    hero_id: str
    slot: int | None = None


class BuildRequest(BaseModel):
    offer_id: str


class BattleRequest(BaseModel):
    target_city_id: str
    category: str = ""


class PurchaseRequest(BaseModel):
    item_id: str


class ResearchRequest(BaseModel):
    node_id: str


class SpecializationRequest(BaseModel):
    specialization_id: str


class TradeRequest(BaseModel):
    target_city_id: str
    offer_hero_id: str | None = None
    request_hero_id: str | None = None
    offer_wealth: int = Field(default=0, ge=0, le=20)
    request_wealth: int = Field(default=0, ge=0, le=20)


def clean_name(value: str, lo: int, hi: int) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    if not lo <= len(value) <= hi or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .'-]*", value):
        raise HTTPException(400, "Use letters, numbers, spaces, periods, apostrophes or hyphens.")
    return value


def auth(db, authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "City key required")
    key = authorization[7:]
    if len(key) < 30 or len(key) > 100:
        raise HTTPException(401, "Invalid city key")
    owner_hash = hashlib.sha256(key.encode()).hexdigest()
    city = db.execute("SELECT * FROM cities WHERE owner_hash=?", (owner_hash,)).fetchone()
    if not city:
        city = db.execute("SELECT c.* FROM google_sessions s JOIN cities c ON c.id=s.city_id WHERE s.session_hash=? AND s.expires_at>?", (owner_hash, int(time.time()))).fetchone()
    if not city:
        raise HTTPException(401, "Unknown city key")
    return city


def registration_identity(request: Request) -> str:
    address = request.client.host if request.client else "unknown"
    if TRUST_PROXY_CLIENT_IP:
        supplied = request.headers.get("x-game-client-ip", "")
        try:
            address = str(ipaddress.ip_address(supplied))
        except ValueError:
            pass
    return hashlib.sha256(f"{INVITE_CODE}|{address}".encode()).hexdigest()


def hero_role(hero) -> str:
    return HERO_ROLES[hashlib.sha256(hero["id"].encode()).digest()[0] % len(HERO_ROLES)]


def hero_ability(hero) -> dict:
    tier = 1 + TIERS.index(hero["tier"])
    role = hero_role(hero)
    descriptions = {
        "guardian": f"Guard: +{tier * 2} defense power when your city is challenged.",
        "rallier": f"Rally: +{tier} team power for each other equipped special citizen.",
        "specialist": f"Focus: +{tier} trait power for each sampled {HERO_TRAIT_DOMAIN[hero['specialty']]} trait.",
    }
    return {"name": hero["title"], "role": role, "effect": descriptions[role]}


def hero_battle_bonuses(heroes, selected, defending):
    power, traits, details = 0, 0, []
    for hero in heroes:
        tier = 1 + TIERS.index(hero["tier"])
        role = hero_role(hero)
        match_count = sum(trait.startswith(HERO_TRAIT_DOMAIN[hero["specialty"]] + " ") for trait in selected)
        added_power = tier * 2 if role == "guardian" and defending else tier * (len(heroes) - 1) if role == "rallier" else 0
        added_traits = tier * match_count if role == "specialist" else 0
        power += added_power
        traits += added_traits
        details.append({"name": hero["name"], "ability": hero["title"], "role": role,
                        "power_bonus": added_power, "trait_bonus": added_traits})
    return power, traits, details


def check_registration_limit(db, request: Request, now: int) -> str | None:
    if not PUBLIC_REGISTRATION_LIMIT:
        return None
    client_hash = registration_identity(request)
    db.execute("DELETE FROM registration_log WHERE created_at<?", (now - 86400,))
    count = db.execute("SELECT COUNT(*) FROM registration_log WHERE client_hash=? AND created_at>=?", (client_hash, now - 86400)).fetchone()[0]
    if count >= PUBLIC_REGISTRATION_LIMIT:
        raise HTTPException(429, "This connection has reached its daily new-city limit")
    return client_hash


def sync_residents(db, city):
    """Keep one named resident per population point without changing city rules."""
    count = max(0, int(city["population"]))
    existing = {row[0] for row in db.execute("SELECT ordinal FROM residents WHERE city_id=?", (city["id"],))}
    if existing:
        db.execute("DELETE FROM residents WHERE city_id=? AND ordinal>=?", (city["id"], count))
    for ordinal in range(count):
        if ordinal not in existing:
            name, race = citizen_identity(city["id"], ordinal)
            db.execute("INSERT INTO residents (city_id,ordinal,name,race) VALUES (?,?,?,?)", (city["id"], ordinal, name, race))


def resident_view(row):
    return {"name": row["name"], "race": row["race"], "preferred_enemy": PREFERRED_ENEMY[row["race"]]}


def city_bonuses(city, nodes=None):
    result = tech_bonuses(nodes if nodes is not None else json.loads(city["tech_nodes"]))
    for name, amount in specialization_bonus(city).items():
        result[name] += amount
    return result


def daily_tick(db, city, now):
    active = db.execute("SELECT * FROM research_queue WHERE city_id=?", (city["id"],)).fetchone()
    if active and now >= active["ready_at"]:
        owned = set(json.loads(city["tech_nodes"]))
        owned.add(active["node_id"])
        db.execute("UPDATE cities SET tech_nodes=? WHERE id=?", (json.dumps(sorted(owned)), city["id"]))
        db.execute("DELETE FROM research_queue WHERE city_id=?", (city["id"],))
        city = db.execute("SELECT * FROM cities WHERE id=?", (city["id"],)).fetchone()
    token_hours = min(720, max(0, (now - city["last_token"]) // TOKEN_SECONDS))
    if token_hours:
        db.execute("UPDATE cities SET tokens=MIN(?,tokens+?),last_token=? WHERE id=?", (MAX_TOKENS, token_hours * DAILY_TOKENS, city["last_token"] + token_hours * TOKEN_SECONDS, city["id"]))
        city = db.execute("SELECT * FROM cities WHERE id=?", (city["id"],)).fetchone()
    income_hours = min(720, max(0, (now - city["last_income"]) // 3600))
    if income_hours:
        levels = json.loads(city["upgrades"])
        nodes = set(json.loads(city["tech_nodes"]))
        bonuses = city_bonuses(city, nodes)
        bank = json.loads(city["growth_bank"])
        values = {stat: city[stat] for stat in ("food", "morale", "tech", "wealth")}
        for stat in values:
            rate = (.001 * (1 + levels.get(stat, 0)) + bonuses[f"growth_{stat}"]) * (bonuses["growth_tech_multiplier"] if stat == "tech" else 1)
            accrued = round(bank.get(stat, 0) + rate * income_hours, 6)
            whole = int(accrued)
            values[stat] = min(STAT_LIMITS[stat][1], values[stat] + whole)
            bank[stat] = 0 if values[stat] >= STAT_LIMITS[stat][1] else round(accrued - whole, 6)
        hourly_cash = round((.1 + .02 * city["wealth"] + bonuses["cash_flat"]) * (1 + .15 * levels.get("income", 0) + bonuses["cash_multiplier"]), 4)
        db.execute("UPDATE cities SET cash=ROUND(cash+?,4),last_income=?,growth_bank=?,food=?,morale=?,tech=?,wealth=? WHERE id=?",
                   (hourly_cash * income_hours, city["last_income"] + 3600 * income_hours, json.dumps(bank), values["food"], values["morale"], values["tech"], values["wealth"], city["id"]))
        city = db.execute("SELECT * FROM cities WHERE id=?", (city["id"],)).fetchone()
    passed = min(365, max(0, (now - city["last_day"]) // DAY_SECONDS))
    if not passed:
        return city
    # The same fixed economic tick runs for offline players. A city can grow or shrink.
    food = city["food"]
    population = city["population"]
    wealth = city["wealth"]
    morale = city["morale"]
    tech = city["tech"]
    weirdness = city["weirdness"]
    traits = json.loads(city["traits"])
    food_skill = round(sum(traits[f"Food {facet.title()}"] for facet in FACETS) / len(FACETS))
    market_skill = round(sum(traits[f"Market {facet.title()}"] for facet in FACETS) / len(FACETS))
    civic_skill = round(sum(traits[f"Civic {facet.title()}"] for facet in FACETS) / len(FACETS))
    hero_bonus = {"wealth": 0, "food": 0, "morale": 0, "tech": 0}
    for hero in db.execute("SELECT tier,specialty FROM heroes WHERE city_id=? AND slot IS NOT NULL", (city["id"],)):
        hero_bonus[hero["specialty"]] += 1 + TIERS.index(hero["tier"])
    for building in db.execute("SELECT blueprint_id FROM city_buildings WHERE city_id=?", (city["id"],)):
        for stat, amount in BUILDING_BY_ID[building["blueprint_id"]]["daily"].items():
            hero_bonus[stat] += amount
    for day_index in range(passed):
        food = max(0, min(200, food + 5 + food_skill // 12 + tech // 35 + hero_bonus["food"] - max(4, population // 12)))
        wealth = max(0, min(200, wealth + max(1, population // 20) + market_skill // 25 + hero_bonus["wealth"] - 4))
        tech = max(0, min(200, tech + hero_bonus["tech"]))
        if food < 5:
            population = max(10, population - 2)
            morale = max(0, morale - 3)
        elif food > 35 and morale > 45:
            population = min(500, population + 1)
        if wealth < 10:
            morale = max(0, morale - 2)
        elif wealth >= 100:
            morale = min(100, morale + 1)
        morale = min(100, morale + (1 if civic_skill >= 45 else 0) + hero_bonus["morale"])
        weirdness = min(weirdness_cap(city, city["last_day"] + (day_index + 1) * DAY_SECONDS), weirdness + 1)
    db.execute("UPDATE cities SET last_day=?,population=?,food=?,wealth=?,morale=?,tech=?,weirdness=? WHERE id=?", (city["last_day"] + passed * DAY_SECONDS, population, food, wealth, morale, tech, weirdness, city["id"]))
    return db.execute("SELECT * FROM cities WHERE id=?", (city["id"],)).fetchone()


def city_view(row, private=False):
    traits = json.loads(row["traits"])
    ranked = sorted(traits.items(), key=lambda item: item[1], reverse=True)
    data = {key: row[key] for key in ("id", "owner_name", "name", "population", "wealth", "food", "morale", "tech", "weirdness")}
    data["top_traits"] = [{"name": DISPLAY_NAME[k], "value": v} for k, v in ranked[:6]]
    data["battle_shield_until"] = max(row["last_attacked"] + DEFENSE_COOLDOWN, row["created_at"] + NEW_CITY_SHIELD)
    if private:
        levels = json.loads(row["upgrades"])
        nodes = set(json.loads(row["tech_nodes"]))
        bonuses = city_bonuses(row, nodes)
        income = (.1 + .02 * row["wealth"] + bonuses["cash_flat"]) * (1 + .15 * levels.get("income", 0) + bonuses["cash_multiplier"])
        growth_rates = {stat: round((.001 * (1 + levels.get(stat, 0)) + bonuses[f"growth_{stat}"]) * (bonuses["growth_tech_multiplier"] if stat == "tech" else 1), 4) for stat in ("food", "morale", "tech", "wealth")}
        data.update(tokens=row["tokens"], shards=row["shards"], cores=row["cores"], cash=round(row["cash"], 3), cash_per_hour=round(income, 3), growth_bank=json.loads(row["growth_bank"]), growth_rates=growth_rates, upgrades=levels, tech_nodes=list(nodes), traits={DISPLAY_NAME[k]: v for k, v in traits.items()}, trait_categories=TRAIT_CATEGORIES, next_tokens_at=row["last_token"] + TOKEN_SECONDS, daily_tokens=DAILY_TOKENS, token_seconds=TOKEN_SECONDS, day_seconds=DAY_SECONDS, max_tokens=MAX_TOKENS, drift=drift_view(row), hero_slots=row["hero_slots"], building_slots=row["building_slots"], next_battle_at=row["last_battle"] + BATTLE_COOLDOWN, battle_cost=BATTLE_COST, specialization=row["specialization"], specialization_changed_at=row["specialization_changed_at"], specialization_next_change_at=row["specialization_changed_at"] + 86400 if row["specialization"] else 0, created_at=row["created_at"], renamed_at=row["renamed_at"])
    return data


def incoming_attack_count(db, city_id, now):
    return db.execute("SELECT COUNT(*) FROM event_log WHERE target_id=? AND actor_id<>target_id AND kind IN ('battle','cast') AND created_at>=?", (city_id, now - 86400)).fetchone()[0]


def research_duration(node):
    # Short first steps, then progressively longer projects; all durations are server-owned.
    return min(1800, 45 + 25 * len(node["requires"]) + 6 * node["tech"])


def daily_tagline(db, city, now):
    day = now // 86400
    found = db.execute("SELECT tagline FROM daily_taglines WHERE city_id=? AND day=?", (city["id"], day)).fetchone()
    if found:
        return found["tagline"]
    gentle = [
        "The town council has approved a second lunch break for the first lunch break.",
        "Our pigeons have formed a neighborhood watch. Nobody hired them.",
        "The mayor has declared the potholes a protected local species.",
        "The library now charges overdue fines in dramatic apologies.",
        "Our farmers report a bumper crop of very judgmental carrots.",
        "The town clock is five minutes fast and extremely proud of it.",
    ]
    strange = [
        "The bus route has elected itself mayor. Ridership is up.",
        "A cloud asked for zoning permission and brought three references.",
        "The sewer orchestra is rehearsing the national anthem backward.",
        "Our traffic lights have begun offering unsolicited life advice.",
        "The moon sent a complaint about our streetlights being too ambitious.",
        "The courthouse found the laws hiding in a vending machine.",
    ]
    pool = gentle if city["weirdness"] < 25 else gentle + strange
    pick = int.from_bytes(hashlib.sha256(f"{city['id']}:{day}".encode()).digest()[:8], "big") % len(pool)
    tagline = pool[pick]
    db.execute("INSERT INTO daily_taglines VALUES (?,?,?)", (city["id"], day, tagline))
    db.execute("DELETE FROM daily_taglines WHERE day<?", (day - 7,))
    return tagline


def prepare_daily_tagline(city_id):
    tomorrow = int(time.time()) // 86400 + 1
    with LOCK, database() as db:
        city = db.execute("SELECT name,weirdness FROM cities WHERE id=?", (city_id,)).fetchone()
        if not city or db.execute("SELECT 1 FROM daily_taglines WHERE city_id=? AND day=?", (city_id, tomorrow)).fetchone():
            return
    try:
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json={"model": OLLAMA_MODEL, "stream": False, "think": False, "options": {"num_predict": 90, "temperature": 1.2}, "messages": [{"role": "system", "content": "Write one original, funny, G-rated daily city notice, 8-22 words, in third person. Return only the sentence. For low weirdness, use ordinary small-town absurdity; for high weirdness, mild surreal comedy. Do not mention game mechanics, stats, or AI."}, {"role": "user", "content": f"City: {city['name']}. Weirdness: {city['weirdness']}/100. Make tomorrow's notice unlike a stock slogan. Nonce: {secrets.token_hex(4)}"}]}, timeout=12)
        response.raise_for_status()
        tagline = response.json()["message"]["content"].strip().strip('"')[:160]
        if not 35 <= len(tagline) <= 160 or not safe_content(tagline):
            return
        with LOCK, database() as db:
            db.execute("INSERT OR IGNORE INTO daily_taglines VALUES (?,?,?)", (city_id, tomorrow, tagline))
    except Exception:
        pass


def shop_view(city):
    levels = json.loads(city["upgrades"])
    nodes = set(json.loads(city["tech_nodes"]))
    result = []
    for item in SHOP:
        level = city["hero_slots"] - 1 if item["id"] == "hero_slot" else city["building_slots"] - 1 if item["id"] == "building_slot" else levels.get(item["id"], 0)
        maximum = 2 if item["id"] == "hero_slot" else 4 if item["id"] == "building_slot" else 20
        result.append({**item, "level": level, "max_level": maximum, "cost": item["base"] * (level + 1) ** 2, "unlocked": item["requires"] in nodes and city["tech"] >= item["tech"]})
    return result


@app.post("/api/research")
def research(data: ResearchRequest, authorization: str | None = Header(None)):
    node = TECH_BY_ID.get(data.node_id)
    if not node:
        raise HTTPException(404, "Unknown technology")
    with LOCK, database() as db:
        city = daily_tick(db, auth(db, authorization), int(time.time()))
        owned = set(json.loads(city["tech_nodes"]))
        if db.execute("SELECT 1 FROM research_queue WHERE city_id=?", (city["id"],)).fetchone():
            raise HTTPException(409, "Another research project is already running")
        if node["id"] in owned or city["tech"] < node["tech"] or not set(node["requires"]) <= owned:
            raise HTTPException(409, "This technology is not available yet")
        if city["cash"] < node["cost"]:
            raise HTTPException(409, "Not enough Cash")
        now = int(time.time())
        db.execute("UPDATE cities SET cash=ROUND(cash-?,4) WHERE id=?", (node["cost"], city["id"]))
        db.execute("INSERT INTO research_queue VALUES (?,?,?,?)", (city["id"], node["id"], now, now + research_duration(node)))
    return {"ok": True, "city": me(authorization)["city"]}


@app.post("/api/shop")
def buy_upgrade(data: PurchaseRequest, authorization: str | None = Header(None)):
    item = SHOP_BY_ID.get(data.item_id)
    if not item:
        raise HTTPException(404, "Unknown upgrade")
    with LOCK, database() as db:
        city = daily_tick(db, auth(db, authorization), int(time.time()))
        offer = next(row for row in shop_view(city) if row["id"] == item["id"])
        if not offer["unlocked"] or offer["level"] >= offer["max_level"]:
            raise HTTPException(409, "Upgrade is locked or complete")
        if city["cash"] < offer["cost"]:
            raise HTTPException(409, "Not enough Cash")
        if item["id"] == "hero_slot":
            db.execute("UPDATE cities SET cash=ROUND(cash-?,4),hero_slots=hero_slots+1 WHERE id=?", (offer["cost"], city["id"]))
        elif item["id"] == "building_slot":
            db.execute("UPDATE cities SET cash=ROUND(cash-?,4),building_slots=building_slots+1 WHERE id=?", (offer["cost"], city["id"]))
        else:
            levels = json.loads(city["upgrades"])
            levels[item["id"]] = offer["level"] + 1
            db.execute("UPDATE cities SET cash=ROUND(cash-?,4),upgrades=? WHERE id=?", (offer["cost"], json.dumps(levels), city["id"]))
    return {"ok": True, "city": me(authorization)["city"]}


def recent_feed(db, city_id=None, limit=10):
    where = "WHERE actor_id=? OR target_id=?" if city_id else ""
    kinds = [row[0] for row in db.execute(f"SELECT DISTINCT kind FROM event_log {where}", (city_id, city_id) if city_id else ())]
    rows = []
    for kind in kinds:
        condition = "WHERE l.kind=? AND (l.actor_id=? OR l.target_id=?)" if city_id else "WHERE l.kind=?"
        args = (kind, city_id, city_id, limit) if city_id else (kind, limit)
        rows.extend(db.execute(f"SELECT l.*,a.name AS actor_name,t.name AS target_name FROM event_log l JOIN cities a ON a.id=l.actor_id JOIN cities t ON t.id=l.target_id {condition} ORDER BY l.created_at DESC,l.id DESC LIMIT ?", args).fetchall())
    rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
    metadata = EVENT_BY_ID | AMBIENT_BY_ID | ERRAND_BY_ID | BUILDING_BY_ID
    result = []
    for row in rows:
        title = row["title"] or metadata.get(row["event_id"], {"name": row["event_id"]})["name"]
        if row["kind"] == "hero":
            title = re.sub(r"^(White|Green|Blue|Purple|Orange) hero joins", lambda match: f"{RARITY_LABELS[match.group(1).lower()]} citizen joins", title)
        result.append(dict(id=row["id"], kind=row["kind"], actor=row["actor_name"], target=row["target_name"], event=title,
                           icon="⚔️" if row["kind"] == "battle" else metadata.get(row["event_id"], {"icon": "🌀"})["icon"], success=bool(row["success"]),
                           story=row["story"], deltas=json.loads(row["deltas"]), changes=json.loads(row["changes"]), created_at=row["created_at"]))
    return result


@app.get("/api/health")
def health():
    return {"ok": True, "traits": len(TRAIT_NAMES), "events": len(EVENTS), "day_seconds": DAY_SECONDS, "ambient_seconds": AMBIENT_SECONDS, "invite_required": bool(INVITE_CODE)}


@app.get("/api/auth/config")
def auth_config():
    return {"google_client_id": GOOGLE_CLIENT_ID, "invite_required": bool(INVITE_CODE)}


@app.post("/api/auth/google")
def google_sign_in(data: GoogleCredential, request: Request):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google sign-in is not configured yet")
    try:
        identity = google_id_token.verify_oauth2_token(data.credential, google_requests.Request(), GOOGLE_CLIENT_ID)
        subject = identity["sub"]
    except (ValueError, KeyError):
        raise HTTPException(401, "Google could not verify that sign-in")
    except Exception:
        raise HTTPException(503, "Google verification is temporarily unavailable")
    now = int(time.time())
    session = secrets.token_urlsafe(32)
    session_hash = hashlib.sha256(session.encode()).hexdigest()
    with LOCK, database() as db:
        linked = db.execute("SELECT city_id FROM google_accounts WHERE subject=?", (subject,)).fetchone()
        if linked:
            city = db.execute("SELECT * FROM cities WHERE id=?", (linked["city_id"],)).fetchone()
        else:
            if INVITE_CODE and not secrets.compare_digest(data.invite_code, INVITE_CODE):
                raise HTTPException(403, "Invite code required")
            client_hash = check_registration_limit(db, request, now)
            given = re.sub(r"[^A-Za-z0-9]", "", identity.get("given_name", "Mayor"))[:16] or "Mayor"
            player = clean_name(given if len(given) >= 2 else "Mayor", 2, 24)
            city_id = str(uuid.uuid4())
            name = ""
            for _ in range(10):
                candidate = f"{given}ville {secrets.randbelow(9000)+1000}"
                if not db.execute("SELECT 1 FROM cities WHERE name=? COLLATE NOCASE", (candidate,)).fetchone():
                    name = candidate
                    break
            if not name:
                name = f"Mayorville {city_id[:8]}"
            rng = random.Random(int.from_bytes(hashlib.sha256(city_id.encode()).digest()[:8], "big"))
            traits = {trait: rng.randint(20, 80) for trait in TRAIT_NAMES}
            db.execute("INSERT INTO cities (id,owner_hash,owner_name,name,tokens,last_day,population,wealth,food,morale,tech,weirdness,traits,created_at,last_token,last_income) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (city_id, hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest(), player, name, 12, now, 100, 60, 60, 60, 20, 2, json.dumps(traits), now, now, now))
            db.execute("INSERT INTO google_accounts VALUES (?,?)", (subject, city_id))
            if client_hash:
                db.execute("INSERT INTO registration_log VALUES (?,?,?,?)", (str(uuid.uuid4()), client_hash, city_id, now))
            city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        db.execute("INSERT INTO google_sessions VALUES (?,?,?)", (session_hash, city["id"], now + 30*86400))
        db.execute("DELETE FROM google_sessions WHERE expires_at<?", (now,))
        return {"session_key": session, "city": city_view(city, True)}


@app.get("/api/catalog")
def catalog():
    return {"trait_names": ALL_LABELS, "categories": list(CATEGORIES), "daily_tokens": DAILY_TOKENS, "day_seconds": DAY_SECONDS, "errand_seconds": ERRAND_SECONDS, "ambient_seconds": AMBIENT_SECONDS, "invite_required": bool(INVITE_CODE)}


@app.post("/api/register")
def register(data: Register, request: Request):
    if INVITE_CODE and not secrets.compare_digest(data.invite_code, INVITE_CODE):
        raise HTTPException(403, "Invite code required")
    player = clean_name(data.player, 2, 24)
    name = clean_name(data.city, 3, 28)
    token = secrets.token_urlsafe(32)
    city_id = str(uuid.uuid4())
    now = int(time.time())
    rng = random.Random(int.from_bytes(hashlib.sha256(city_id.encode()).digest()[:8], "big"))
    traits = {trait: rng.randint(20, 80) for trait in TRAIT_NAMES}
    with LOCK, database() as db:
        if db.execute("SELECT 1 FROM cities WHERE name=? COLLATE NOCASE", (name,)).fetchone():
            raise HTTPException(409, "That city name is taken")
        client_hash = check_registration_limit(db, request, now)
        db.execute("INSERT INTO cities (id,owner_hash,owner_name,name,tokens,last_day,population,wealth,food,morale,tech,weirdness,traits,created_at,last_token,last_income) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (city_id, hashlib.sha256(token.encode()).hexdigest(), player, name, 12, now, 100, 60, 60, 60, 20, 2, json.dumps(traits), now, now, now))
        if client_hash:
            db.execute("INSERT INTO registration_log VALUES (?,?,?,?)", (str(uuid.uuid4()), client_hash, city_id, now))
        row = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
    return {"city_key": token, "city": city_view(row, True)}


@app.get("/api/me")
def me(authorization: str | None = Header(None)):
    with LOCK, database() as db:
        city = daily_tick(db, auth(db, authorization), int(time.time()))
        sync_residents(db, city)
        offers = [offer_view(row) for row in db.execute("SELECT * FROM chaos_offers WHERE city_id=? ORDER BY created_at,id", (city["id"],))]
        heroes = [dict(row) | {"ability": hero_ability(row)} for row in db.execute("SELECT * FROM heroes WHERE city_id=? ORDER BY slot IS NULL,slot,joined_at", (city["id"],))]
        buildings = [building_view(row) for row in db.execute("SELECT * FROM city_buildings WHERE city_id=? ORDER BY built_at", (city["id"],))]
        building_offers = [building_offer_view(row) for row in db.execute("SELECT * FROM prepared_buildings WHERE city_id=? ORDER BY blueprint_id", (city["id"],))]
        next_offers_at = min((row["created_at"] for row in db.execute("SELECT created_at FROM chaos_offers WHERE city_id=?", (city["id"],))), default=int(time.time())) + OFFER_SECONDS
        residents = [resident_view(row) for row in db.execute("SELECT name,race FROM residents WHERE city_id=? ORDER BY ordinal", (city["id"],))]
        active = db.execute("SELECT * FROM research_queue WHERE city_id=?", (city["id"],)).fetchone()
        private_city = city_view(city, True)
        private_city.update(incoming_attacks_24h=incoming_attack_count(db, city["id"], int(time.time())), incoming_attack_limit=INCOMING_ATTACK_LIMIT)
        return {"city": private_city, "daily_tagline": daily_tagline(db, city, int(time.time())), "research": dict(active) if active else None, "phone_server_url": PHONE_SERVER_URL, "events": offers, "shop": shop_view(city), "tech_tree": TECH_NODES, "specializations": SPECIALIZATIONS, "buildings": buildings, "building_offers": building_offers, "next_offers_at": next_offers_at, "heroes": heroes, "residents": residents, "races": list(RACES), "feed": recent_feed(db, city["id"])}


@app.post("/api/city/rename")
def rename_city(data: RenameRequest, authorization: str | None = Header(None)):
    name = clean_name(data.name, 3, 28)
    with LOCK, database() as db:
        city = auth(db, authorization)
        if city["name"].casefold() == name.casefold():
            return {"city": city_view(city, True)}
        if db.execute("SELECT 1 FROM cities WHERE name=? COLLATE NOCASE AND id<>?", (name, city["id"])).fetchone():
            raise HTTPException(409, "That city name is taken")
        db.execute("UPDATE cities SET name=?,renamed_at=? WHERE id=?", (name, int(time.time()), city["id"]))
        return {"city": city_view(db.execute("SELECT * FROM cities WHERE id=?", (city["id"],)).fetchone(), True)}


@app.post("/api/specializations")
def choose_specialization(data: SpecializationRequest, authorization: str | None = Header(None)):
    choice = SPECIALIZATION_BY_ID.get(data.specialization_id)
    if not choice:
        raise HTTPException(404, "Unknown city specialization")
    now = int(time.time())
    with LOCK, database() as db:
        city = daily_tick(db, auth(db, authorization), now)
        if city["specialization"] == choice["id"]:
            raise HTTPException(409, "Your city already has this specialization")
        if city["specialization"] and now < city["specialization_changed_at"] + 86400:
            raise HTTPException(409, "Your city can change specialization once per day")
        cost = 0 if not city["specialization"] else 25
        if city["cash"] < cost:
            raise HTTPException(409, "Changing specialization costs 25 Cash")
        db.execute("UPDATE cities SET specialization=?,specialization_changed_at=?,cash=ROUND(cash-?,4) WHERE id=?", (choice["id"], now, cost, city["id"]))
    return {"ok": True, "city": me(authorization)["city"]}


@app.get("/api/cities")
def cities(authorization: str | None = Header(None)):
    with LOCK, database() as db:
        actor = auth(db, authorization)
        now = int(time.time())
        rows = db.execute("SELECT * FROM cities ORDER BY created_at DESC LIMIT 100").fetchall()
        records = {row["id"]: {"wins": 0, "losses": 0} for row in rows}
        for fight in db.execute("SELECT actor_id,target_id,success FROM event_log WHERE kind='battle' AND created_at>=?", (now-30*86400,)):
            winner = fight["actor_id"] if fight["success"] else fight["target_id"]
            loser = fight["target_id"] if fight["success"] else fight["actor_id"]
            if winner in records: records[winner]["wins"] += 1
            if loser in records: records[loser]["losses"] += 1
        pair_attacks = {row["target_id"]: row["count"] for row in db.execute("SELECT target_id,COUNT(*) count FROM event_log WHERE kind='battle' AND actor_id=? AND created_at>=? GROUP BY target_id", (actor["id"], now-86400))}
        incoming = {row["target_id"]: row["count"] for row in db.execute("SELECT target_id,COUNT(*) count FROM event_log WHERE actor_id<>target_id AND kind IN ('battle','cast') AND created_at>=? GROUP BY target_id", (now-86400,))}
        public_cities = []
        for row in rows:
            view = city_view(daily_tick(db, row, now))
            view.update(incoming_attacks_24h=incoming.get(row["id"], 0), incoming_attack_limit=INCOMING_ATTACK_LIMIT)
            public_cities.append(view)
        return {"cities": public_cities, "battle_records": records, "pair_attacks": pair_attacks, "pair_battle_limit": PAIR_BATTLE_LIMIT}


def trade_view(row):
    return {key: row[key] for key in ("id", "sender_id", "target_id", "sender_name", "target_name",
                                       "offer_hero_id", "request_hero_id", "offer_hero_name", "request_hero_name",
                                       "offer_wealth", "request_wealth", "status", "created_at", "expires_at")}


@app.get("/api/trades")
def list_trades(authorization: str | None = Header(None)):
    with LOCK, database() as db:
        city = auth(db, authorization)
        now = int(time.time())
        db.execute("UPDATE trade_offers SET status='expired',resolved_at=? WHERE status='pending' AND expires_at<=?", (now, now))
        rows = db.execute("""SELECT o.*,s.name sender_name,t.name target_name,
                           h1.name offer_hero_name,h2.name request_hero_name FROM trade_offers o
                           JOIN cities s ON s.id=o.sender_id JOIN cities t ON t.id=o.target_id
                           LEFT JOIN heroes h1 ON h1.id=o.offer_hero_id LEFT JOIN heroes h2 ON h2.id=o.request_hero_id
                           WHERE o.sender_id=? OR o.target_id=? ORDER BY o.created_at DESC LIMIT 30""", (city["id"], city["id"])).fetchall()
        rivals = [dict(row) for row in db.execute("SELECT id,city_id,name,title,tier FROM heroes WHERE city_id<>? ORDER BY joined_at DESC LIMIT 100", (city["id"],))]
        sent_today = db.execute("SELECT COUNT(*) FROM trade_offers WHERE sender_id=? AND created_at>=?", (city["id"], now-86400)).fetchone()[0]
        pair_sent = {row["target_id"]: row["count"] for row in db.execute("SELECT target_id,COUNT(*) count FROM trade_offers WHERE sender_id=? AND created_at>=? GROUP BY target_id", (city["id"], now-86400))}
        return {"offers": [trade_view(row) for row in rows], "rival_heroes": rivals, "sent_today": sent_today, "daily_limit": TRADE_DAILY_LIMIT, "pair_sent_today": pair_sent, "pair_daily_limit": TRADE_PAIR_DAILY_LIMIT}


@app.post("/api/trades")
def propose_trade(data: TradeRequest, authorization: str | None = Header(None)):
    if not any((data.offer_hero_id, data.request_hero_id, data.offer_wealth, data.request_wealth)):
        raise HTTPException(400, "A trade must offer or request something")
    now = int(time.time())
    with LOCK, database() as db:
        sender = auth(db, authorization)
        if data.target_city_id == sender["id"]:
            raise HTTPException(400, "Choose another city")
        if not db.execute("SELECT 1 FROM cities WHERE id=?", (data.target_city_id,)).fetchone():
            raise HTTPException(404, "Target city not found")
        sent_today = db.execute("SELECT COUNT(*) FROM trade_offers WHERE sender_id=? AND created_at>=?", (sender["id"], now-86400)).fetchone()[0]
        if sent_today >= TRADE_DAILY_LIMIT:
            raise HTTPException(429, "You have reached your daily trade proposal limit")
        sent_to_target = db.execute("SELECT COUNT(*) FROM trade_offers WHERE sender_id=? AND target_id=? AND created_at>=?", (sender["id"], data.target_city_id, now-86400)).fetchone()[0]
        if sent_to_target >= TRADE_PAIR_DAILY_LIMIT:
            raise HTTPException(429, "You have sent this city enough proposals today")
        pending = db.execute("SELECT COUNT(*) FROM trade_offers WHERE sender_id=? AND status='pending' AND expires_at>?", (sender["id"], now)).fetchone()[0]
        if pending >= 3:
            raise HTTPException(409, "You already have three open trade offers")
        if db.execute("SELECT 1 FROM trade_offers WHERE sender_id=? AND created_at>?", (sender["id"], now-60)).fetchone():
            raise HTTPException(429, "Wait one minute before proposing another trade")
        for hero_id, owner in ((data.offer_hero_id, sender["id"]), (data.request_hero_id, data.target_city_id)):
            if hero_id and not db.execute("SELECT 1 FROM heroes WHERE id=? AND city_id=?", (hero_id, owner)).fetchone():
                raise HTTPException(409, "A selected citizen no longer belongs to that city")
        if sender["wealth"] < data.offer_wealth:
            raise HTTPException(409, "You do not have enough Wealth to offer")
        offer_id = str(uuid.uuid4())
        db.execute("INSERT INTO trade_offers VALUES (?,?,?,?,?,?,?,?,?,?,?)", (offer_id, sender["id"], data.target_city_id, data.offer_hero_id, data.request_hero_id, data.offer_wealth, data.request_wealth, "pending", now, now+48*3600, 0))
    return {"ok": True, "id": offer_id}


@app.post("/api/trades/{offer_id}/accept")
def accept_trade(offer_id: str, authorization: str | None = Header(None)):
    now = int(time.time())
    with LOCK, database() as db:
        target = daily_tick(db, auth(db, authorization), now)
        offer = db.execute("SELECT * FROM trade_offers WHERE id=? AND target_id=?", (offer_id, target["id"])).fetchone()
        if not offer:
            raise HTTPException(404, "Trade offer not found")
        if offer["status"] != "pending" or offer["expires_at"] <= now:
            raise HTTPException(409, "Trade offer is no longer open")
        sender = daily_tick(db, db.execute("SELECT * FROM cities WHERE id=?", (offer["sender_id"],)).fetchone(), now)
        if sender["wealth"] < offer["offer_wealth"] or target["wealth"] < offer["request_wealth"]:
            raise HTTPException(409, "A city no longer has enough Wealth")
        heroes = []
        for hero_id, owner in ((offer["offer_hero_id"], sender["id"]), (offer["request_hero_id"], target["id"])):
            if hero_id:
                hero = db.execute("SELECT * FROM heroes WHERE id=? AND city_id=?", (hero_id, owner)).fetchone()
                if not hero:
                    raise HTTPException(409, "A selected citizen has moved to another city")
                heroes.append(hero)
        db.execute("UPDATE cities SET wealth=wealth-?+? WHERE id=?", (offer["offer_wealth"], offer["request_wealth"], sender["id"]))
        db.execute("UPDATE cities SET wealth=wealth+?-? WHERE id=?", (offer["offer_wealth"], offer["request_wealth"], target["id"]))
        if offer["offer_hero_id"]:
            db.execute("UPDATE heroes SET city_id=?,slot=NULL WHERE id=?", (target["id"], offer["offer_hero_id"]))
        if offer["request_hero_id"]:
            db.execute("UPDATE heroes SET city_id=?,slot=NULL WHERE id=?", (sender["id"], offer["request_hero_id"]))
        db.execute("UPDATE trade_offers SET status='accepted',resolved_at=? WHERE id=?", (now, offer_id))
        for hero in heroes:
            db.execute("UPDATE trade_offers SET status='expired',resolved_at=? WHERE status='pending' AND id<>? AND (offer_hero_id=? OR request_hero_id=?)", (now, offer_id, hero["id"], hero["id"]))
        pieces = [f"{hero['name']} changed cities" for hero in heroes]
        if offer["offer_wealth"] or offer["request_wealth"]:
            pieces.append(f"{offer['offer_wealth']} Wealth went to {target['name']} and {offer['request_wealth']} Wealth went to {sender['name']}")
        story = f"I am {target['name']}. {sender['name']} and I signed a very official napkin. " + "; ".join(pieces) + "."
        changes = {"target_city": target["name"], "wallet_city": target["name"], "stats": {}, "traits": {}, "wallet": {},
                   "sender_wallet": {"wealth": change(sender["wealth"], sender["wealth"] - offer["offer_wealth"] + offer["request_wealth"])},
                   "target_wallet": {"wealth": change(target["wealth"], target["wealth"] + offer["offer_wealth"] - offer["request_wealth"])},
                   "sender_name": sender["name"], "target_name": target["name"],
                   "citizens": {hero["name"]: {"before": sender["name"] if hero["city_id"] == sender["id"] else target["name"], "after": target["name"] if hero["city_id"] == sender["id"] else sender["name"], "delta": 1} for hero in heroes}}
        log_id = str(uuid.uuid4())
        db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (log_id, sender["id"], target["id"], "city_trade", 1, story, "{}", now, "trade", json.dumps(changes), "The Very Official Napkin Trade"))
    title, generated = trade_story(sender["name"], target["name"], pieces, story)
    with LOCK, database() as db:
        db.execute("UPDATE event_log SET title=?,story=? WHERE id=?", (title, generated, log_id))
    return {"ok": True, "title": title, "story": generated, "changes": changes}


@app.post("/api/trades/{offer_id}/close")
def close_trade(offer_id: str, authorization: str | None = Header(None)):
    with LOCK, database() as db:
        city = auth(db, authorization)
        offer = db.execute("SELECT * FROM trade_offers WHERE id=? AND (sender_id=? OR target_id=?)", (offer_id, city["id"], city["id"])).fetchone()
        if not offer:
            raise HTTPException(404, "Trade offer not found")
        if offer["status"] != "pending":
            raise HTTPException(409, "Trade offer is already closed")
        status = "canceled" if city["id"] == offer["sender_id"] else "declined"
        db.execute("UPDATE trade_offers SET status=?,resolved_at=? WHERE id=?", (status, int(time.time()), offer_id))
    return {"ok": True, "status": status}


@app.get("/api/feed")
def feed(authorization: str | None = Header(None)):
    with database() as db:
        city = auth(db, authorization)
        return {"feed": recent_feed(db, city["id"])}


def fallback_story(event, actor, target, success):
    if not success:
        return f"I am {target}, and {actor} tried {event['name']} on me. A suspiciously competent intern stopped it; I am appointing them Minister of Not Today."
    return f"I am {target}, and {actor} unleashed {event['name']} on me. {event['tagline']} My city council insists this was mostly intentional."


def llm_story(event, actor, target, success, deltas, actor_traits, target_traits):
    fallback = fallback_story(event, actor, target, success)
    try:
        actor_top = [DISPLAY_NAME[key] for key in sorted(actor_traits, key=actor_traits.get, reverse=True)[:4]]
        target_top = [DISPLAY_NAME[key] for key in sorted(target_traits, key=target_traits.get, reverse=True)[:4]]
        payload = {"model": OLLAMA_MODEL, "stream": False, "think": False, "options": {"num_predict": 100, "temperature": 0.8}, "messages": [{"role": "system", "content": "You are the affected city itself, speaking in first person after an absurd event. Write two funny, punchy, G-rated sentences. Let your listed personality traits shape your voice. No markdown. The result and numbers are fixed. Never invent additional game effects."}, {"role": "user", "content": f"Your city: {target}. Your strongest traits: {target_top}. Actor: {actor}, strongest traits: {actor_top}. Event: {event['name']}. Success: {success}. Effects: {deltas}. Premise: {event['tagline']}"}]}
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=12)
        response.raise_for_status()
        story = response.json()["message"]["content"].strip()
        return story[:450] if story and re.search(r"\b(I|my|me)\b", story, re.IGNORECASE) else fallback
    except Exception:
        return fallback


def personality_score(traits, domain, facet):
    domain_score = sum(traits[f"{domain.title()} {name.title()}"] for name in FACETS) / len(FACETS)
    facet_score = sum(traits[f"{name.title()} {facet.title()}"] for name in DOMAINS) / len(DOMAINS)
    exact = traits[f"{domain.title()} {facet.title()}"]
    return round((domain_score + facet_score + exact) / 3)


STAT_LIMITS = {"population": (10, 500), "wealth": (0, 200), "food": (0, 200), "morale": (0, 100), "tech": (0, 200), "weirdness": (0, 200)}


def change(before, after):
    return {"before": before, "after": after, "delta": after - before}


def applied_stats(city, deltas):
    values = {}
    changes = {}
    for key, delta in deltas.items():
        lo, hi = STAT_LIMITS[key]
        if key == "weirdness":
            hi = weirdness_cap(city)
            delta = max(-2, min(2, round(delta / 8)))
        values[key] = max(lo, min(hi, city[key] + delta))
        changes[key] = change(city[key], values[key])
    return values, changes


def weirdness_cap(city, now=None):
    age_days = max(0, ((now or int(time.time())) - city["created_at"]) / 86400)
    return min(100, 5 + int(95 * age_days / RAMP_DAYS))


def drift_view(city):
    now = int(time.time())
    elapsed = max(0, now - city["created_at"])
    total = RAMP_DAYS * 86400
    next_day = city["created_at"] + (elapsed // 86400 + 1) * 86400
    return {"day": min(RAMP_DAYS, elapsed // 86400), "days_total": RAMP_DAYS,
            "progress": min(100, round(100 * elapsed / total, 2)),
            "cap": weirdness_cap(city, now), "next_ramp_at": min(city["created_at"] + total, next_day),
            "full_ramp_at": city["created_at"] + total}


def offer_view(row):
    event = EVENT_BY_ID[row["template_id"]].copy()
    event.update(id=row["id"], name=row["title"], tagline=row["tagline"])
    if row["bonus_stat"] in {"wealth", "food", "morale", "tech"}:
        event["effects"] = event["effects"].copy()
        event["effects"][row["bonus_stat"]] = event["effects"].get(row["bonus_stat"], 0) + (2 if event["kind"] == "self" else -2)
    if row["trait_domain"] in DOMAINS and row["trait_facet"] in FACETS:
        event["domain"], event["facet"] = row["trait_domain"], row["trait_facet"]
    event["trait_display"] = DISPLAY_NAME[f"{event['domain'].title()} {event['facet'].title()}"]
    return event


def job_view(row):
    task = ERRAND_BY_ID[row["template_id"]].copy()
    task.update(id=row["id"], name=row["title"], tagline=row["tagline"])
    return task


def building_offer_view(row):
    blueprint = BUILDING_BY_ID[row["blueprint_id"]]
    return {"id": row["id"], "blueprint_id": row["blueprint_id"], "name": row["title"],
            "description": row["tagline"], "icon": blueprint["icon"], "cost": blueprint["cost"],
            "daily": blueprint["daily"], "defense": blueprint["defense"]}


def building_view(row):
    blueprint = BUILDING_BY_ID[row["blueprint_id"]]
    return {"id": row["id"], "blueprint_id": row["blueprint_id"], "name": row["name"],
            "description": row["description"], "icon": blueprint["icon"], "daily": blueprint["daily"],
            "defense": blueprint["defense"], "built_at": row["built_at"]}


def available_templates(city):
    days = max(0, (int(time.time()) - city["created_at"]) // 86400)
    if days < 14:
        gentle = {"library_swap", "garden_day", "market_fair", "pigeon_union", "flyer_mixup", "parking_panic", "bureaucratic_fog", "meme_plague"}
        return [event for event in EVENTS if event["id"] in gentle]
    max_cost = 5 if days < 14 else 8 if days < 45 else 12 if days < 75 else 20
    return [event for event in EVENTS if event["cost"] <= max_cost]


def generate_offer_text(city, templates, previous):
    """The model chooses flavor and bounded mechanical twists in one batch."""
    stage = "mostly ordinary with one odd detail" if weirdness_cap(city) < 20 else "playfully surreal" if weirdness_cap(city) < 60 else "wildly absurd"
    try:
        payload = {"model": OLLAMA_MODEL, "stream": False, "think": False,
                   "format": {"type": "object", "properties": {"offers": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "tagline": {"type": "string"}, "bonus_stat": {"type": "string", "enum": ["wealth", "food", "morale", "tech"]}, "trait_domain": {"type": "string", "enum": DOMAINS}, "trait_facet": {"type": "string", "enum": FACETS}}, "required": ["title", "tagline", "bonus_stat", "trait_domain", "trait_facet"]}}}, "required": ["offers"]},
                   "options": {"num_predict": 750, "temperature": 1.05},
                   "messages": [{"role": "system", "content": "Invent fresh, funny G-rated city event offers in JSON, one per supplied template and in the same order. Every title must be distinct. The tone is " + stage + ". At the early stage, avoid aliens, hive minds, cosmic apocalypse, magic, and reality collapse. Give each offer a short title and one sentence teaser. Reinterpret the themes with new situations. Choose one bonus_stat, trait_domain, and trait_facet for each offer; vary your choices across the batch. The server will limit all effects. Never mention numbers or mechanics in the teaser."},
                                {"role": "user", "content": json.dumps({"city": city["name"], "recent_titles_to_avoid": previous[-20:], "templates": [{"theme": item["name"], "domain": item["domain"], "kind": item["kind"]} for item in templates]})}]}
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=45)
        response.raise_for_status()
        result = json.loads(response.json()["message"]["content"])["offers"]
        if len(result) != len(templates):
            raise ValueError("Incomplete offer batch")
        return result
    except Exception:
        return [{} for _ in templates]


def fill_offers(city_id):
    with LOCK, database() as db:
        city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        if not city:
            return
        existing = db.execute("SELECT template_id,title FROM chaos_offers WHERE city_id=?", (city_id,)).fetchall()
        if len(existing) >= 6:
            return
        previous = [row["title"] for row in db.execute("SELECT title FROM event_log WHERE actor_id=? AND kind='cast' AND title<>'' ORDER BY created_at DESC LIMIT 20", (city_id,))]
        previous += [row["title"] for row in existing]
        pool = available_templates(city)
        selected = []
        used = {row["template_id"] for row in existing}
        for kind in ("self", "attack"):
            choices = [item for item in pool if item["kind"] == kind and item["id"] not in used]
            random.shuffle(choices)
            selected.extend(choices[:max(0, 3 - sum(EVENT_BY_ID[row["template_id"]]["kind"] == kind for row in existing))])
        if not selected:
            return
    generated = generate_offer_text(city, selected, previous)
    adjectives = ("Unexpected", "Suspicious", "Remarkable", "Unauthorized", "Perplexing", "Ceremonial", "Accidental", "Unscheduled")
    now = int(time.time())
    with LOCK, database() as db:
        for template, item in zip(selected, generated):
            title = re.sub(r"\s+", " ", str(item.get("title", ""))).strip(" .!?\"'")[:70]
            tagline = re.sub(r"\s+", " ", str(item.get("tagline", ""))).strip()[:170]
            too_wild = weirdness_cap(city) < 20 and re.search(r"alien|hive|clone|gravity|cosmic|moon|meteor|portal|reality|apocalyp|sentient|dimension|quantum|dragon", title + " " + tagline, re.I)
            if len(title) < 8 or len(tagline) < 15 or too_wild or not safe_content(title, tagline):
                title = f"{random.choice(adjectives)} {template['domain'].title()} Incident {secrets.randbelow(9000) + 1000}"
                tagline = f"A peculiar local situation tests the city's {template['domain']} instincts."
            content_hash = hashlib.sha256(title.casefold().encode()).hexdigest()
            bonus_stat = item.get("bonus_stat") if item.get("bonus_stat") in {"wealth", "food", "morale", "tech"} else random.choice(("wealth", "food", "morale", "tech"))
            trait_domain = item.get("trait_domain") if item.get("trait_domain") in DOMAINS else random.choice(DOMAINS)
            trait_facet = item.get("trait_facet") if item.get("trait_facet") in FACETS else random.choice(FACETS)
            try:
                db.execute("INSERT INTO used_content VALUES (?,?)", (content_hash, now))
                db.execute("INSERT INTO chaos_offers (id,city_id,template_id,title,tagline,created_at,bonus_stat,trait_domain,trait_facet) VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), city_id, template["id"], title, tagline, now, bonus_stat, trait_domain, trait_facet))
            except sqlite3.IntegrityError:
                continue


def fill_prepared_jobs(city_id):
    with LOCK, database() as db:
        city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        if not city:
            return
        existing = {row["template_id"] for row in db.execute("SELECT template_id FROM prepared_jobs WHERE city_id=?", (city_id,))}
        templates = [task for task in ERRANDS if task["id"] not in existing]
        if not templates:
            return
    try:
        schema = {"type": "object", "properties": {"jobs": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "tagline": {"type": "string"}}, "required": ["title", "tagline"]}}}, "required": ["jobs"]}
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json={"model": OLLAMA_MODEL, "stream": False, "think": False, "format": schema, "options": {"num_predict": 330, "temperature": 0.95}, "messages": [{"role": "system", "content": "Invent one playful, G-rated mayor job for each supplied theme in the same order. Give each a short action title and one sentence description. Start gently odd, like a quirky town, not a cosmic disaster. Do not describe stat effects. Return JSON only."}, {"role": "user", "content": json.dumps({"city": city["name"], "themes": [{"name": t["name"], "purpose": list(t["effects"])} for t in templates]})}]}, timeout=40)
        response.raise_for_status()
        generated = json.loads(response.json()["message"]["content"])["jobs"]
        if len(generated) != len(templates):
            raise ValueError("Incomplete job batch")
    except Exception:
        generated = [{} for _ in templates]
    now = int(time.time())
    with LOCK, database() as db:
        for task, item in zip(templates, generated):
            title = re.sub(r"\s+", " ", str(item.get("title", ""))).strip(" .!?\"'")[:65]
            tagline = re.sub(r"\s+", " ", str(item.get("tagline", ""))).strip()[:160]
            if len(title) < 7 or len(tagline) < 12 or not safe_content(title, tagline):
                title = f"{random.choice(('Friendly', 'Odd', 'Neighborhood', 'Tuesday'))} {task['name']} {secrets.randbelow(900)+100}"
                tagline = task["tagline"]
            content_hash = hashlib.sha256(("job:" + title.casefold()).encode()).hexdigest()
            try:
                db.execute("INSERT INTO used_content VALUES (?,?)", (content_hash, now))
                db.execute("INSERT INTO prepared_jobs VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), city_id, task["id"], title, tagline, now))
            except sqlite3.IntegrityError:
                continue


def fill_prepared_heroes(city_id):
    with LOCK, database() as db:
        city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        if not city:
            return
        owned = db.execute("SELECT COUNT(*) FROM heroes WHERE city_id=?", (city_id,)).fetchone()[0]
        available = db.execute("SELECT COUNT(*) FROM prepared_heroes WHERE city_id=?", (city_id,)).fetchone()[0]
        count = min(3 - available, 30 - owned - available)
        if count <= 0:
            return
        traits = json.loads(city["traits"])
        top = [DISPLAY_NAME[key] for key in sorted(traits, key=traits.get, reverse=True)[:5]]
    cap = weirdness_cap(city)
    tier_options = ["white", "green"] if cap < 20 else ["white", "green", "blue"] if cap < 60 else list(TIERS)
    weights = [65, 35] if len(tier_options) == 2 else [48, 35, 17] if len(tier_options) == 3 else [45, 30, 16, 7, 2]
    specs = [{"tier": random.choices(tier_options, weights=weights)[0], "specialty": random.choice(("wealth", "food", "morale", "tech"))} for _ in range(count)]
    try:
        schema = {"type": "object", "properties": {"heroes": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "title": {"type": "string"}}, "required": ["name", "title"]}}}, "required": ["heroes"]}
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json={"model": OLLAMA_MODEL, "stream": False, "think": False, "format": schema, "options": {"num_predict": 260, "temperature": 1}, "messages": [{"role": "system", "content": "Invent a different memorable, funny, G-rated city resident for each supplied specification, in order. Give each a short personal name and eccentric job title. Reflect the city's personality. Early cities should feel gently odd, not apocalyptic. Return JSON only."}, {"role": "user", "content": json.dumps({"city": city["name"], "traits": top, "heroes": specs, "reality_drift_cap": cap})}]}, timeout=40)
        response.raise_for_status()
        generated = json.loads(response.json()["message"]["content"])["heroes"]
        if len(generated) != count:
            raise ValueError("Incomplete hero batch")
    except Exception:
        generated = [{} for _ in specs]
    now = int(time.time())
    with LOCK, database() as db:
        for spec, item in zip(specs, generated):
            name = re.sub(r"\s+", " ", str(item.get("name", ""))).strip(" .!?\"'")[:42]
            title = re.sub(r"\s+", " ", str(item.get("title", ""))).strip(" .!?\"'")[:62]
            if len(name) < 3 or len(title) < 5 or not safe_content(name, title):
                name = f"{random.choice(('Ada', 'Milo', 'Juniper', 'Basil', 'Nora', 'Pip'))} {random.choice(('Bell', 'Finch', 'Quill', 'Moss', 'Wren'))} {secrets.randbelow(90)+10}"
                title = f"{spec['specialty'].title()} Department Volunteer"
            content_hash = hashlib.sha256(("hero:" + name.casefold()).encode()).hexdigest()
            try:
                db.execute("INSERT INTO used_content VALUES (?,?)", (content_hash, now))
                db.execute("INSERT INTO prepared_heroes VALUES (?,?,?,?,?,?,?)", (str(uuid.uuid4()), city_id, name, title, spec["tier"], spec["specialty"], now))
            except sqlite3.IntegrityError:
                continue


def fill_resident_names(city_id):
    """Replace deterministic fallback names in small batches with local AI names."""
    with LOCK, database() as db:
        city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        if not city:
            return
        sync_residents(db, city)
        pending = db.execute("SELECT ordinal,name,race FROM residents WHERE city_id=? AND ai_named=0 ORDER BY ordinal LIMIT 20", (city_id,)).fetchall()
        if not pending:
            return
        existing = {row[0].casefold() for row in db.execute("SELECT name FROM residents WHERE city_id=?", (city_id,))}
    try:
        schema = {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"}}}, "required": ["names"]}
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json={"model": OLLAMA_MODEL, "stream": False, "think": False, "format": schema, "options": {"num_predict": 420, "temperature": 1.1}, "messages": [{"role": "system", "content": "Invent one distinct, gently funny, G-rated first and last name for each city resident in order. Their race is already decided. Do not add numbers, titles, commentary, or existing names. Return JSON with a names array only."}, {"role": "user", "content": json.dumps({"city": city["name"], "residents": [{"race": row["race"]} for row in pending]})}]}, timeout=35)
        response.raise_for_status()
        names = json.loads(response.json()["message"]["content"])["names"]
        if len(names) != len(pending):
            return
    except Exception:
        return
    with LOCK, database() as db:
        for row, candidate in zip(pending, names):
            name = re.sub(r"\s+", " ", str(candidate)).strip(" .!?\"'")[:42]
            if not 3 <= len(name) <= 42 or not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", name) or not safe_content(name):
                continue
            if name.casefold() in existing:
                name = f"{name} {row['ordinal']+1}"
            existing.add(name.casefold())
            db.execute("UPDATE residents SET name=?,ai_named=1 WHERE city_id=? AND ordinal=? AND ai_named=0", (name, city_id, row["ordinal"]))


def fill_prepared_buildings(city_id):
    with LOCK, database() as db:
        city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        if not city:
            return
        owned = {row["blueprint_id"] for row in db.execute("SELECT blueprint_id FROM city_buildings WHERE city_id=?", (city_id,))}
        existing = {row["blueprint_id"] for row in db.execute("SELECT blueprint_id FROM prepared_buildings WHERE city_id=?", (city_id,))}
        blueprints = [item for item in BUILDING_BLUEPRINTS if item["id"] not in owned | existing]
        if not blueprints:
            return
    try:
        schema = {"type": "object", "properties": {"buildings": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}}, "required": ["name", "description"]}}}, "required": ["buildings"]}
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json={"model": OLLAMA_MODEL, "stream": False, "think": False, "format": schema, "options": {"num_predict": 420, "temperature": 0.95}, "messages": [{"role": "system", "content": "Name each special building for this funny city, in the same order as the themes. Invent distinct names and one short G-rated description each. Keep the opening-game tone mildly odd. Do not claim extra game effects. Return JSON only."}, {"role": "user", "content": json.dumps({"city": city["name"], "themes": [item["theme"] for item in blueprints]})}]}, timeout=45)
        response.raise_for_status()
        generated = json.loads(response.json()["message"]["content"])["buildings"]
        if len(generated) != len(blueprints):
            raise ValueError("Incomplete building batch")
    except Exception:
        generated = [{} for _ in blueprints]
    now = int(time.time())
    with LOCK, database() as db:
        for blueprint, item in zip(blueprints, generated):
            title = re.sub(r"\s+", " ", str(item.get("name", ""))).strip(" .!?\"'")[:60]
            tagline = re.sub(r"\s+", " ", str(item.get("description", ""))).strip()[:165]
            if len(title) < 7 or len(tagline) < 15 or not safe_content(title, tagline):
                title = f"The {blueprint['name']} No. {secrets.randbelow(900)+100}"
                tagline = f"A local {blueprint['theme']} with a surprising sense of civic pride."
            original_title = title
            suffix = 2
            while (db.execute("SELECT 1 FROM city_buildings WHERE lower(name)=lower(?)", (title,)).fetchone()
                   or db.execute("SELECT 1 FROM prepared_buildings WHERE lower(title)=lower(?)", (title,)).fetchone()
                   or db.execute("SELECT 1 FROM used_content WHERE content_hash=?", (hashlib.sha256(("building:" + title.casefold()).encode()).hexdigest(),)).fetchone()):
                title = f"{original_title[:50]} No. {suffix}"
                suffix += 1
            content_hash = hashlib.sha256(("building:" + title.casefold()).encode()).hexdigest()
            try:
                db.execute("INSERT INTO used_content VALUES (?,?)", (content_hash, now))
                db.execute("INSERT INTO prepared_buildings VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), city_id, blueprint["id"], title, tagline, now))
            except sqlite3.IntegrityError:
                continue


@app.post("/api/events")
def cast(data: Cast, authorization: str | None = Header(None)):
    now = int(time.time())
    with LOCK, database() as db:
        actor = daily_tick(db, auth(db, authorization), now)
        offer = db.execute("SELECT * FROM chaos_offers WHERE id=? AND city_id=?", (data.event_id, actor["id"])).fetchone()
        if not offer:
            raise HTTPException(404, "This chaos choice is no longer available")
        event = offer_view(offer)
        target_id = actor["id"] if event["kind"] == "self" else data.target_city_id
        if event["kind"] == "attack" and (not target_id or target_id == actor["id"]):
            raise HTTPException(400, "Pick another player's city")
        target = db.execute("SELECT * FROM cities WHERE id=?", (target_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Target city not found")
        target = daily_tick(db, target, now)
        if event["kind"] == "attack":
            if now < target["created_at"] + NEW_CITY_SHIELD:
                raise HTTPException(409, "This new city is protected for its first hour")
            if now < target["last_attacked"] + DEFENSE_COOLDOWN:
                raise HTTPException(409, "This city is recovering from an attack")
            if incoming_attack_count(db, target_id, now) >= INCOMING_ATTACK_LIMIT:
                raise HTTPException(409, "This city has reached its daily defense limit")
        if actor["tokens"] < event["cost"]:
            raise HTTPException(409, "Not enough Chaos Tokens")
        if actor["shards"] < event["shard_cost"]:
            raise HTTPException(409, "Not enough Anomaly Shards")
        if actor["cores"] < event["core_cost"]:
            raise HTTPException(409, "Not enough Reality Cores")
        actor_traits = json.loads(actor["traits"])
        target_traits = json.loads(target["traits"])
        before_trait = target_traits.copy()
        trait_name = f"{event['domain'].title()} {event['facet'].title()}"
        actor_score = personality_score(actor_traits, event["domain"], event["facet"])
        if event["kind"] == "attack":
            defense = personality_score(target_traits, "defense", "resilience")
            chance = max(25, min(85, 60 + (actor_score - defense) // 3))
        else:
            chance = 100
        success = secrets.randbelow(100) < chance
        strength = max(0.75, min(1.25, 1 + (actor_score - 50) / 100))
        deltas = {key: round(value * strength) or (1 if value > 0 else -1) for key, value in event["effects"].items()} if success else {"weirdness": 2}
        changed, stat_changes = applied_stats(target, deltas)
        target_traits[trait_name] = max(0, min(100, target_traits[trait_name] + (event["trait"] if success else 2)))
        db.execute("UPDATE cities SET tokens=tokens-?,shards=shards-?,cores=cores-? WHERE id=?", (event["cost"], event["shard_cost"], event["core_cost"], actor["id"]))
        db.execute("DELETE FROM chaos_offers WHERE id=?", (offer["id"],))
        columns = ",".join(f"{key}=?" for key in changed)
        db.execute(f"UPDATE cities SET {columns}, traits=? WHERE id=?", (*changed.values(), json.dumps(target_traits), target_id))
        if event["kind"] == "attack":
            db.execute("UPDATE cities SET last_attacked=? WHERE id=?", (now, target_id))
        changes = {
            "target_city": target["name"],
            "wallet_city": actor["name"],
            "stats": stat_changes,
            "traits": {DISPLAY_NAME[trait_name]: change(before_trait[trait_name], target_traits[trait_name])},
            "wallet": {
                "tokens": change(actor["tokens"], actor["tokens"] - event["cost"]),
                "shards": change(actor["shards"], actor["shards"] - event["shard_cost"]),
                "cores": change(actor["cores"], actor["cores"] - event["core_cost"]),
            },
        }
        # Commit the immutable result before asking the model for its optional news report.
        log_id = str(uuid.uuid4())
        story = fallback_story(event, actor["name"], target["name"], success)
        db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (log_id, actor["id"], target_id, event["template_id"] if "template_id" in event else offer["template_id"], int(success), story, json.dumps(deltas), now, "cast", json.dumps(changes), event["name"]))
    generated = llm_story(event, actor["name"], target["name"], success, deltas, actor_traits, target_traits)
    with LOCK, database() as db:
        db.execute("UPDATE event_log SET story=? WHERE id=?", (generated, log_id))
    return {"success": success, "story": generated, "changes": changes, "city": me(authorization)["city"]}


@app.post("/api/errands")
def do_errand(data: ErrandRequest, authorization: str | None = Header(None)):
    raise HTTPException(410, "City jobs have retired. Shards now arrive through City AI incidents.")
    now = int(time.time())
    with LOCK, database() as db:
        city = daily_tick(db, auth(db, authorization), now)
        prepared = db.execute("SELECT * FROM prepared_jobs WHERE id=? AND city_id=?", (data.task_id, city["id"])).fetchone()
        if not prepared:
            raise HTTPException(404, "This city job is no longer available")
        task = job_view(prepared)
        if now < city["last_errand"] + ERRAND_SECONDS:
            raise HTTPException(409, "City desk is on cooldown")
        values, stat_changes = applied_stats(city, task["effects"])
        progress = city["errand_progress"] + 1
        shard_gain = progress // 4
        progress %= 4
        shards_earned = city["shards_earned"] + shard_gain
        core_gain = shards_earned // 5 - city["shards_earned"] // 5
        columns = ",".join(f"{key}=?" for key in values)
        db.execute(f"UPDATE cities SET {columns},errand_progress=?,shards=shards+?,cores=cores+?,shards_earned=?,last_errand=? WHERE id=?", (*values.values(), progress, shard_gain, core_gain, shards_earned, now, city["id"]))
        db.execute("DELETE FROM prepared_jobs WHERE id=?", (prepared["id"],))
        changes = {"target_city": city["name"], "wallet_city": city["name"], "stats": stat_changes, "traits": {}, "wallet": {"shards": change(city["shards"], city["shards"] + shard_gain), "cores": change(city["cores"], city["cores"] + core_gain)}}
        story = f"I am {city['name']}. My mayor chose to {task['name'].lower()}, and I have filed the results under 'productive nonsense.'"
        db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), city["id"], city["id"], prepared["template_id"], 1, story, json.dumps(task["effects"]), now, "errand", json.dumps(changes), task["name"]))
    return {"story": story, "changes": changes, "city": me(authorization)["city"]}


def choose_ambient(city, last_id, last_title=""):
    cap = weirdness_cap(city)
    mild = {"umbrella_monopoly", "pigeon_opera", "tax_frogs", "clock_strike", "raccoon_railway"}
    medium = mild | {"sentient_loaf", "singing_sewers", "invisible_parade", "mayor_shadow"}
    allowed = mild if cap < 20 else medium if cap < 60 else {item["id"] for item in AMBIENT}
    options = [incident for incident in AMBIENT if incident["id"] != last_id and incident["id"] in allowed]
    traits = json.loads(city["traits"])
    top = [DISPLAY_NAME[key] for key in sorted(traits, key=traits.get, reverse=True)[:6]]
    fallback = options[secrets.randbelow(len(options))]
    try:
        schema = {"type": "object", "properties": {"id": {"type": "string", "enum": [incident["id"] for incident in options]}, "title": {"type": "string"}, "voice": {"type": "string"}}, "required": ["id", "title", "voice"]}
        prompt = {"model": OLLAMA_MODEL, "stream": False, "think": False, "format": schema, "options": {"num_predict": 170, "temperature": 0.9}, "messages": [{"role": "system", "content": "You are the city's odd subconscious. Choose exactly one mechanical incident id from the supplied list based on the city's personality and condition. Invent a NEW funny incident headline within that incident's theme, different from the last headline. Then speak AS the city in first person, in two funny G-rated sentences describing that invented happening. Do not add game effects or numbers. Return JSON only. Keep the tone " + ("mostly ordinary with one small odd detail" if cap < 20 else "playfully surreal" if cap < 60 else "wildly absurd") + "."}, {"role": "user", "content": json.dumps({"city": city["name"], "personality": top, "population": city["population"], "food": city["food"], "morale": city["morale"], "weirdness": city["weirdness"], "last_headline": last_title, "incident_themes": [{"id": item["id"], "premise": item["premise"]} for item in options]})}]}
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json=prompt, timeout=20)
        response.raise_for_status()
        answer = json.loads(response.json()["message"]["content"])
        selected = next((item for item in options if item["id"] == answer.get("id")), fallback)
        title = re.sub(r"\s+", " ", str(answer.get("title", ""))).strip(" .!?\"'")[:72]
        if len(title) < 6 or title.lower() == last_title.lower():
            title = selected["name"]
        voice = str(answer.get("voice", "")).strip()[:450]
        if not re.search(r"\b(I|my|me)\b", voice, re.IGNORECASE):
            voice = ""
    except Exception:
        selected, title, voice = fallback, fallback["name"], ""
    if not voice:
        voice = f"I am {city['name']}. {selected['premise']} My city council denies knowing how this started."
    return selected, title, voice


@app.post("/api/heroes/equip")
def equip_hero(data: EquipRequest, authorization: str | None = Header(None)):
    if data.slot is not None and not 0 <= data.slot < HERO_SLOTS:
        raise HTTPException(400, "Invalid hero slot")
    with LOCK, database() as db:
        city = auth(db, authorization)
        if data.slot is not None and data.slot >= city["hero_slots"]:
            raise HTTPException(409, "Buy another Hero slot first")
        hero = db.execute("SELECT * FROM heroes WHERE id=? AND city_id=?", (data.hero_id, city["id"])).fetchone()
        if not hero:
            raise HTTPException(404, "Hero not found")
        if data.slot is not None:
            db.execute("UPDATE heroes SET slot=NULL WHERE city_id=? AND slot=?", (city["id"], data.slot))
        db.execute("UPDATE heroes SET slot=? WHERE id=?", (data.slot, data.hero_id))
    return {"ok": True}


@app.post("/api/buildings")
def construct_building(data: BuildRequest, authorization: str | None = Header(None)):
    now = int(time.time())
    with LOCK, database() as db:
        city = daily_tick(db, auth(db, authorization), now)
        offer = db.execute("SELECT * FROM prepared_buildings WHERE id=? AND city_id=?", (data.offer_id, city["id"])).fetchone()
        if not offer:
            raise HTTPException(404, "This building plan is no longer available")
        blueprint = BUILDING_BY_ID[offer["blueprint_id"]]
        if db.execute("SELECT COUNT(*) FROM city_buildings WHERE city_id=?", (city["id"],)).fetchone()[0] >= city["building_slots"]:
            raise HTTPException(409, "All building slots are full")
        if city["wealth"] < blueprint["cost"]:
            raise HTTPException(409, "Not enough Wealth")
        db.execute("INSERT INTO city_buildings VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), city["id"], blueprint["id"], offer["title"], offer["tagline"], now))
        db.execute("DELETE FROM prepared_buildings WHERE id=?", (offer["id"],))
        db.execute("UPDATE cities SET wealth=wealth-? WHERE id=?", (blueprint["cost"], city["id"]))
        changes = {"target_city": city["name"], "wallet_city": city["name"], "stats": {}, "traits": {},
                   "wallet": {"wealth": change(city["wealth"], city["wealth"] - blueprint["cost"])},
                   "buildings": {offer["title"]: {"before": "planned", "after": "built", "delta": 1}}}
        story = f"I am {city['name']}. {offer['tagline']} The crew finished {offer['title']} and celebrated with a suspiciously tidy ribbon-cutting."
        db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), city["id"], city["id"], blueprint["id"], 1, story, json.dumps(blueprint["daily"]), now, "building", json.dumps(changes), f"Built {offer['title']}"))
    return {"story": story, "changes": changes, "city": me(authorization)["city"]}


def trade_story(sender, target, items, fallback):
    try:
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json={"model": OLLAMA_MODEL, "stream": False, "think": False, "format": "json", "options": {"num_predict": 160, "temperature": 1.05}, "messages": [{"role": "system", "content": "Invent a short funny G-rated headline and two-sentence story spoken by the receiving city in first person. Describe only the exact trade already completed. Do not add rewards or alter any item. JSON with title and story only."}, {"role": "user", "content": json.dumps({"sender_city": sender, "receiving_city": target, "actual_trade": items, "nonce": secrets.token_hex(4)})}]}, timeout=16)
        response.raise_for_status()
        content = json.loads(response.json()["message"]["content"])
        title = str(content.get("title", "")).strip()[:90]
        story = str(content.get("story", "")).strip()[:420]
        if 8 <= len(title) <= 90 and 35 <= len(story) <= 420 and re.search(r"\b(I|my|me)\b", story, re.I) and safe_content(title, story):
            digest = hashlib.sha256(("trade:" + title.casefold()).encode()).hexdigest()
            with LOCK, database() as db:
                if not db.execute("SELECT 1 FROM used_content WHERE content_hash=?", (digest,)).fetchone():
                    db.execute("INSERT INTO used_content VALUES (?,?)", (digest, int(time.time())))
                    return title, story
    except Exception:
        pass
    return "The Very Official Napkin Trade", fallback


def battle_story(actor, target, sampled, winner, reward):
    title = f"The {sampled[0]['name']} and {sampled[1]['name']} Incident"
    fallback = f"I am {target}. {actor} arrived with twenty arguments about my personality. {winner} won a ridiculous civic contest and claimed {reward}."
    try:
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json={"model": OLLAMA_MODEL, "stream": False, "think": False, "format": "json", "options": {"num_predict": 390, "temperature": 1.1}, "messages": [{"role": "system", "content": "Invent one unique funny G-rated city-versus-city event. Use the provided twenty traits and their scores to reflect BOTH city personalities. The result and reward are already decided; do not change them or invent more rewards. Answer JSON with short title, 2-sentence story spoken by the defending city in first person, and beats: six short funny live-commentary sentences for a battle animation. Beats must not reveal the winner or reward. No markdown."}, {"role": "user", "content": json.dumps({"attacker": actor, "defender": target, "twenty_traits": sampled, "winner": winner, "reward": reward, "nonce": secrets.token_hex(4)})}]}, timeout=18)
        response.raise_for_status()
        content = json.loads(response.json()["message"]["content"])
        proposed_title = str(content.get("title", "")).strip()[:90]
        proposed_story = str(content.get("story", "")).strip()[:480]
        if 8 <= len(proposed_title) <= 90 and 40 <= len(proposed_story) <= 480 and re.search(r"\b(I|my|me)\b", proposed_story, re.I) and safe_content(proposed_title, proposed_story):
            with LOCK, database() as db:
                digest = hashlib.sha256(proposed_title.casefold().encode()).hexdigest()
                if not db.execute("SELECT 1 FROM used_content WHERE content_hash=?", (digest,)).fetchone():
                    db.execute("INSERT INTO used_content VALUES (?,?)", (digest, int(time.time())))
                    beats = [str(line).strip()[:140] for line in content.get("beats", []) if isinstance(line, str)]
                    beats = [line for line in beats if 15 <= len(line) <= 140 and safe_content(line) and not re.search(r"\b(?:win(?:s|ning)?|won|winner|victor(?:y|ious)?|defeat(?:ed|s)?|lose|loses|lost|reward|stole|steal(?:s|ing)?|prevail(?:s|ed)?)\b", line, re.I)]
                    return proposed_title, proposed_story, beats[:8]
    except Exception:
        pass
    return title, fallback, []


@app.post("/api/battles")
def battle(data: BattleRequest, authorization: str | None = Header(None)):
    now = int(time.time())
    with LOCK, database() as db:
        actor = daily_tick(db, auth(db, authorization), now)
        if data.target_city_id == actor["id"]:
            raise HTTPException(400, "Choose another city")
        target = db.execute("SELECT * FROM cities WHERE id=?", (data.target_city_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Target city not found")
        target = daily_tick(db, target, now)
        if now < actor["last_battle"] + BATTLE_COOLDOWN:
            raise HTTPException(409, "Your challengers are resting")
        if now < target["last_attacked"] + DEFENSE_COOLDOWN:
            raise HTTPException(409, "This city is recovering from a battle")
        if now < target["created_at"] + NEW_CITY_SHIELD:
            raise HTTPException(409, "This new city is protected for its first hour")
        if incoming_attack_count(db, target["id"], now) >= INCOMING_ATTACK_LIMIT:
            raise HTTPException(409, "This city has reached its daily defense limit")
        recent_pair = db.execute("SELECT COUNT(*) FROM event_log WHERE kind='battle' AND actor_id=? AND target_id=? AND created_at>=?", (actor["id"], target["id"], now-86400)).fetchone()[0]
        if recent_pair >= PAIR_BATTLE_LIMIT:
            raise HTTPException(409, "You have challenged this city twice in the last 24 hours")
        if actor["wealth"] < BATTLE_COST:
            raise HTTPException(409, "Not enough Wealth for the challenge")
        actor_traits, target_traits = json.loads(actor["traits"]), json.loads(target["traits"])
        sync_residents(db, actor)
        sync_residents(db, target)
        actor_fighters = db.execute("SELECT name,race FROM residents WHERE city_id=? ORDER BY RANDOM() LIMIT 5", (actor["id"],)).fetchall()
        target_fighters = db.execute("SELECT name,race FROM residents WHERE city_id=? ORDER BY RANDOM() LIMIT 5", (target["id"],)).fetchall()
        duels = []
        race_edge = 0
        for challenger, defender in zip(actor_fighters, target_fighters):
            dealt = 2 if PREFERRED_ENEMY[challenger["race"]] == defender["race"] else 1
            received = 2 if PREFERRED_ENEMY[defender["race"]] == challenger["race"] else 1
            race_edge += dealt - received
            duels.append({"attacker": challenger["name"], "attacker_race": challenger["race"], "defender": defender["name"], "defender_race": defender["race"], "attacker_damage": dealt, "defender_damage": received})
        equipped_actor = db.execute("SELECT * FROM heroes WHERE city_id=? AND slot IS NOT NULL", (actor["id"],)).fetchall()
        equipped_target = db.execute("SELECT * FROM heroes WHERE city_id=? AND slot IS NOT NULL", (target["id"],)).fetchall()
        def hero_power(heroes, fighters):
            present = {fighter["race"] for fighter in fighters} | {hero["race"] for hero in heroes}
            return sum(1 + ("white", "green", "blue", "purple", "orange").index(hero["tier"]) + (3 if hero["ally_race"] in present else 0) for hero in heroes)
        attack_power = hero_power(equipped_actor, actor_fighters)
        defense_power = hero_power(equipped_target, target_fighters)
        selected = secrets.SystemRandom().sample(TRAIT_NAMES, 20)
        sampled = [{"name": DISPLAY_NAME[name], "attacker": actor_traits[name], "defender": target_traits[name]} for name in selected]
        target_defense = sum(BUILDING_BY_ID[row["blueprint_id"]]["defense"] for row in db.execute("SELECT blueprint_id FROM city_buildings WHERE city_id=?", (target["id"],)))
        # Only the sampled traits decide the match. A strong city has no global-level bonus.
        def hero_trait_bonus(heroes):
            return sum((1 + TIERS.index(hero["tier"])) * 2 for hero in heroes for trait in selected if trait.startswith(HERO_TRAIT_DOMAIN[hero["specialty"]] + " "))
        actor_trait_bonus = hero_trait_bonus(equipped_actor)
        target_trait_bonus = hero_trait_bonus(equipped_target)
        actor_power_boost, actor_trait_boost, actor_abilities = hero_battle_bonuses(equipped_actor, selected, False)
        target_power_boost, target_trait_boost, target_abilities = hero_battle_bonuses(equipped_target, selected, True)
        attack_power += actor_power_boost
        defense_power += target_power_boost
        actor_trait_bonus += actor_trait_boost
        target_trait_bonus += target_trait_boost
        difference = (sum(actor_traits[name] - target_traits[name] for name in selected) + actor_trait_bonus - target_trait_bonus) / 20
        chance = max(35, min(65, round(50 + difference / 4 + race_edge * 2 + (attack_power - defense_power) / 2 - (target_defense + city_bonuses(target)["defense"]) / 2)))
        success = secrets.randbelow(100) < chance
        winner, loser = (actor, target) if success else (target, actor)
        winner_traits, loser_traits = (actor_traits, target_traits) if success else (target_traits, actor_traits)
        stolen_hero = None
        eligible_heroes = db.execute("SELECT * FROM heroes WHERE city_id=? ORDER BY joined_at", (loser["id"],)).fetchall()
        if eligible_heroes and secrets.randbelow(100) < 30:
            stolen_hero = secrets.choice(eligible_heroes)
            db.execute("UPDATE heroes SET city_id=?,slot=NULL WHERE id=?", (winner["id"], stolen_hero["id"]))
            db.execute("UPDATE trade_offers SET status='expired',resolved_at=? WHERE status='pending' AND (offer_hero_id=? OR request_hero_id=?)", (now, stolen_hero["id"], stolen_hero["id"]))
        trait_names = secrets.SystemRandom().sample(selected, 3)
        attacker_changes, defender_changes = {}, {}
        moved = 0
        for trait_name in trait_names:
            actor_before, target_before = actor_traits[trait_name], target_traits[trait_name]
            amount = min(2, loser_traits[trait_name], 100 - winner_traits[trait_name])
            winner_traits[trait_name] += amount
            loser_traits[trait_name] -= amount
            moved += amount
            label = DISPLAY_NAME[trait_name]
            attacker_changes[label] = change(actor_before, actor_traits[trait_name])
            defender_changes[label] = change(target_before, target_traits[trait_name])
        db.execute("UPDATE cities SET traits=?,wealth=wealth-?,last_battle=? WHERE id=?", (json.dumps(actor_traits), BATTLE_COST, now, actor["id"]))
        db.execute("UPDATE cities SET traits=?,last_attacked=? WHERE id=?", (json.dumps(target_traits), now, target["id"]))
        changes = {"target_city": target["name"], "wallet_city": actor["name"], "attacker_city": actor["name"], "defender_city": target["name"], "stats": {}, "traits": {},
                   "attacker_traits": attacker_changes, "defender_traits": defender_changes,
                   "wallet": {"wealth": change(actor["wealth"], actor["wealth"] - BATTLE_COST)},
                   "sampled_traits": sampled, "win_chance": chance, "race_duels": duels, "hero_power": {"attacker": attack_power, "defender": defense_power}, "hero_trait_bonus": {"attacker": actor_trait_bonus, "defender": target_trait_bonus}, "hero_abilities": {"attacker": actor_abilities, "defender": target_abilities}}
        if stolen_hero:
            changes["citizens"] = {stolen_hero["name"]: {"before": loser["name"], "after": winner["name"], "delta": 1}}
        reward = f"{moved} trait points" + (f" and {stolen_hero['name']} joined {winner['name']}" if stolen_hero else "")
        title = f"Twenty-Trait Clash: {DISPLAY_NAME[selected[0]]}"
        log_id = str(uuid.uuid4())
        story = f"I am {target['name']}. {actor['name']} challenged me with twenty arguments. {winner['name']} earned {reward}."
        db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (log_id, actor["id"], target["id"], "trait_battle", int(success), story, json.dumps({"trait_points": moved, "hero": stolen_hero["name"] if stolen_hero else None}), now, "battle", json.dumps(changes), title))
    narrative = battle_story(actor["name"], target["name"], sampled, winner["name"], reward)
    generated_title, generated = narrative[:2]
    beats = narrative[2] if len(narrative) > 2 else []
    with LOCK, database() as db:
        db.execute("UPDATE event_log SET title=?,story=? WHERE id=?", (generated_title, generated, log_id))
    return {"success": success, "title": generated_title, "story": generated, "beats": beats, "changes": changes, "sampled_traits": sampled, "moved": moved, "stolen_hero": stolen_hero["name"] if stolen_hero else None, "chance": chance, "city": me(authorization)["city"]}


def process_ambient_city(city_id):
    now = int(time.time())
    with LOCK, database() as db:
        city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        if not city or now < city["last_ambient"] + AMBIENT_SECONDS:
            return False
        last = db.execute("SELECT event_id,title FROM event_log WHERE target_id=? AND kind='ambient' ORDER BY created_at DESC LIMIT 1", (city_id,)).fetchone()
        last_id = last["event_id"] if last else None
        last_title = last["title"] if last else ""
    incident, title, story = choose_ambient(city, last_id, last_title)
    now = int(time.time())
    with LOCK, database() as db:
        city = db.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        if not city or now < city["last_ambient"] + AMBIENT_SECONDS:
            return False
        city = daily_tick(db, city, now)
        values, stat_changes = applied_stats(city, incident["effects"])
        shard_gain = 1 if secrets.randbelow(100) < max(6, incident.get("shard_chance", 0)) else 0
        core_gain = 1 if weirdness_cap(city, now) >= 35 and secrets.randbelow(100) < 1 else 0
        columns = ",".join(f"{key}=?" for key in values)
        db.execute(f"UPDATE cities SET {columns},shards=shards+?,cores=cores+?,last_ambient=? WHERE id=?", (*values.values(), shard_gain, core_gain, now, city_id))
        changes = {"target_city": city["name"], "wallet_city": city["name"], "stats": stat_changes, "traits": {}, "wallet": {"shards": change(city["shards"], city["shards"] + shard_gain), "cores": change(city["cores"], city["cores"] + core_gain)}}
        db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), city_id, city_id, incident["id"], 1, story, json.dumps(incident["effects"]), now, "ambient", json.dumps(changes), title))
        hero = db.execute("SELECT * FROM prepared_heroes WHERE city_id=? ORDER BY created_at LIMIT 1", (city_id,)).fetchone() if secrets.randbelow(100) < 16 else None
        if hero:
            db.execute("DELETE FROM prepared_heroes WHERE id=?", (hero["id"],))
            occupied = {row["slot"] for row in db.execute("SELECT slot FROM heroes WHERE city_id=? AND slot IS NOT NULL", (city_id,))}
            free_slot = next((slot for slot in range(city["hero_slots"]) if slot not in occupied), None)
            race = secrets.choice(RACES)
            ally_race = secrets.choice([item for item in RACES if item != race])
            db.execute("INSERT INTO heroes (id,city_id,name,title,tier,specialty,slot,joined_at,race,ally_race) VALUES (?,?,?,?,?,?,?,?,?,?)", (hero["id"], city_id, hero["name"], hero["title"], hero["tier"], hero["specialty"], free_slot, now, race, ally_race))
            hero_story = f"I am {city['name']}. {hero['name']}, my new {hero['title']}, arrived with a packed lunch and an alarming amount of confidence. They are now " + ("on my active team." if free_slot is not None else "waiting for an open team slot.")
            db.execute("INSERT INTO event_log (id,actor_id,target_id,event_id,success,story,deltas,created_at,kind,changes,title) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), city_id, city_id, "hero_join", 1, hero_story, "{}", now + 1, "hero", "{}", f"{RARITY_LABELS[hero['tier']]} citizen joins: {hero['name']}"))
    return True


def ambient_worker():
    while True:
        try:
            with LOCK, database() as db:
                due = [row["id"] for row in db.execute("SELECT id FROM cities WHERE last_ambient<=? ORDER BY last_ambient LIMIT 10", (int(time.time()) - AMBIENT_SECONDS,))]
            for city_id in due:
                process_ambient_city(city_id)
        except Exception as exc:
            print(f"Ambient worker: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(20)


def content_worker():
    while True:
        try:
            with LOCK, database() as db:
                db.execute("DELETE FROM chaos_offers WHERE created_at<?", (int(time.time()) - OFFER_SECONDS,))
                city_ids = [row["id"] for row in db.execute("SELECT id FROM cities ORDER BY created_at LIMIT 50")]
            for city_id in city_ids:
                fill_offers(city_id)
                fill_prepared_heroes(city_id)
                fill_prepared_buildings(city_id)
                fill_resident_names(city_id)
                prepare_daily_tagline(city_id)
        except Exception as exc:
            print(f"Content worker: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(30)


@app.on_event("startup")
def start_ambient_worker():
    threading.Thread(target=ambient_worker, name="ambient-events", daemon=True).start()
    threading.Thread(target=content_worker, name="prepared-content", daemon=True).start()


@app.get("/")
def index():
    return FileResponse("/app/www/index.html")


@app.get("/board")
def board():
    return FileResponse("/app/www/board.html")


@app.get("/{asset_name}")
def mobile_asset(asset_name: str):
    if asset_name not in {"style.css", "extra.css", "reality.css", "app-v2.js", "qr.js", "native-app.js"}:
        raise HTTPException(404, "File not found")
    return FileResponse(f"/app/www/{asset_name}")


app.mount("/assets", StaticFiles(directory="/app/www"), name="assets")
