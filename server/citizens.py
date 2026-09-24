"""Small deterministic citizen catalog; story text and special titles come from Ollama."""

import hashlib
import random

RACES = (
    "Human", "Vampire", "Zombie", "Mummy", "Goblin", "Orc", "Wizard",
    "Elf", "Dwarf", "Troll", "Gnome", "Fairy", "Werewolf", "Ghost",
    "Merfolk", "Centaur", "Minotaur", "Harpy", "Dragonkin", "Golem",
    "Dryad", "Satyr", "Banshee", "Cyclops", "Imp", "Angel", "Demon",
    "Alien", "Robot", "Slime", "Mushroom Folk", "Skeleton", "Kobold",
    "Naga", "Phoenix Folk", "Time Traveler",
)
PREFERRED_ENEMY = {race: RACES[(index + 7) % len(RACES)] for index, race in enumerate(RACES)}
FIRST = ("Ada", "Basil", "Cleo", "Dara", "Elio", "Faye", "Gus", "Hana", "Ivo", "Juno", "Kira", "Luca", "Mara", "Nico", "Oona", "Pip", "Quinn", "Rhea", "Sage", "Tavi", "Uma", "Vera", "Wren", "Xavi", "Yara", "Zed")
LAST = ("Acorn", "Bell", "Cloud", "Drift", "Elm", "Finch", "Grove", "Hearth", "Ivy", "Jasper", "Kettle", "Lark", "Moss", "Nettle", "Oak", "Puddle", "Quill", "River", "Sparrow", "Thistle", "Umbra", "Vale", "Wick", "Yarrow")


def citizen_identity(city_id: str, ordinal: int) -> tuple[str, str]:
    seed = hashlib.sha256(f"{city_id}:{ordinal}".encode()).digest()
    rng = random.Random(int.from_bytes(seed[:8], "big"))
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)} {ordinal + 1}"
    return name, rng.choice(RACES)
