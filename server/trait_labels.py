"""Distinct public names for the 320 persistent personality weights.

The order maps onto the original 20 x 16 stored weights, preserving existing cities.
"""

GROUPS = {
    "civic": "Public Trust|Council Infighting|Mayor Mythmaking|Referendum Fever|Queue Discipline|Street Assembly|Ordinance Acrobatics|Volunteer Spirit|Petition Persistence|Neighborhood Pride|Protest Wit|Town Hall Transparency|Civic Amnesia|Jury Independence|Curfew Flexibility|Festival Permits",
    "market": "Barter Instinct|Shopkeeper Nerve|Debt Appetite|Price Haggling|Pawnshop Luck|Merchant Gossip|Black Market Etiquette|Coin Hoarding|Supply Agility|Coupon Obsession|Warehouse Ingenuity|Bazaar Diplomacy|Rent Tolerance|Auction Mayhem|Artisan Demand|Payroll Reliability",
    "science": "Lab Inquiry|Experiment Safety|Gadget Tinkering|Research Patience|Peer Review Snark|Patent Hunger|Telescope Precision|Quantum Skepticism|Prototype Bravery|Data Honesty|Failure Recycling|Inventor Ego|Rocket Calculus|Robot Sympathy|Discovery Momentum|Mad Genius Density",
    "food": "Bakery Ambition|Soup Consensus|Snack Smuggling|Harvest Wisdom|Pickle Preservation|Cafeteria Daring|Spice Addiction|Rooftop Farming|Feast Generosity|Leftover Alchemy|Fermentation Talent|Lunch Bell Obedience|Dessert Politics|Fish Market Funk|Potato Resilience|Edible Architecture",
    "weather": "Umbrella Readiness|Storm Bargaining|Sunbeam Greed|Blizzard Improvisation|Fog Navigation|Thunder Worship|Heatwave Endurance|Rain Dance Accuracy|Cloud Reading|Windmill Cooperation|Hail Avoidance|Puddle Enthusiasm|Seasonal Memory|Lightning Nerves|Tornado Etiquette|Forecast Suspicion",
    "cosmic": "Meteor Manners|Alien Hospitality|Orbit Anxiety|Stargazing Stamina|Gravity Respect|Moon Mining Zeal|Planetary Humility|Comet Insurance|Void Listening|Constellation Gossip|Satellite Reverence|Asteroid Opportunism|Eclipse Superstition|Space Junk Salvage|Galactic Courtesy|Black Hole Denial",
    "magic": "Spell Hygiene|Wand Control|Potion Reliability|Curse Detection|Wizard Payroll|Enchantment Taxation|Familiar Loyalty|Portal Caution|Rune Literacy|Hex Resistance|Crystal Empathy|Charm Accuracy|Broomstick Traffic|Witchcraft Licensing|Sorcerer Rivalry|Prophecy Interpretation",
    "ecology": "Tree Kinship|River Patience|Moss Appreciation|Pollinator Protection|Soil Recovery|Swamp Hospitality|Wildflower Ambush|Squirrel Negotiation|Compost Engineering|Forest Silence|Reef Empathy|Air Purity|Fungus Research|Wetland Respect|Recycling Compulsion|Volcano Restraint",
    "architecture": "Pothole Philosophy|Bridge Confidence|Staircase Mysticism|Roof Resilience|Window Curiosity|Tunnel Secrecy|Plaza Sociability|Elevator Trust|Wall Humor|Basement Lore|Tower Envy|Sidewalk Flow|Doorway Drama|Fountain Ambition|Alley Awareness|Chimney Style",
    "fashion": "Hat Authority|Cape Practicality|Sock Solidarity|Uniform Rebellion|Neon Tolerance|Glitter Restraint|Runway Gossip|Vintage Loyalty|Shoe Innovation|Pocket Capacity|Color Courage|Scarf Industry|Costume Timing|Textile Recycling|Dress Code Defiance|Eyebrow Prestige",
    "transport": "Tram Loyalty|Bus Punctuality|Bicycle Swagger|Traffic Patience|Crosswalk Respect|Boat Readiness|Horse Nostalgia|Taxi Honesty|Jetpack Risk|Tunnel Speed|Delivery Coordination|Pedestrian Power|Parking Mercy|Road Trip Spirit|Zeppelin Readiness|Scooter Diplomacy",
    "diplomacy": "Border Politeness|Treaty Memory|Embassy Wit|Gift Calibration|Rival Respect|Alliance Hunger|Apology Timing|Negotiation Stamina|Peacekeeping Nerve|Spy Detection|Summit Fashion|Cultural Fluency|Ultimatum Restraint|Ambassador Ego|Truce Reliability|Foreign Curiosity",
    "defense": "Gate Discipline|Watchtower Alertness|Shield Craft|Panic Control|Militia Morale|Decoy Ingenuity|Alarm Reliability|Fortress Patience|Rooftop Vigilance|Siege Endurance|Secret Passage Knowledge|Drill Enthusiasm|Cannon Restraint|Evacuation Grace|Guard Dog Loyalty|Strategic Napping",
    "dream": "Lucid Ambition|Nightmare Composting|Pillow Diplomacy|Bedtime Order|Sleepwalking Routes|Daydream Productivity|Moonlit Nostalgia|Blanket Security|Dream Journal Honesty|Insomnia Creativity|Yawn Contagion|Snore Harmony|Imagination Overflow|Midnight Resolve|Dreamcatcher Skill|Nap Economics",
    "animal": "Pigeon Politics|Raccoon Agency|Cat Sovereignty|Dog Optimism|Goose Intimidation|Rat Engineering|Llama Diplomacy|Beaver Construction|Otter Mischief|Crow Memory|Frog Timing|Moth Devotion|Goat Appetite|Octopus Planning|Ferret Curiosity|Chicken Courage",
    "bureaucracy": "Form Multiplication|Stamp Authority|Clerk Empathy|Filing Accuracy|Permit Delay|Ledger Obsession|Signature Panic|Archive Dust|Meeting Fatigue|Regulation Elasticity|Audit Ferocity|Desk Arrangement|Policy Acrobatics|Application Mercy|Department Rivalry|Budget Fog",
    "festival": "Parade Coordination|Confetti Supply|Dance Floor Courage|Firework Restraint|Mascot Charisma|Carnival Luck|Costume Rivalry|Float Engineering|Street Music Pulse|Party Recovery|Ticket Tinkering|Balloon Logistics|Midnight Revelry|Stage Fright|Crowd Harmony|Celebration Excess",
    "memory": "Historian Honesty|Museum Dust|Ancestor Respect|Rumor Retention|Monument Pride|Forgotten Names|Oral Tradition|Time Capsule Discipline|Archive Curiosity|Nostalgia Surge|Collective Trauma|Birthday Precision|Legend Inflation|Photograph Evidence|Historical Revision|Memoir Wit",
    "machinery": "Gear Patience|Engine Appetite|Wire Discipline|Steam Pressure|Conveyor Timing|Automaton Rights|Battery Hoarding|Circuit Empathy|Factory Tempo|Repair Ingenuity|Rust Tolerance|Oil Diplomacy|Magnet Mischief|Clockwork Trust|Assembly Rhythm|Scrap Utilization",
    "mystery": "Secret Keeping|Clue Hunger|Disguise Skill|Ghost Etiquette|Unsolved Panic|Hidden Door Instinct|Conspiracy Filter|Detective Stamina|Shadow Reading|Coincidence Faith|Cipher Fluency|Vanishing Discipline|Whisper Networks|Moonlit Investigation|Artifact Suspicion|Occult Paperwork",
}

GROUPS = {domain: labels.split("|") for domain, labels in GROUPS.items()}
ALL_LABELS = [label for labels in GROUPS.values() for label in labels]
assert len(GROUPS) == 20
assert all(len(labels) == 16 for labels in GROUPS.values())
assert len(ALL_LABELS) == len(set(ALL_LABELS)) == 320
