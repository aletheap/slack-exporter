#!/usr/bin/env python3
"""
Slack Export HTML Renderer

Converts a Slack export directory (produced by slack_exporter.py) into
a set of browsable HTML pages with user avatars, reactions, threads, and
file attachments.

Usage:
  python slack_html.py <export_dir>
  python slack_html.py <export_dir> --channel engineering --channel general
"""

import argparse
import html
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    print("Error: tqdm not installed.  Run: pip install tqdm")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Common Slack emoji name → Unicode character  (~130 entries)
# ---------------------------------------------------------------------------

UNICODE_EMOJI = {
    # ── Smileys & faces ────────────────────────────────────────────────
    "grinning": "😀", "smiley": "😃", "smile": "😄", "grin": "😁",
    "laughing": "😆", "satisfied": "😆", "sweat_smile": "😅",
    "rofl": "🤣", "joy": "😂", "slightly_smiling_face": "🙂",
    "simple_smile": "🙂", "upside_down_face": "🙃", "wink": "😉",
    "blush": "😊", "innocent": "😇", "heart_eyes": "😍",
    "kissing_heart": "😘", "kissing": "😗", "kissing_smiling_eyes": "😙",
    "kissing_closed_eyes": "😚", "yum": "😋", "stuck_out_tongue": "😛",
    "stuck_out_tongue_winking_eye": "😜",
    "stuck_out_tongue_closed_eyes": "😝",
    "money_mouth_face": "🤑", "sunglasses": "😎", "nerd_face": "🤓",
    "monocle_face": "🧐", "thinking_face": "🤔", "zipper_mouth_face": "🤐",
    "raised_eyebrow": "🤨", "neutral_face": "😐", "expressionless": "😑",
    "no_mouth": "😶", "smirk": "😏", "unamused": "😒",
    "roll_eyes": "🙄", "grimacing": "😬", "lying_face": "🤥",
    "relieved": "😌", "pensive": "😔", "sleepy": "😪",
    "drooling_face": "🤤", "sleeping": "😴", "mask": "😷",
    "face_with_thermometer": "🤒", "face_with_head_bandage": "🤕",
    "nauseated_face": "🤢", "sneezing_face": "🤧", "hot_face": "🥵",
    "cold_face": "🥶", "woozy_face": "🥴", "dizzy_face": "😵",
    "exploding_head": "🤯", "cowboy_hat_face": "🤠", "partying_face": "🥳",
    "hushed": "😯", "open_mouth": "😮", "astonished": "😲",
    "flushed": "😳", "pleading_face": "🥺", "anguished": "😧",
    "fearful": "😨", "cold_sweat": "😰", "disappointed_relieved": "😥",
    "cry": "😢", "sob": "😭", "scream": "😱", "confounded": "😖",
    "persevere": "😣", "disappointed": "😞", "sweat": "😓",
    "weary": "😩", "tired_face": "😫", "yawning_face": "🥱",
    "triumph": "😤", "rage": "😡", "angry": "😠",
    "skull": "💀", "skull_and_crossbones": "☠️", "ghost": "👻",
    "alien": "👽", "space_invader": "👾", "robot_face": "🤖",
    "hankey": "💩", "poop": "💩", "shit": "💩",
    "smiling_imp": "😈", "imp": "👿", "japanese_ogre": "👹",
    "japanese_goblin": "👺", "clown_face": "🤡", "poop": "💩",
    "see_no_evil": "🙈", "hear_no_evil": "🙉", "speak_no_evil": "🙊",
    "baby": "👶", "boy": "👦", "girl": "👧", "man": "👨", "woman": "👩",
    "older_man": "👴", "older_woman": "👵",
    # ── Gestures & body ────────────────────────────────────────────────
    "wave": "👋", "raised_back_of_hand": "🤚", "hand": "✋",
    "raised_hand": "✋", "vulcan_salute": "🖖", "ok_hand": "👌",
    "pinched_fingers": "🤌", "pinching_hand": "🤏",
    "v": "✌️", "crossed_fingers": "🤞", "love_you_gesture": "🤟",
    "metal": "🤘", "call_me_hand": "🤙",
    "point_left": "👈", "point_right": "👉", "point_up": "☝️",
    "point_up_2": "👆", "middle_finger": "🖕", "point_down": "👇",
    "+1": "👍", "thumbsup": "👍", "-1": "👎", "thumbsdown": "👎",
    "fist": "✊", "facepunch": "👊", "punch": "👊",
    "left_facing_fist": "🤛", "right_facing_fist": "🤜",
    "raised_hands": "🙌", "open_hands": "👐", "clap": "👏",
    "pray": "🙏", "handshake": "🤝", "nail_care": "💅",
    "writing_hand": "✍️", "muscle": "💪", "mechanical_arm": "🦾",
    "leg": "🦵", "foot": "🦶", "ear": "👂", "nose": "👃",
    "eyes": "👀", "eye": "👁️", "tongue": "👅", "lips": "👄",
    "brain": "🧠", "tooth": "🦷", "bone": "🦴",
    # ── Hearts & romance ───────────────────────────────────────────────
    "heart": "❤️", "orange_heart": "🧡", "yellow_heart": "💛",
    "green_heart": "💚", "blue_heart": "💙", "purple_heart": "💜",
    "brown_heart": "🤎", "black_heart": "🖤", "white_heart": "🤍",
    "broken_heart": "💔", "heart_exclamation": "❣️", "two_hearts": "💕",
    "revolving_hearts": "💞", "heartbeat": "💓", "heartpulse": "💗",
    "sparkling_heart": "💖", "cupid": "💘", "gift_heart": "💝",
    "heart_decoration": "💟", "peace_symbol": "☮️",
    "kiss": "💋", "love_letter": "💌", "ring": "💍", "bouquet": "💐",
    # ── Nature & weather ───────────────────────────────────────────────
    "sunny": "☀️", "sun_with_face": "🌞", "sun_behind_cloud": "⛅",
    "cloud": "☁️", "cloud_with_rain": "🌧️", "thunder_cloud_and_rain": "⛈️",
    "partly_sunny": "⛅", "umbrella": "☂️", "umbrella_with_rain_drops": "☔",
    "snowflake": "❄️", "snowman": "⛄", "snowman_without_snow": "⛄",
    "wind_face": "🌬️", "fog": "🌫️", "rainbow": "🌈",
    "zap": "⚡", "cyclone": "🌀", "tornado": "🌪️",
    "fire": "🔥", "droplet": "💧", "ocean": "🌊", "wave": "🌊",
    "earth_africa": "🌍", "earth_americas": "🌎", "earth_asia": "🌏",
    "globe_with_meridians": "🌐", "world_map": "🗺️",
    "mount_fuji": "🗻", "national_park": "🏞️",
    "crescent_moon": "🌙", "new_moon": "🌑", "full_moon": "🌕",
    "stars": "🌟", "star": "⭐", "star2": "🌟", "dizzy": "💫",
    "sparkles": "✨", "comet": "☄️",
    "cherry_blossom": "🌸", "rose": "🌹", "wilted_flower": "🥀",
    "hibiscus": "🌺", "sunflower": "🌻", "blossom": "🌼",
    "tulip": "🌷", "seedling": "🌱", "evergreen_tree": "🌲",
    "deciduous_tree": "🌳", "palm_tree": "🌴", "cactus": "🌵",
    "ear_of_rice": "🌾", "herb": "🌿", "shamrock": "☘️",
    "four_leaf_clover": "🍀", "maple_leaf": "🍁", "fallen_leaf": "🍂",
    "leaves": "🍃", "mushroom": "🍄",
    # ── Animals ────────────────────────────────────────────────────────
    "dog": "🐶", "dog2": "🐕", "poodle": "🐩", "wolf": "🐺",
    "fox_face": "🦊", "raccoon": "🦝", "cat": "🐱", "cat2": "🐈",
    "lion_face": "🦁", "tiger": "🐯", "tiger2": "🐅",
    "leopard": "🐆", "horse": "🐴", "unicorn_face": "🦄",
    "zebra_face": "🦓", "deer": "🦌", "cow": "🐮", "cow2": "🐄",
    "ox": "🐂", "pig": "🐷", "pig2": "🐖", "boar": "🐗",
    "pig_nose": "🐽", "ram": "🐏", "sheep": "🐑", "goat": "🐐",
    "camel": "🐫", "llama": "🦙", "giraffe_face": "🦒",
    "elephant": "🐘", "rhinoceros": "🦏", "hippopotamus": "🦛",
    "mouse": "🐭", "mouse2": "🐁", "rat": "🐀", "hamster": "🐹",
    "rabbit": "🐰", "rabbit2": "🐇", "chipmunk": "🐿️",
    "hedgehog": "🦔", "bat": "🦇", "bear": "🐻",
    "panda_face": "🐼", "sloth": "🦥", "otter": "🦦",
    "skunk": "🦨", "kangaroo": "🦘", "badger": "🦡",
    "paw_prints": "🐾", "turkey": "🦃", "chicken": "🐔",
    "rooster": "🐓", "hatching_chick": "🐣", "baby_chick": "🐤",
    "hatched_chick": "🐥", "bird": "🐦", "penguin": "🐧",
    "dove_of_peace": "🕊️", "eagle": "🦅", "duck": "🦆",
    "swan": "🦢", "owl": "🦉", "flamingo": "🦩", "peacock": "🦚",
    "parrot": "🦜", "frog": "🐸", "crocodile": "🐊",
    "turtle": "🐢", "lizard": "🦎", "snake": "🐍",
    "dragon_face": "🐲", "dragon": "🐉", "sauropod": "🦕",
    "t-rex": "🦖", "whale": "🐳", "whale2": "🐋",
    "dolphin": "🐬", "flipper": "🐬", "fish": "🐟",
    "tropical_fish": "🐠", "blowfish": "🐡", "shark": "🦈",
    "octopus": "🐙", "shell": "🐚", "snail": "🐌", "butterfly": "🦋",
    "bug": "🐛", "ant": "🐜", "bee": "🐝", "honeybee": "🐝",
    "cricket": "🦗", "spider": "🕷️", "scorpion": "🦂",
    "mosquito": "🦟", "microbe": "🦠",
    # ── Food & drink ───────────────────────────────────────────────────
    "apple": "🍎", "green_apple": "🍏", "pear": "🍐",
    "tangerine": "🍊", "orange": "🍊", "lemon": "🍋",
    "banana": "🍌", "watermelon": "🍉", "grapes": "🍇",
    "strawberry": "🍓", "melon": "🍈", "cherries": "🍒",
    "peach": "🍑", "mango": "🥭", "pineapple": "🍍",
    "coconut": "🥥", "kiwi_fruit": "🥝", "tomato": "🍅",
    "eggplant": "🍆", "avocado": "🥑", "broccoli": "🥦",
    "leafy_green": "🥬", "cucumber": "🥒", "hot_pepper": "🌶️",
    "corn": "🌽", "carrot": "🥕", "garlic": "🧄", "onion": "🧅",
    "potato": "🥔", "sweet_potato": "🍠", "croissant": "🥐",
    "bagel": "🥯", "bread": "🍞", "baguette_bread": "🥖",
    "pretzel": "🥨", "cheese_wedge": "🧀", "egg": "🥚",
    "cooking": "🍳", "pancakes": "🥞", "waffle": "🧇",
    "bacon": "🥓", "cut_of_meat": "🥩", "poultry_leg": "🍗",
    "meat_on_bone": "🍖", "hotdog": "🌭", "hamburger": "🍔",
    "fries": "🍟", "pizza": "🍕", "sandwich": "🥪",
    "stuffed_flatbread": "🥙", "falafel": "🧆", "taco": "🌮",
    "burrito": "🌯", "salad": "🥗", "shallow_pan_of_food": "🥘",
    "spaghetti": "🍝", "ramen": "🍜", "stew": "🍲",
    "curry": "🍛", "sushi": "🍣", "bento": "🍱", "dumpling": "🥟",
    "fried_shrimp": "🍤", "rice_ball": "🍙", "rice": "🍚",
    "rice_cracker": "🍘", "fish_cake": "🍥", "fortune_cookie": "🥠",
    "moon_cake": "🥮", "oden": "🍢", "dango": "🍡",
    "shaved_ice": "🍧", "ice_cream": "🍨", "icecream": "🍦",
    "pie": "🥧", "cake": "🎂", "birthday": "🎂",
    "shortcake": "🍰", "cupcake": "🧁", "candy": "🍬",
    "lollipop": "🍭", "chocolate_bar": "🍫", "popcorn": "🍿",
    "doughnut": "🍩", "cookie": "🍪", "honey_pot": "🍯",
    "salt": "🧂", "soft_ice_cream": "🍦",
    "beer": "🍺", "beers": "🍻", "clinking_glasses": "🥂",
    "wine_glass": "🍷", "cocktail": "🍸", "tropical_drink": "🍹",
    "tumbler_glass": "🥃", "cup_with_straw": "🥤", "beverage_box": "🧃",
    "mate": "🧉", "bubble_tea": "🧋", "champagne": "🍾",
    "tea": "🍵", "coffee": "☕", "cup_with_straw": "🥤",
    "milk_glass": "🥛", "baby_bottle": "🍼",
    # ── Travel & places ────────────────────────────────────────────────
    "car": "🚗", "taxi": "🚕", "bus": "🚌", "trolleybus": "🚎",
    "racing_car": "🏎️", "police_car": "🚓", "ambulance": "🚑",
    "fire_engine": "🚒", "minibus": "🚐", "truck": "🚚",
    "articulated_lorry": "🚛", "tractor": "🚜", "kick_scooter": "🛴",
    "bike": "🚲", "motor_scooter": "🛵", "motorcycle": "🏍️",
    "monorail": "🚝", "mountain_railway": "🚞", "train": "🚋",
    "train2": "🚆", "bullettrain_side": "🚄", "bullettrain_front": "🚅",
    "steam_locomotive": "🚂", "railway_car": "🚃",
    "station": "🚉", "airplane": "✈️", "small_airplane": "🛩️",
    "rocket": "🚀", "flying_saucer": "🛸", "seat": "💺",
    "helicopter": "🚁", "suspension_railway": "🚟",
    "boat": "⛵", "sailboat": "⛵", "canoe": "🛶",
    "speedboat": "🚤", "ship": "🚢", "ferry": "⛴️",
    "anchor": "⚓", "construction": "🚧",
    "vertical_traffic_light": "🚦", "traffic_light": "🚥",
    "busstop": "🚏", "fuelpump": "⛽", "rotating_light": "🚨",
    "house": "🏠", "house_with_garden": "🏡", "office": "🏢",
    "post_office": "🏣", "european_post_office": "🏤",
    "hospital": "🏥", "bank": "🏦", "hotel": "🏨",
    "convenience_store": "🏪", "school": "🏫", "love_hotel": "🏩",
    "wedding": "💒", "european_castle": "🏰", "japanese_castle": "🏯",
    "stadium": "🏟️", "statue_of_liberty": "🗽",
    "moyai": "🗿", "tokyo_tower": "🗼",
    # ── Activities & sports ────────────────────────────────────────────
    "soccer": "⚽", "basketball": "🏀", "football": "🏈",
    "baseball": "⚾", "softball": "🥎", "tennis": "🎾",
    "volleyball": "🏐", "rugby_football": "🏉", "flying_disc": "🥏",
    "8ball": "🎱", "ping_pong": "🏓", "badminton_racquet_and_shuttlecock": "🏸",
    "goal_net": "🥅", "ice_hockey_stick_and_puck": "🏒",
    "field_hockey_stick_and_ball": "🏑", "lacrosse": "🥍",
    "cricket_game": "🏏", "golf": "⛳", "bow_and_arrow": "🏹",
    "fishing_pole_and_fish": "🎣", "boxing_glove": "🥊",
    "martial_arts_uniform": "🥋", "ice_skate": "⛸️",
    "ski": "🎿", "sled": "🛷", "curling_stone": "🥌",
    "dart": "🎯", "skateboard": "🛹", "trophy": "🏆",
    "medal": "🥇", "2nd_place_medal": "🥈", "3rd_place_medal": "🥉",
    "sports_medal": "🏅", "ribbon": "🎀", "rosette": "🏵️",
    "ticket": "🎫", "tickets": "🎟️",
    "circus_tent": "🎪", "performing_arts": "🎭",
    "art": "🎨", "slot_machine": "🎰", "game_die": "🎲",
    "jigsaw": "🧩", "teddy_bear": "🧸", "spades": "♠️",
    "hearts": "♥️", "diamonds": "♦️", "clubs": "♣️",
    "chess_pawn": "♟️", "joker": "🃏", "mahjong": "🀄",
    "flower_playing_cards": "🎴",
    "video_game": "🎮", "joystick": "🕹️",
    "runner": "🏃", "walking": "🚶", "dancer": "💃",
    "man_dancing": "🕺", "swimming_woman": "🏊",
    "bicyclist": "🚴", "mountain_bicyclist": "🚵",
    "horse_racing": "🏇", "snowboarder": "🏂",
    "weight_lifter": "🏋️", "golfing": "🏌️", "surfer": "🏄",
    "rowing_woman": "🚣", "climbing": "🧗", "person_fencing": "🤺",
    "wrestlers": "🤼", "handball": "🤾", "juggling": "🤹",
    "yoga": "🧘", "bath": "🛁", "sleeping_accommodation": "🛌",
    # ── Objects ────────────────────────────────────────────────────────
    "tada": "🎉", "confetti_ball": "🎊", "balloon": "🎈",
    "christmas_tree": "🎄", "sparkler": "🎇", "fireworks": "🎆",
    "jack_o_lantern": "🎃", "gift": "🎁", "reminder_ribbon": "🎗️",
    "boom": "💥", "anger": "💢", "100": "💯",
    "moneybag": "💰", "yen": "💴", "dollar": "💵",
    "euro": "💶", "pound": "💷", "gem": "💎",
    "credit_card": "💳", "chart": "💹",
    "bulb": "💡", "flashlight": "🔦", "candle": "🕯️",
    "mag": "🔍", "mag_right": "🔎",
    "lock": "🔒", "unlock": "🔓", "key": "🔑", "old_key": "🗝️",
    "hammer": "🔨", "axe": "🪓", "pick": "⛏️", "hammer_and_pick": "⚒️",
    "hammer_and_wrench": "🛠️", "dagger_knife": "🗡️",
    "sword": "⚔️", "gun": "🔫", "shield": "🛡️",
    "wrench": "🔧", "screwdriver": "🪛", "nut_and_bolt": "🔩",
    "gear": "⚙️", "chains": "⛓️", "link": "🔗",
    "scissors": "✂️", "broom": "🧹", "basket": "🧺",
    "roll_of_paper": "🧻", "sponge": "🧽", "bucket": "🪣",
    "package": "📦", "mailbox": "📬", "mailbox_with_mail": "📬",
    "mailbox_closed": "📪", "inbox_tray": "📥", "outbox_tray": "📤",
    "wastebasket": "🗑️", "card_box": "🗃️", "file_cabinet": "🗄️",
    "clipboard": "📋", "notepad_spiral": "🗒️", "calendar_spiral": "🗓️",
    "card_index": "📇", "chart_with_upwards_trend": "📈",
    "chart_with_downwards_trend": "📉", "bar_chart": "📊",
    "file_folder": "📁", "open_file_folder": "📂",
    "bookmark_tabs": "📑", "memo": "📝", "pencil": "✏️",
    "pencil2": "✏️", "pen": "🖊️", "fountain_pen": "🖋️",
    "black_nib": "✒️", "crayon": "🖍️", "straight_ruler": "📏",
    "triangular_ruler": "📐", "bookmark": "🔖", "label": "🏷️",
    "books": "📚", "book": "📖", "ledger": "📒",
    "notebook": "📓", "notebook_with_decorative_cover": "📔",
    "closed_book": "📕", "green_book": "📗", "blue_book": "📘",
    "orange_book": "📙", "newspaper": "📰", "newspaper_roll": "🗞️",
    "email": "📧", "envelope": "✉️", "envelope_with_arrow": "📩",
    "incoming_envelope": "📨", "e-mail": "📧",
    "inbox_tray": "📥", "outbox_tray": "📤",
    "package": "📦", "mailbox": "📬",
    "postbox": "📮", "ballot_box_with_ballot": "🗳️",
    "pencil": "✏️", "paperclip": "📎", "linked_paperclips": "🖇️",
    "pushpin": "📌", "round_pushpin": "📍",
    "calendar": "📅", "date": "📅", "calendar_spiral": "🗓️",
    "wastebasket": "🗑️",
    "telephone": "☎️", "telephone_receiver": "📞", "phone": "📱",
    "iphone": "📱", "calling": "📲", "pager": "📟",
    "fax": "📠", "battery": "🔋", "electric_plug": "🔌",
    "computer": "💻", "desktop_computer": "🖥️",
    "printer": "🖨️", "keyboard": "⌨️", "computer_mouse": "🖱️",
    "trackball": "🖲️", "minidisc": "💽", "floppy_disk": "💾",
    "cd": "💿", "dvd": "📀", "abacus": "🧮",
    "movie_camera": "🎥", "film_frames": "🎞️", "film_projector": "📽️",
    "clapper": "🎬", "tv": "📺", "radio": "📻",
    "vhs": "📼", "camera": "📷", "camera_with_flash": "📸",
    "video_camera": "📹", "telephone_receiver": "📞",
    "loud_sound": "🔊", "sound": "🔉", "speaker": "🔈",
    "mute": "🔇", "bell": "🔔", "no_bell": "🔕",
    "mega": "📣", "loudspeaker": "📢",
    "hourglass": "⌛", "hourglass_flowing_sand": "⏳",
    "clock1": "🕐", "clock2": "🕑", "clock3": "🕒",
    "alarm_clock": "⏰", "stopwatch": "⏱️", "timer_clock": "⏲️",
    "watch": "⌚", "calendar": "📅",
    "money_with_wings": "💸", "moneybag": "💰",
    "hammer": "🔨", "wrench": "🔧",
    "mag": "🔍", "telescope": "🔭", "microscope": "🔬",
    "syringe": "💉", "pill": "💊", "adhesive_bandage": "🩹",
    "stethoscope": "🩺", "drop_of_blood": "🩸",
    "door": "🚪", "bed": "🛏️", "couch_and_lamp": "🛋️",
    "toilet": "🚽", "shower": "🚿", "bathtub": "🛁",
    "shopping_cart": "🛒", "shopping_bags": "🛍️",
    "briefcase": "💼", "backpack": "🎒", "luggage": "🧳",
    "handbag": "👜", "purse": "👛", "pouch": "👝",
    "mans_shoe": "👞", "athletic_shoe": "👟", "hiking_boot": "🥾",
    "high_heel": "👠", "sandal": "👡", "flat_shoe": "🥿",
    "boot": "👢", "crown": "👑", "hat": "🎩", "tophat": "🎩",
    "womans_hat": "👒", "billed_cap": "🧢",
    "shirt": "👕", "tshirt": "👕", "necktie": "👔",
    "jeans": "👖", "coat": "🧥", "scarf": "🧣",
    "gloves": "🧤", "socks": "🧦", "dress": "👗",
    "kimono": "👘", "sari": "🥻", "one_piece_swimsuit": "🩱",
    "swim_brief": "🩲", "shorts": "🩳", "bikini": "👙",
    "womans_clothes": "👚", "thread": "🧵", "yarn": "🧶",
    # ── Symbols ────────────────────────────────────────────────────────
    "white_check_mark": "✅", "ballot_box_with_check": "☑️",
    "heavy_check_mark": "✔️", "x": "❌", "negative_squared_cross_mark": "❎",
    "heavy_plus_sign": "➕", "heavy_minus_sign": "➖",
    "heavy_division_sign": "➗", "heavy_multiplication_x": "✖️",
    "question": "❓", "grey_question": "❔",
    "exclamation": "❗", "heavy_exclamation_mark": "❗",
    "grey_exclamation": "❕", "warning": "⚠️",
    "no_entry": "⛔", "no_entry_sign": "🚫",
    "prohibited": "🚫", "sos": "🆘", "recycle": "♻️",
    "fleur_de_lis": "⚜️", "beginner": "🔰",
    "trident": "🔱", "information_source": "ℹ️",
    "ok": "🆗", "up": "🆙", "cool": "🆒", "free": "🆓",
    "new": "🆕", "ng": "🆖", "sos": "🆘", "up": "🆙",
    "vs": "🆚", "end": "🔚", "back": "🔙", "on": "🔛",
    "top": "🔝", "soon": "🔜",
    "zero": "0️⃣", "one": "1️⃣", "two": "2️⃣", "three": "3️⃣",
    "four": "4️⃣", "five": "5️⃣", "six": "6️⃣", "seven": "7️⃣",
    "eight": "8️⃣", "nine": "9️⃣", "keycap_ten": "🔟",
    "100": "💯", "1234": "🔢",
    "arrow_forward": "▶️", "pause_button": "⏸️", "stop_button": "⏹️",
    "record_button": "⏺️", "next_track_button": "⏭️",
    "previous_track_button": "⏮️", "fast_forward": "⏩",
    "rewind": "⏪", "twisted_rightwards_arrows": "🔀",
    "repeat": "🔁", "repeat_one": "🔂",
    "arrow_backward": "◀️", "arrow_up_small": "🔼",
    "arrow_down_small": "🔽", "arrow_double_up": "⏫",
    "arrow_double_down": "⏬", "arrow_right": "➡️",
    "arrow_left": "⬅️", "arrow_up": "⬆️", "arrow_down": "⬇️",
    "arrow_upper_right": "↗️", "arrow_lower_right": "↘️",
    "arrow_lower_left": "↙️", "arrow_upper_left": "↖️",
    "arrow_up_down": "↕️", "left_right_arrow": "↔️",
    "arrows_counterclockwise": "🔄", "arrow_right_hook": "↪️",
    "arrow_heading_up": "⤴️", "arrow_heading_down": "⤵️",
    "radio_button": "🔘", "large_blue_circle": "🔵",
    "large_orange_circle": "🟠", "large_yellow_circle": "🟡",
    "large_green_circle": "🟢", "large_red_circle": "🔴",
    "large_purple_circle": "🟣", "large_brown_circle": "🟤",
    "black_circle": "⚫", "white_circle": "⚪",
    "red_square": "🟥", "orange_square": "🟧",
    "yellow_square": "🟨", "green_square": "🟩",
    "blue_square": "🟦", "purple_square": "🟪",
    "brown_square": "🟫", "black_large_square": "⬛",
    "white_large_square": "⬜",
    "small_red_triangle": "🔺", "small_red_triangle_down": "🔻",
    "large_blue_diamond": "🔷", "large_orange_diamond": "🔶",
    "small_blue_diamond": "🔹", "small_orange_diamond": "🔸",
    "speech_balloon": "💬", "thought_balloon": "💭",
    "zzz": "💤", "anger": "💢", "boom": "💥",
    "wave_emoji": "〰️", "wavy_dash": "〰️",
    "copyright": "©️", "registered": "®️", "tm": "™️",
    "hash": "#️⃣", "asterisk": "*️⃣",
    # ── Flags ──────────────────────────────────────────────────────────
    "checkered_flag": "🏁", "triangular_flag_on_post": "🚩",
    "crossed_flags": "🎌", "white_flag": "🏳️", "black_flag": "🏴",
    "rainbow_flag": "🏳️‍🌈",
    "us": "🇺🇸", "gb": "🇬🇧", "jp": "🇯🇵", "ca": "🇨🇦",
    "de": "🇩🇪", "fr": "🇫🇷", "au": "🇦🇺", "br": "🇧🇷",
    "cn": "🇨🇳", "kr": "🇰🇷", "in": "🇮🇳", "mx": "🇲🇽",
    "es": "🇪🇸", "it": "🇮🇹", "ru": "🇷🇺",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_size(size_bytes: int) -> str:
    """Return a human-readable file size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} GB"


def _extract_blocks_text(blocks: list) -> str:
    """Best-effort text extraction from Slack block-kit blocks."""
    parts = []
    for block in blocks:
        btype = block.get("type")
        if btype == "section":
            t = block.get("text", {})
            if t.get("text"):
                parts.append(t["text"])
        elif btype == "rich_text":
            for section in block.get("elements", []):
                for item in section.get("elements", []):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif item.get("type") == "link":
                        parts.append(item.get("url", ""))
        elif btype in ("header", "context"):
            for el in block.get("elements", []):
                if el.get("text"):
                    parts.append(el["text"])
    return "\n".join(parts)


def _placeholder_avatar(display_name: str) -> str:
    """Return a data-URI SVG avatar with the user's initial."""
    initial = (display_name or "?")[0].upper()
    # URL-encode the characters that matter inside a data URI
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36">'
        f'<rect width="36" height="36" rx="4" fill="%23e8e8e8"/>'
        f'<text x="18" y="25" text-anchor="middle" '
        f'font-size="18" font-family="sans-serif" fill="%23888">{initial}</text>'
        f'</svg>'
    )
    return f"data:image/svg+xml,{svg}"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class SlackHTMLRenderer:
    """Renders a Slack export directory to browsable HTML pages."""

    def __init__(
        self,
        export_dir: Path,
        channel_filter: set = None,
    ):
        self.export_dir = Path(export_dir)
        self.channel_filter = channel_filter
        self.html_dir = self.export_dir / "_html"

        self.users: dict = {}    # uid → user object
        self.channels: list = []
        self.emoji: dict = {}    # name → url or "alias:name"

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_users(self):
        path = self.export_dir / "users.json"
        with open(path, encoding="utf-8") as f:
            self.users = {u["id"]: u for u in json.load(f)}

    def load_channels(self):
        path = self.export_dir / "channels.json"
        with open(path, encoding="utf-8") as f:
            self.channels = json.load(f)

    def load_emoji(self):
        path = self.export_dir / "emoji.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                self.emoji = json.load(f)

    def load_channel_messages(self, channel_name: str, is_private: bool = False) -> list:
        """Read all daily JSON files for a channel, sorted by ts."""
        ch_dir = (
            self.export_dir / "_private_channels" / channel_name
            if is_private
            else self.export_dir / channel_name
        )
        messages = []
        for json_file in sorted(ch_dir.glob("????-??-??.json")):
            with open(json_file, encoding="utf-8") as f:
                messages.extend(json.load(f))
        messages.sort(key=lambda m: float(m.get("ts", 0)))
        return messages

    # ------------------------------------------------------------------
    # Avatars
    # ------------------------------------------------------------------

    def _avatar_src(self, user_id: str) -> str:
        """Return the src attribute value for an avatar <img>."""
        avatars_dir = self.export_dir / "_avatars"
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            if (avatars_dir / f"{user_id}{ext}").exists():
                return f"../_avatars/{user_id}{ext}"
        return _placeholder_avatar(self._display_name(user_id))

    def _display_name(self, user_id: str) -> str:
        user = self.users.get(user_id, {})
        profile = user.get("profile", {})
        return (
            profile.get("display_name")
            or profile.get("real_name")
            or user.get("name")
            or user_id
            or "Unknown"
        )

    # ------------------------------------------------------------------
    # mrkdwn rendering
    # ------------------------------------------------------------------

    def resolve_emoji_alias(self, name: str, depth: int = 0) -> str:
        if depth > 5:
            return name
        val = self.emoji.get(name, "")
        if val.startswith("alias:"):
            return self.resolve_emoji_alias(val[len("alias:"):], depth + 1)
        return name

    def render_emoji(self, name: str) -> str:
        canonical = self.resolve_emoji_alias(name)
        safe_name = html.escape(name)

        # 1. Custom emoji downloaded to __emoji/ (preferred — works offline)
        emoji_dir = self.export_dir / "__emoji"
        if emoji_dir.exists():
            for ext in (".png", ".gif", ".jpg", ".jpeg", ".webp"):
                if (emoji_dir / f"{canonical}{ext}").exists():
                    src = f"../__emoji/{canonical}{ext}"
                    return (
                        f'<img class="emoji" src="{src}" '
                        f'alt=":{safe_name}:" title=":{safe_name}:">'
                    )

        # 2. Unicode lookup for standard emoji
        char = UNICODE_EMOJI.get(canonical) or UNICODE_EMOJI.get(name)
        if char:
            return f'<span class="emoji-char" title=":{safe_name}:">{char}</span>'

        # 4. Fallback: plain text
        return f'<span class="emoji-text">:{safe_name}:</span>'

    def render_mrkdwn(self, text: str) -> str:
        """Convert Slack mrkdwn to safe HTML."""
        if not text:
            return ""

        # Step 1: Extract Slack angle-bracket tokens to numbered placeholders
        # so they survive HTML-escaping intact.
        tokens: list = []

        def _extract(m):
            tokens.append(m.group(0))
            return f"\x00{len(tokens) - 1}\x00"

        text = re.sub(r"<[^>]+>", _extract, text)

        # Step 2: Decode Slack's pre-escaped entities, then re-escape for HTML.
        # (Slack sends &amp; &lt; &gt; for literal & < > in message bodies.)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = html.escape(text, quote=False)

        # Step 3: Code blocks (must precede inline code and inline formatting)
        def _codeblock(m):
            code = m.group(1).strip("\n")
            return f"<pre><code>{code}</code></pre>"

        text = re.sub(r"```(.*?)```", _codeblock, text, flags=re.DOTALL)

        # Step 4: Inline code
        text = re.sub(r"`([^`\n]+)`", lambda m: f"<code>{m.group(1)}</code>", text)

        # Step 5: Restore Slack tokens → HTML
        def _restore(m):
            inner = tokens[int(m.group(1))][1:-1]  # strip < >

            if inner.startswith("@"):
                parts = inner[1:].split("|", 1)
                uid = parts[0]
                name = parts[1] if len(parts) > 1 else self._display_name(uid)
                return f'<span class="mention">@{html.escape(name)}</span>'

            if inner.startswith("#"):
                parts = inner[1:].split("|", 1)
                name = parts[1] if len(parts) > 1 else parts[0]
                return f'<span class="ch-mention">#{html.escape(name)}</span>'

            if inner.startswith("!"):
                if "|" in inner:
                    label = inner.split("|", 1)[1]
                elif "^" in inner:
                    label = inner.split("^", 1)[0][1:]
                else:
                    label = inner[1:]
                return f'<span class="mention">@{html.escape(label)}</span>'

            if inner.startswith(("http", "mailto:")):
                parts = inner.split("|", 1)
                url = html.escape(parts[0], quote=True)
                label = html.escape(parts[1]) if len(parts) > 1 else html.escape(parts[0])
                return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'

            return html.escape(inner)

        text = re.sub(r"\x00(\d+)\x00", _restore, text)

        # Step 6: Bold, italic, strikethrough
        text = re.sub(r"\*([^*\n]+)\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\b_([^_\n]+)_\b", r"<em>\1</em>", text)
        text = re.sub(r"~([^~\n]+)~", r"<del>\1</del>", text)

        # Step 7: Emoji  :name:
        text = re.sub(
            r":([a-zA-Z0-9_\-+]+):",
            lambda m: self.render_emoji(m.group(1)),
            text,
        )

        # Step 8: Newlines → <br>
        text = text.replace("\n", "<br>\n")

        return text

    # ------------------------------------------------------------------
    # Timestamp formatting
    # ------------------------------------------------------------------

    def _format_ts(self, ts: str) -> tuple:
        """Return (display_str, iso_str). Display is in local time."""
        try:
            dt_local = datetime.fromtimestamp(float(ts))
            dt_utc = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (ValueError, OSError):
            return "?", "?"
        try:
            display = dt_local.strftime("%-I:%M %p")
        except ValueError:  # Windows
            display = dt_local.strftime("%I:%M %p").lstrip("0") or "12:00 AM"
        return display, dt_utc.isoformat()

    def _day_label(self, date_str: str) -> str:
        """Convert 'YYYY-MM-DD' to 'Monday, January 6, 2025'."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            try:
                return dt.strftime("%A, %B %-d, %Y")
            except ValueError:  # Windows
                return dt.strftime("%A, %B %d, %Y").replace(" 0", " ")
        except ValueError:
            return date_str

    # ------------------------------------------------------------------
    # Thread map
    # ------------------------------------------------------------------

    def _build_thread_map(self, messages: list) -> tuple:
        """Return (top_level_messages, {parent_ts: [reply, ...]})."""
        top_level = []
        replies_by_ts: dict = defaultdict(list)
        for msg in messages:
            thread_ts = msg.get("thread_ts")
            ts = msg.get("ts")
            if thread_ts and thread_ts != ts:
                replies_by_ts[thread_ts].append(msg)
            else:
                top_level.append(msg)
        return top_level, dict(replies_by_ts)

    # ------------------------------------------------------------------
    # Message rendering
    # ------------------------------------------------------------------

    def _render_reactions(self, reactions: list) -> str:
        if not reactions:
            return ""
        parts = []
        for r in reactions:
            name = r.get("name", "")
            count = r.get("count", 0)
            user_ids = r.get("users", [])
            names = [self._display_name(uid) for uid in user_ids]
            popover_html = ""
            if names:
                names_html = html.escape(", ".join(names))
                popover_html = (
                    f'<div class="reaction-popover">'
                    f'<span class="reaction-popover-emoji">{self.render_emoji(name)}</span>'
                    f' {names_html}'
                    f'</div>'
                )
            parts.append(
                f'<span class="reaction" onclick="toggleReactionPopover(this)">'
                f'{self.render_emoji(name)}'
                f'<span class="reaction-count">{count}</span>'
                f'{popover_html}'
                f'</span>'
            )
        return f'<div class="reactions">{"".join(parts)}</div>'

    def _render_files(self, files: list, channel_name: str, is_private: bool = False) -> str:
        if not files:
            return ""
        IMAGE_TYPES = {
            "image/jpeg", "image/png", "image/gif",
            "image/webp", "image/svg+xml",
        }
        VIDEO_TYPES = {"video/mp4", "video/webm", "video/ogg"}
        parts = []
        for f in files:
            if f.get("mode") == "tombstone":
                continue
            name = html.escape(f.get("name") or f.get("id", "file"))
            mimetype = f.get("mimetype", "")
            local_path = f.get("local_path")

            if local_path:
                # Path from _html/<channel>.html → ../<channel-dir>/_files/<file>
                ch_dir = (
                    f"_private_channels/{html.escape(channel_name)}"
                    if is_private
                    else html.escape(channel_name)
                )
                src = f"../{ch_dir}/{html.escape(local_path)}"
                href = src
            else:
                url = f.get("url_private") or ""
                src = href = html.escape(url, quote=True)

            if not href:
                continue

            if mimetype in IMAGE_TYPES:
                parts.append(
                    f'<div class="file-attachment">'
                    f'<a href="{href}" target="_blank" rel="noopener">'
                    f'<img src="{src}" alt="{name}" loading="lazy">'
                    f'</a></div>'
                )
            elif mimetype in VIDEO_TYPES and local_path:
                parts.append(
                    f'<div class="file-attachment">'
                    f'<video controls preload="none">'
                    f'<source src="{src}" type="{html.escape(mimetype)}">'
                    f'Your browser does not support video.'
                    f'</video></div>'
                )
            else:
                size = f.get("size", 0)
                size_str = f" ({_fmt_size(size)})" if size else ""
                parts.append(
                    f'<div class="file-attachment file-download">'
                    f'<a href="{href}" target="_blank" rel="noopener">'
                    f'📎 {name}{html.escape(size_str)}'
                    f'</a></div>'
                )
        return "\n".join(parts)

    def _render_attachments(self, attachments: list) -> str:
        """Render legacy Slack message attachments (title + text + color bar)."""
        if not attachments:
            return ""
        parts = []
        for att in attachments:
            title = att.get("title") or ""
            text = att.get("text") or att.get("fallback") or ""
            color = att.get("color") or "cccccc"
            if not color.startswith("#"):
                color = f"#{color}"
            inner = []
            if title:
                link = att.get("title_link", "")
                t = html.escape(title)
                inner.append(
                    f'<div class="att-title">'
                    + (f'<a href="{html.escape(link, quote=True)}" target="_blank"'
                       f' rel="noopener">{t}</a>' if link else t)
                    + '</div>'
                )
            if text:
                inner.append(
                    f'<div class="att-text">{self.render_mrkdwn(text)}</div>'
                )
            if inner:
                parts.append(
                    f'<div class="attachment" style="border-left-color:{html.escape(color)}">'
                    + "".join(inner)
                    + "</div>"
                )
        return "\n".join(parts)

    def render_message(self, msg: dict, channel_name: str, is_reply: bool = False, is_private: bool = False) -> str:
        subtype = msg.get("subtype", "")
        ts = msg.get("ts", "")
        display_ts, iso_ts = self._format_ts(ts)

        # System messages
        SYSTEM_SUBTYPES = {
            "channel_join", "channel_leave", "channel_archive",
            "channel_unarchive", "channel_name", "channel_purpose", "channel_topic",
        }
        if subtype in SYSTEM_SUBTYPES:
            text = self.render_mrkdwn(msg.get("text", ""))
            return f'<div class="system-message">{text}</div>\n'

        # Author
        if subtype == "bot_message":
            display_name = html.escape(msg.get("username") or "Bot")
            avatar_src = _placeholder_avatar("B")
            extra_class = " bot-message"
        else:
            user_id = msg.get("user") or msg.get("bot_id") or ""
            display_name = html.escape(self._display_name(user_id))
            avatar_src = self._avatar_src(user_id)
            extra_class = ""

        # Text (fall back to blocks extraction)
        text = msg.get("text") or ""
        if not text and msg.get("blocks"):
            text = _extract_blocks_text(msg["blocks"])
        rendered_text = self.render_mrkdwn(text)

        files_html = self._render_files(msg.get("files", []), channel_name, is_private)
        reactions_html = self._render_reactions(msg.get("reactions", []))
        attachments_html = self._render_attachments(msg.get("attachments", []))

        reply_class = " reply" if is_reply else ""
        ts_id = ts.replace(".", "-")

        return (
            f'<div class="message{extra_class}{reply_class}"'
            f' id="msg-{ts_id}" data-ts="{html.escape(ts)}">\n'
            f'  <img class="avatar" src="{html.escape(avatar_src)}"'
            f' alt="{display_name}" width="36" height="36">\n'
            f'  <div class="message-body">\n'
            f'    <div class="message-header">\n'
            f'      <span class="username">{display_name}</span>\n'
            f'      <span class="timestamp" title="{html.escape(iso_ts)}">'
            f'{html.escape(display_ts)}</span>\n'
            f'    </div>\n'
            f'    <div class="message-text">{rendered_text}</div>\n'
            f'{attachments_html}\n'
            f'{files_html}\n'
            f'{reactions_html}\n'
            f'  </div>\n'
            f'</div>\n'
        )

    def _render_thread(self, parent: dict, replies: list, channel_name: str, is_private: bool = False) -> str:
        if not replies:
            return ""
        count = len(replies)
        word = "reply" if count == 1 else "replies"
        thread_id = f"thread-{parent['ts'].replace('.', '-')}"
        replies_html = "".join(
            self.render_message(r, channel_name, is_reply=True, is_private=is_private) for r in replies
        )
        return (
            f'<button class="thread-toggle"'
            f' onclick="toggleThread(\'{thread_id}\')"'
            f' aria-expanded="false">&#9658; {count} {word}</button>\n'
            f'<div id="{thread_id}" class="replies">\n'
            f'{replies_html}'
            f'</div>\n'
        )

    # ------------------------------------------------------------------
    # Page assembly
    # ------------------------------------------------------------------

    def render_index(self) -> str:
        rows = []
        for ch in sorted(self.channels, key=lambda c: c.get("name", "")):
            name = ch.get("name", "unknown")
            if self.channel_filter and name not in self.channel_filter:
                continue
            archived = ch.get("is_archived", False)
            topic = ch.get("topic", {}).get("value", "") or ""
            archived_badge = (
                ' <span class="archived-badge">archived</span>' if archived else ""
            )
            topic_span = (
                f'<span class="ch-topic">{html.escape(topic)}</span>' if topic else ""
            )
            row_class = "channel-row archived" if archived else "channel-row"
            rows.append(
                f'<a href="{html.escape(name)}.html" class="{row_class}">'
                f'<span class="ch-name"># {html.escape(name)}{archived_badge}</span>'
                f'{topic_span}'
                f'</a>'
            )

        channels_html = "\n".join(rows) if rows else "<p>No channels to display.</p>"

        # Prefer the timestamp encoded in the export dir name (slack_export_YYYYMMDD_HHMMSS);
        # fall back to the directory's modification time.
        m = re.search(r"(\d{8})_(\d{6})", self.export_dir.name)
        if m:
            try:
                dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            except ValueError:
                dt = None
        else:
            dt = None
        if dt is None:
            dt = datetime.fromtimestamp(self.export_dir.stat().st_mtime)
        try:
            generated = dt.strftime("%B %-d, %Y")
        except ValueError:  # Windows
            generated = dt.strftime("%B %d, %Y").replace(" 0", " ")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Slack Export</title>
  <link rel="stylesheet" href="style.css">
  <script>
    // Apply saved theme before body renders to avoid flash
    (function() {{
      if (localStorage.getItem('slackTheme') === 'light')
        document.documentElement.classList.add('light');
    }})();
  </script>
</head>
<body>
<button id="theme-toggle" onclick="toggleTheme()" title="Toggle light/dark mode">🌓</button>
<div class="index-page">
  <header class="index-header">
    <h1>&#128172; Slack Export</h1>
    <p class="export-meta">Generated {html.escape(generated)}</p>
  </header>
  <div class="channel-list">
{channels_html}
  </div>
</div>
<script>
function toggleTheme() {{
  var isLight = document.documentElement.classList.toggle('light');
  localStorage.setItem('slackTheme', isLight ? 'light' : 'dark');
}}
</script>
</body>
</html>"""

    def render_channel_page(self, channel: dict, messages: list) -> str:
        name = channel.get("name", "unknown")
        topic = channel.get("topic", {}).get("value", "") or ""
        is_archived = channel.get("is_archived", False)
        is_private = channel.get("is_private", False)

        top_level, replies_by_ts = self._build_thread_map(messages)

        # Group top-level messages by UTC day
        by_day: dict = defaultdict(list)
        for msg in top_level:
            try:
                day_key = datetime.fromtimestamp(
                    float(msg.get("ts", 0)), tz=timezone.utc
                ).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                day_key = "unknown"
            by_day[day_key].append(msg)

        body_parts = []
        for day_key in sorted(by_day.keys()):
            label = self._day_label(day_key)
            body_parts.append(
                f'<div class="day-separator"><span>{html.escape(label)}</span></div>\n'
            )
            for msg in by_day[day_key]:
                body_parts.append(self.render_message(msg, name, is_private=is_private))
                ts = msg.get("ts", "")
                if ts in replies_by_ts:
                    body_parts.append(
                        self._render_thread(msg, replies_by_ts[ts], name, is_private)
                    )

        messages_html = "".join(body_parts) if body_parts else "<p>No messages.</p>"
        archived_notice = (
            '<div class="archived-notice">This channel is archived.</div>'
            if is_archived else ""
        )
        topic_html = (
            f'<p class="ch-topic-text">{html.escape(topic)}</p>' if topic else ""
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>#{html.escape(name)} \u2014 Slack Export</title>
  <link rel="stylesheet" href="style.css">
  <script>
    // Apply saved theme before body renders to avoid flash
    (function() {{
      if (localStorage.getItem('slackTheme') === 'light')
        document.documentElement.classList.add('light');
    }})();
  </script>
</head>
<body>
<button id="theme-toggle" onclick="toggleTheme()" title="Toggle light/dark mode">🌓</button>
<div class="channel-page">
  <header class="channel-header">
    <a href="index.html" class="back-link">&#8592; All Channels</a>
    <h1># {html.escape(name)}</h1>
{topic_html}
{archived_notice}
  </header>
  <main class="messages">
{messages_html}
  </main>
</div>
<script>
function toggleTheme() {{
  var isLight = document.documentElement.classList.toggle('light');
  localStorage.setItem('slackTheme', isLight ? 'light' : 'dark');
}}

function toggleThread(id) {{
  var el = document.getElementById(id);
  var btn = el.previousElementSibling;
  var open = el.classList.toggle('open');
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  btn.textContent = (open ? '\u25bc' : '\u25b6') + btn.textContent.slice(1);
}}

function toggleReactionPopover(el) {{
  var pop = el.querySelector('.reaction-popover');
  if (!pop) return;
  var isOpen = pop.classList.contains('open');
  document.querySelectorAll('.reaction-popover.open').forEach(function(p) {{
    p.classList.remove('open');
  }});
  if (!isOpen) pop.classList.add('open');
}}

document.addEventListener('click', function(e) {{
  if (!e.target.closest('.reaction')) {{
    document.querySelectorAll('.reaction-popover.open').forEach(function(p) {{
      p.classList.remove('open');
    }});
  }}
}});
</script>
</body>
</html>"""

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    CSS = """\
*, *::before, *::after { box-sizing: border-box; }

/* ── Colour tokens — dark mode is the default ───────────────────────── */
:root {
  --bg:               #1a1d21;
  --bg-hover:         #222529;
  --bg-surface:       #2c2f33;
  --bg-code:          #222529;
  --bg-reaction:      #27292d;
  --bg-attachment:    #1e2125;
  --border:           #3d3f43;
  --text:             #d1d2d3;
  --text-dim:         #999aab;
  --text-strong:      #e8e8e8;
  --link:             #1d9bd1;
  --mention-bg:       #163a5c;
  --mention-fg:       #6cb4f4;
  --rxn-hover-bg:     #163a5c;
  --rxn-hover-border: #1d9bd1;
  --rxn-count:        #6cb4f4;
  --header-bg:        #1a1d21;
  --popover-bg:       #e0e0e0;
  --popover-fg:       #1d1c1d;
  --thread-fg:        #1d9bd1;
  --thread-border:    #3d3f43;
  --thread-hover-bg:  #163a5c;
  --archived-fg:      #f0a050;
  --bot-badge-bg:     #3d3f43;
  --bot-badge-fg:     #999aab;
  --sep-color:        #999aab;
}

:root.light {
  --bg:               #ffffff;
  --bg-hover:         #f8f8f8;
  --bg-surface:       #f5f5f5;
  --bg-code:          #f5f5f5;
  --bg-reaction:      #f8f8f8;
  --bg-attachment:    #fafafa;
  --border:           #e8e8e8;
  --text:             #1d1c1d;
  --text-dim:         #616061;
  --text-strong:      #1d1c1d;
  --link:             #1264a3;
  --mention-bg:       #e8f0fa;
  --mention-fg:       #1264a3;
  --rxn-hover-bg:     #e8f0fa;
  --rxn-hover-border: #1264a3;
  --rxn-count:        #1264a3;
  --header-bg:        #ffffff;
  --popover-bg:       #1d1c1d;
  --popover-fg:       #ffffff;
  --thread-fg:        #1264a3;
  --thread-border:    #e0e0e0;
  --thread-hover-bg:  #e8f0fa;
  --archived-fg:      #e8912d;
  --bot-badge-bg:     #e8e8e8;
  --bot-badge-fg:     #616061;
  --sep-color:        #616061;
}

body {
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 15px;
  line-height: 1.5;
  color: var(--text);
  background: var(--bg);
  margin: 0;
  padding: 0;
}

a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Theme toggle button ─────────────────────────────────────────────── */
#theme-toggle {
  position: fixed;
  top: 12px;
  right: 16px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 4px 10px;
  font-size: 16px;
  line-height: 1.4;
  cursor: pointer;
  z-index: 1000;
  color: var(--text);
}
#theme-toggle:hover { border-color: var(--link); }

