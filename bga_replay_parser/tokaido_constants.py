"""Lookup tables for Tokaido replay parsing."""

# BGA "type_arg" -> souvenir category. (Comments are individual costs.)
SOUVENIR_TYPE_ARG_TO_CATEGORY = {
    "0": "food",      # 1
    "1": "food",      # 2
    "2": "food",      # 2
    "3": "food",      # 2
    "4": "food",      # 1
    "5": "food",      # 1
    "6": "clothing",
    "7": "clothing",
    "8": "clothing",
    "9": "clothing",
    "10": "clothing",
    "11": "clothing",
    "12": "trinket",
    "13": "trinket",
    "14": "trinket",
    "15": "trinket",
    "16": "trinket",
    "17": "trinket",
    "18": "art",      # 2
    "19": "art",      # 3
    "20": "art",      # 3
    "21": "art",      # 2
    "22": "art",      # 2
    "23": "art",      # 3
}

# BGA "position" -> "<space_type>_<index>" (index disambiguates same-type spaces)
POSITION_TO_SPACE = {
    "2": "Village_1",
    "3": "Temple_1",
    "4": "Encounter_1",
    "5": "Field_1",
    "6": "HotSpring_1",
    "7": "Mountain_1",
    "8": "Farm_1",
    "9": "Village_2",
    "10": "Temple_2",
    "11": "Encounter_2",
    "12": "Sea_1",
    "13": "Mountain_2",
    "14": "HotSpring_2",
    "15": "Inn_1",
    "16": "Sea_2",
    "17": "Temple_3",
    "18": "Farm_2",
    "19": "Field_2",
    "20": "Mountain_3",
    "21": "Encounter_3",
    "22": "Temple_4",
    "23": "HotSpring_3",
    "24": "Mountain_4",
    "25": "Sea_3",
    "26": "Village_3",
    "27": "Farm_3",
    "28": "Inn_2",
    "29": "Field_3",
    "30": "Village_4",
    "31": "Encounter_4",
    "32": "Farm_4",
    "33": "Mountain_5",
    "34": "HotSpring_4",
    "35": "Sea_4",
    "36": "Field_4",
    "37": "Temple_5",
    "38": "Farm_5",
    "39": "Encounter_5",
    "40": "Sea_5",
    "41": "Village_5",
    "42": "Inn_3",
    "43": "HotSpring_5",
    "44": "Temple_6",
    "45": "Encounter_6",
    "46": "Village_6",
    "47": "Sea_6",
    "48": "Farm_6",
    "49": "HotSpring_6",
    "50": "Encounter_7",
    "51": "Mountain_6",
    "52": "Field_5",
    "53": "Sea_7",
    "54": "Village_7",
    "55": "Inn_4",
}

# Inn meal name -> base cost (in coins).
MEAL_COST = {
    "Dango": 1, "Misoshiru": 1, "Nigirimeshi": 1,
    "Soba": 2, "Sushi": 2, "Tofu": 2, "Tempura": 2, "Yakitori": 2,
    "Donburi": 3, "Fugu": 3, "Sashimi": 3, "Tai Meshi": 3, "Udon": 3, "Unagi": 3,
}

# Legendary Object "type_arg" -> object kind (Crossroads expansion).
LEGENDARY_OBJECT_TYPE = {
    "0": "script",     # Shodo
    "1": "script",     # Emaki
    "2": "offering",   # Buppatsu
    "3": "offering",   # Ema
    "4": "sword",      # Murasame
    "5": "sword",      # Masamune
}

# Calligraphy "type_arg" -> name (Crossroads expansion).
# Names verified by joining buy events to scoring events via `calligraphy_card_type`.
CALLIGRAPHY_TYPE_ARG_TO_NAME = {
    "0": "foresight",
    "1": "contemplation",
    "2": "nostalgia",
    "3": "patience",
    "4": "perfection",
    "5": "fasting",
}

# Panorama color identifiers used in event "panorama_type" / move subtype.
# Normalized lowercase to "mountain" / "sea" / "field" before routing.
PANORAMA_COLORS = ("mountain", "sea", "field")

# Amulet "type_arg" -> amulet name. Names verified by elimination (games
# where a player bought exactly one amulet and used exactly one type).
# Lowercased for consistency with CALLIGRAPHY_TYPE_ARG_TO_NAME.
AMULET_TYPE = {
    "0": "vitality",
    "1": "fortune",
    "2": "health",
    "3": "friendship",
    "4": "hospitality",
    "5": "devotion",
}

