"""Connected, persistent city research. Every paid node has a server-side effect."""

BRANCHES = [
    ("Commerce", 130, [
        ("coin_counter", "Coin Counting Committee", 20, 12, "+0.5 Cash/hour; unlock Wealth upgrades", {"cash_flat": .5}),
        ("sock_swap", "Sock Swap Station", 25, 17, "+0.2 Cash/hour", {"cash_flat": .2}),
        ("penny_parade", "Penny Parade Permit", 33, 24, "+5% Cash income", {"cash_multiplier": .05}),
        ("moon_mint", "Moonlight Mint", 45, 35, "+2 Cash/hour", {"cash_flat": 2}),
        ("whimsy_bodega", "Bodega of Whimsy", 55, 48, "+0.002 Wealth/hour", {"growth_wealth": .002}),
        ("coupon_constellation", "Coupon Constellation", 68, 65, "+10% Cash income", {"cash_multiplier": .10}),
        ("orbiting_register", "Orbiting Register", 80, 85, "+3 Cash/hour", {"cash_flat": 3}),
        ("galactic_receipt", "Galactic Receipt Audit", 95, 110, "+0.003 Wealth/hour", {"growth_wealth": .003}),
        ("infinite_change", "Infinite Change Drawer", 115, 150, "+15% Cash income", {"cash_multiplier": .15}),
        ("cosmic_exchange", "Cosmic Sock Exchange", 140, 200, "+5 Cash/hour", {"cash_flat": 5}),
    ]),
    ("Science", 365, [
        ("soup_science", "Soup Powered Research", 25, 12, "Unlock Food and Tech upgrades; +0.001 Tech/hour", {"growth_tech": .001}),
        ("magnifying_glass", "Magic Magnifying Glass", 30, 18, "+0.001 Tech/hour", {"growth_tech": .001}),
        ("balloon_bureau", "Balloon Buoyancy Bureau", 40, 26, "+0.002 Tech/hour", {"growth_tech": .002}),
        ("thinking_hat", "Municipal Thinking Hat", 55, 40, "Double passive Tech growth", {"growth_tech_multiplier": 2}),
        ("cloud_computing", "Cloud Computing Corner", 65, 55, "+0.003 Tech/hour", {"growth_tech": .003}),
        ("glitter_lab", "The Glitter Lab", 78, 72, "+0.004 Tech/hour", {"growth_tech": .004}),
        ("clockwork_oracle", "Clockwork Oracle", 90, 95, "+0.005 Tech/hour", {"growth_tech": .005}),
        ("probability_teapot", "Probability Teapot", 105, 125, "+2 battle defense", {"defense": 2}),
        ("paradox_archive", "Paradox Archive", 125, 165, "+0.006 Tech/hour", {"growth_tech": .006}),
        ("future_manual", "Tomorrow's Instruction Manual", 150, 220, "+0.008 Tech/hour", {"growth_tech": .008}),
    ]),
    ("Food", 600, [
        ("seed_council", "Seed Council", 20, 10, "+0.001 Food/hour", {"growth_food": .001}),
        ("wiggly_kitchen", "The Wiggly Kitchen", 27, 16, "+0.001 Food/hour", {"growth_food": .001}),
        ("pickle_forecast", "Pickle Forecast Office", 36, 23, "+0.002 Food/hour", {"growth_food": .002}),
        ("cake_lake", "Cake by the Lake", 48, 33, "+0.002 Food/hour", {"growth_food": .002}),
        ("spoon_orchard", "Spoon Orchard", 58, 45, "+0.003 Food/hour", {"growth_food": .003}),
        ("toast_telescope", "Toast Telescope", 70, 62, "+0.003 Food/hour", {"growth_food": .003}),
        ("bubble_tea_barn", "Bubble Tea Barn", 84, 82, "+0.004 Food/hour", {"growth_food": .004}),
        ("moon_garden", "Moon Garden", 100, 110, "+0.005 Food/hour", {"growth_food": .005}),
        ("cosmic_compost", "Cosmic Compost", 120, 150, "+0.006 Food/hour", {"growth_food": .006}),
        ("infinite_lunch", "Infinite Lunch Break", 145, 200, "+0.008 Food/hour", {"growth_food": .008}),
    ]),
    ("Culture", 835, [
        ("pocket_parliament", "Pocket Parliament", 25, 12, "Unlock Morale upgrades; +0.001 Morale/hour", {"growth_morale": .001}),
        ("storytime_stool", "Storytime Stool", 30, 17, "+0.001 Morale/hour", {"growth_morale": .001}),
        ("hero_hall", "Hall of Questionable Heroes", 35, 22, "Unlock Hero chair purchases; +0.001 Morale/hour", {"growth_morale": .001}),
        ("puppet_parade", "Puppet Parade Ground", 48, 34, "+0.002 Morale/hour", {"growth_morale": .002}),
        ("hummingbird_hive", "Hummingbird Hive", 60, 47, "+0.003 Morale/hour", {"growth_morale": .003}),
        ("compliment_choir", "Compliment Choir", 72, 64, "+0.003 Morale/hour", {"growth_morale": .003}),
        ("yarn_yolk", "Yarn Yolk Theater", 86, 85, "+0.004 Morale/hour", {"growth_morale": .004}),
        ("festival_farm", "Festival Farm", 102, 115, "+0.005 Morale/hour", {"growth_morale": .005}),
        ("dream_mayor", "Dream Mayor Academy", 122, 155, "+0.006 Morale/hour", {"growth_morale": .006}),
        ("legendary_council", "Legendary Council of Hats", 148, 210, "+0.008 Morale/hour", {"growth_morale": .008}),
    ]),
    ("Construction", 1070, [
        ("plot_twist", "Plot Twist Permit", 35, 22, "Unlock building plot purchases; +0.001 Wealth/hour", {"growth_wealth": .001}),
        ("brick_bunny", "Brick Bunny Factory", 42, 28, "+0.001 Wealth/hour", {"growth_wealth": .001}),
        ("pillow_fort", "Pillow Fort Doctrine", 55, 35, "+5 battle defense", {"defense": 5}),
        ("upside_down_zoning", "Upside-Down Zoning", 65, 48, "+0.002 Wealth/hour", {"growth_wealth": .002}),
        ("treehouse_guild", "Treehouse Titans Guild", 78, 67, "+2 battle defense", {"defense": 2}),
        ("rainbow_road", "Rainbow Road Builders", 90, 88, "+0.003 Wealth/hour", {"growth_wealth": .003}),
        ("floating_foundry", "Floating Foundry", 105, 115, "+3 battle defense", {"defense": 3}),
        ("cloud_castle", "Cloud Castle Creations", 120, 150, "+0.004 Wealth/hour", {"growth_wealth": .004}),
        ("gravity_planner", "Gravity Planner", 140, 190, "+4 battle defense", {"defense": 4}),
        ("reality_architect", "Reality Architect", 165, 250, "+0.006 Wealth/hour", {"growth_wealth": .006}),
    ]),
]