/* ── Index page ─────────────────────────────────────────────────────── */

.index-page { max-width: 720px; margin: 0 auto; padding: 40px 24px; }

.index-header h1 { font-size: 28px; font-weight: 700; margin: 0 0 4px; }

.export-meta { color: var(--text-dim); font-size: 13px; margin: 0 0 32px; }

.channel-list { display: flex; flex-direction: column; gap: 2px; }

.channel-row {
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 10px 12px;
  border-radius: 6px;
  color: var(--text);
}
.channel-row:hover { background: var(--bg-surface); text-decoration: none; }
.channel-row.archived { opacity: 0.6; }

.ch-name { font-weight: 600; font-size: 15px; min-width: 180px; }

.ch-topic {
  font-size: 13px;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.archived-badge {
  font-size: 11px;
  background: var(--bg-surface);
  color: var(--text-dim);
  border-radius: 3px;
  padding: 1px 5px;
  font-weight: 400;
  margin-left: 6px;
  vertical-align: middle;
}

/* ── Channel page ────────────────────────────────────────────────────── */

.channel-page { max-width: 900px; margin: 0 auto; padding: 0 24px 80px; }

.channel-header {
  position: sticky;
  top: 0;
  background: var(--header-bg);
  border-bottom: 1px solid var(--border);
  padding: 16px 0 12px;
  margin-bottom: 8px;
  z-index: 10;
}

.back-link { font-size: 13px; color: var(--text-dim); display: inline-block; margin-bottom: 4px; }
.back-link:hover { color: var(--link); }

.channel-header h1 { font-size: 20px; font-weight: 700; margin: 0 0 2px; }

.ch-topic-text { font-size: 13px; color: var(--text-dim); margin: 0; }

.archived-notice { font-size: 13px; color: var(--archived-fg); margin-top: 4px; }

/* ── Day separator ───────────────────────────────────────────────────── */

.day-separator {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 24px 0 8px;
  color: var(--sep-color);
  font-size: 13px;
  font-weight: 700;
}
.day-separator::before,
.day-separator::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--border);
}

