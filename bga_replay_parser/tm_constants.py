"""Constants for Terra Mystica parser: faction mappings, tile names, patterns."""

import re

FACTIONS = {
    # Base game (14)
    "halflings": "plains", "cultists": "plains",
    "alchemists": "swamp", "darklings": "swamp",
    "witches": "forest", "auren": "forest",
    "mermaids": "lakes", "swarmlings": "lakes",
    "dwarves": "mountains", "engineers": "mountains",
    "giants": "wasteland", "chaosmagicians": "wasteland",
    "fakirs": "desert", "nomads": "desert",
    # Fire & Ice — Ice factions (supported)
    "icemaidens": "ice", "yetis": "ice",
    # Fan factions — standard terrains
    "timetravellers": "plains", "golddiggers": "plains",
    "goblins": "swamp", "childrenofthewyrm": "swamp",
    "chashdallah": "forest", "theenlightened": "forest",
    "atlanteans": "lakes", "wisps": "lakes",
    "conspirators": "mountains", "dyniongeifr": "mountains",
    "architects": "wasteland", "treasurers": "wasteland",
    "archivists": "desert", "djinni": "desert",
    # Fan factions — Ice
    "selkies": "ice", "snowshamans": "ice",
}

EXCLUDED_FACTIONS = {
    "shapeshifters", "riverwalkers", "changelings", "geologists",
    "dragonlords", "acolytes", "firewalkers", "kingdomofember",
}

CULT_NAMES = {
    "1": "fire", "2": "water", "3": "earth", "4": "air",
    1: "fire", 2: "water", 3: "earth", 4: "air",
}

BONUS_TYPE_NAMES = {
    "1": "priest", "2": "worker_power", "3": "6_coins", "4": "temp_ship",
    "5": "spade", "6": "cult_coins", "7": "dwelling_vp",
    "8": "trading_post_vp", "9": "big_building_vp", "10": "shipping_vp",
}

SCORING_TYPE_NAMES = {
    "1": "2vp_dwelling_priest_per_4water",
    "2": "2vp_dwelling_power_per_4fire",
    "3": "3vp_tp_spade_per_4air",
    "4": "3vp_tp_spade_per_4water",
    "5": "5vp_sh_sa_worker_per_2air",
    "6": "5vp_sh_sa_worker_per_2fire",
    "7": "2vp_spade_coin_per_earth",
    "8": "5vp_town_spade_per_4earth",
    "9": "4vp_temple_coins_per_priest",
}

FAVOR_TYPE_NAMES = {
    "1": "fire+3", "2": "water+3", "3": "earth+3", "4": "air+3",
    "5": "fire+2_town6", "6": "water+2_cult_action",
    "7": "earth+2_1w1pw", "8": "air+2_4pw",
    "9": "fire+1_3c", "10": "water+1_3vp_tp",
    "11": "earth+1_2vp_dw", "12": "air+1_pass_vp_tp",
}

RESOURCE_AMOUNT_PATTERN = re.compile(r"title='([^']+)'.*?(\w+)_amount'>(\d+)<")