TECH_NODES = [dict(id="city_charter", name="Officially a City", branch="Civic", tech=0, cost=5, requires=[], effect="Open the five research branches", bonus={}, x=600, y=80)]
for branch, x, specs in BRANCHES:
    for index, (node_id, name, tech, cost, effect, bonus) in enumerate(specs):
        previous = specs[index - 1][0] if index else "city_charter"
        requires = [previous]
        if node_id == "plot_twist":
            requires = ["soup_science"]
        if node_id == "pillow_fort":
            requires.append("pocket_parliament")
        if node_id == "cosmic_exchange":
            requires.append("paradox_archive")
        if node_id == "festival_farm":
            requires.append("bubble_tea_barn")
        if node_id == "reality_architect":
            requires.append("infinite_change")
        TECH_NODES.append(dict(id=node_id, name=name, branch=branch, tech=tech, cost=cost, requires=requires,
                               effect=effect, bonus=bonus, x=x + (-32 if index % 3 == 1 else 32 if index % 3 == 2 else 0), y=240 + index * 135))

TECH_BY_ID = {node["id"]: node for node in TECH_NODES}
assert len(TECH_NODES) == 51 and len(TECH_BY_ID) == len(TECH_NODES)


def tech_bonuses(owned_ids):
    result = {"cash_flat": 0.0, "cash_multiplier": 0.0, "growth_food": 0.0, "growth_morale": 0.0,
              "growth_tech": 0.0, "growth_wealth": 0.0, "growth_tech_multiplier": 1.0, "defense": 0.0}
    for node_id in owned_ids:
        node = TECH_BY_ID.get(node_id)
        if not node:
            continue
        for key, value in node["bonus"].items():
            if key == "growth_tech_multiplier":
                result[key] *= value
            else:
                result[key] += value
    return result