/* ── Messages ────────────────────────────────────────────────────────── */

.messages { padding-top: 4px; }

.message {
  display: flex;
  gap: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  margin: 1px 0;
}
.message:hover { background: var(--bg-hover); }

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 2px;
  object-fit: cover;
}

.message-body { flex: 1; min-width: 0; }

.message-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}

.username { font-weight: 700; font-size: 15px; color: var(--text-strong); }

.bot-message .username::after {
  content: "APP";
  font-size: 10px;
  font-weight: 400;
  background: var(--bot-badge-bg);
  color: var(--bot-badge-fg);
  border-radius: 3px;
  padding: 1px 4px;
  margin-left: 5px;
  vertical-align: middle;
}

.timestamp { font-size: 12px; color: var(--text-dim); cursor: default; }

.message-text { word-break: break-word; overflow-wrap: break-word; }

.system-message {
  color: var(--text-dim);
  font-size: 13px;
  font-style: italic;
  padding: 3px 8px 3px 56px;
}

/* ── Inline formatting ───────────────────────────────────────────────── */

code {
  background: var(--bg-code);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 13px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

pre {
  background: var(--bg-code);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 16px;
  overflow-x: auto;
  margin: 6px 0;
}
pre code { background: none; border: none; padding: 0; font-size: 13px; }

.mention {
  background: var(--mention-bg);
  color: var(--mention-fg);
  border-radius: 3px;
  padding: 0 3px;
  font-weight: 500;
}
.ch-mention { color: var(--mention-fg); font-weight: 500; }

/* ── Emoji ───────────────────────────────────────────────────────────── */

img.emoji { width: 20px; height: 20px; vertical-align: -4px; display: inline; }
.emoji-char { font-size: 18px; line-height: 1; }
.emoji-text { font-size: 13px; color: var(--text-dim); }

/* ── Reactions ───────────────────────────────────────────────────────── */

.reactions { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }

.reaction {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--bg-reaction);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 2px 8px;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
  position: relative;
}
.reaction:hover { background: var(--rxn-hover-bg); border-color: var(--rxn-hover-border); }
.reaction-count { color: var(--rxn-count); font-weight: 600; }

