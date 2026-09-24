"""City class mechanics. Effects are fixed so generated prose cannot change balance."""

SPECIALIZATIONS = [
    dict(id="soup_stewards", name="Soup Stewards", icon="🥣", effect="+0.004 Food each hour", bonus={"growth_food": .004}),
    dict(id="coin_whisperers", name="Coin Whisperers", icon="🪙", effect="+0.4 Cash each hour", bonus={"cash_flat": .4}),
    dict(id="roof_astronomers", name="Rooftop Astronomers", icon="🔭", effect="+0.004 Tech each hour", bonus={"growth_tech": .004}),
    dict(id="civic_bards", name="Civic Bards", icon="🎺", effect="+0.004 Morale each hour", bonus={"growth_morale": .004}),
    dict(id="pillow_architects", name="Pillow Architects", icon="🛠️", effect="+0.004 Wealth each hour; +2 battle defense", bonus={"growth_wealth": .004, "defense": 2}),
]
SPECIALIZATION_BY_ID = {item["id"]: item for item in SPECIALIZATIONS}


def specialization_bonus(city):
    choice = SPECIALIZATION_BY_ID.get(city["specialization"])
    return choice["bonus"] if choice else {}