.reaction-popover {
  display: none;
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--popover-bg);
  color: var(--popover-fg);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  white-space: nowrap;
  z-index: 200;
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}
.reaction-popover::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--popover-bg);
}
.reaction-popover.open { display: block; }
.reaction-popover-emoji { margin-right: 4px; }

/* ── Files ───────────────────────────────────────────────────────────── */

.file-attachment { margin-top: 6px; }

.file-attachment img {
  max-width: 360px;
  max-height: 280px;
  border-radius: 6px;
  border: 1px solid var(--border);
  display: block;
  cursor: pointer;
}

.file-attachment video {
  max-width: 480px;
  border-radius: 6px;
  display: block;
}

.file-download a {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
}
.file-download a:hover { background: var(--bg-hover); text-decoration: none; }

/* ── Legacy attachments ──────────────────────────────────────────────── */

.attachment {
  border-left: 3px solid var(--border);
  padding: 6px 12px;
  margin-top: 6px;
  background: var(--bg-attachment);
  border-radius: 0 4px 4px 0;
}
.att-title { font-weight: 600; margin-bottom: 2px; }
.att-text { font-size: 14px; color: var(--text-dim); }

/* ── Threads ─────────────────────────────────────────────────────────── */

.thread-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  background: none;
  border: 1px solid var(--thread-border);
  border-radius: 4px;
  padding: 3px 10px;
  font-size: 13px;
  color: var(--thread-fg);
  cursor: pointer;
  font-family: inherit;
}
.thread-toggle:hover { background: var(--thread-hover-bg); border-color: var(--rxn-hover-border); }

.replies {
  display: none;
  margin: 4px 0 4px 20px;
  padding-left: 16px;
  border-left: 2px solid var(--border);
}
.replies.open { display: block; }
"""

    def write_stylesheet(self):
        (self.html_dir / "style.css").write_text(self.CSS, encoding="utf-8")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def render(self) -> Path:
        self.html_dir.mkdir(parents=True, exist_ok=True)

        print("Loading export data…")
        self.load_users()
        self.load_channels()
        self.load_emoji()

        self.write_stylesheet()

        # Index page
        (self.html_dir / "index.html").write_text(
            self.render_index(), encoding="utf-8"
        )

        # Channel pages
        channels_to_render = [
            ch for ch in self.channels
            if self.channel_filter is None or ch.get("name") in self.channel_filter
        ]

        bar = tqdm(channels_to_render, desc="Rendering channels", unit=" ch")
        for ch in bar:
            name = ch.get("name", "unknown")
            is_private = ch.get("is_private", False)
            bar.set_postfix_str(f"#{name}")
            messages = self.load_channel_messages(name, is_private=is_private)
            html_content = self.render_channel_page(ch, messages)
            (self.html_dir / f"{name}.html").write_text(html_content, encoding="utf-8")

        index_path = self.html_dir / "index.html"
        print(f"\nDone.  Open in your browser: {index_path}")
        return index_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Render a Slack export directory to browsable HTML pages."
    )
    parser.add_argument(
        "export_dir",
        help="Path to the Slack export directory (must contain users.json)",
    )
    parser.add_argument(
        "--channel",
        nargs="+",
        metavar="NAME",
        help="Render only these channels (space-separated names)",
    )
    args = parser.parse_args()

    export_dir = Path(args.export_dir).resolve()
    if not export_dir.is_dir():
        print(f"Error: '{export_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    if not (export_dir / "users.json").exists():
        print(
            f"Error: '{export_dir}' doesn't look like a Slack export "
            f"(missing users.json).",
            file=sys.stderr,
        )
        sys.exit(1)

    renderer = SlackHTMLRenderer(
        export_dir=export_dir,
        channel_filter=set(args.channel) if args.channel else None,
    )
    renderer.render()


if __name__ == "__main__":
    main()
