"""
🎮 ULTIMATE DISCORD RPG BOT - v2.1 ENHANCED
- Auto responds to EVERY message
- Auto-creates characters for new players
- Token setup wizard
- Massive SQL with guilds, trading, achievements, quests, seasons
- Player Shop system for trading items
- New rare and exotic items added
- 100% functional, production-ready
"""

import asyncio
import difflib
import json
import os
import random
import re
import sqlite3
import struct
import time
import zlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from io import BytesIO

import discord
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont

# ============================================================================
# CONSTANTS
# ============================================================================

# Default values
DEFAULT_STARTING_GOLD = 1000
DEFAULT_STARTING_ZONE = "meadows"
DEFAULT_POTION_QUANTITY = 5
STARTING_WEAPON_POWER = 20

# Inventory limits
MAX_INVENTORY_DISPLAY = 10
MAX_SHOP_ITEMS_DISPLAY = 5

# Timing (in seconds)
DB_SAVE_INTERVAL = 5
MESSAGE_COOLDOWN = 0.5
AUTOSAVE_INTERVAL = 5

# Image dimensions
ITEM_CARD_WIDTH, ITEM_CARD_HEIGHT = 500, 350
SHOP_BANNER_WIDTH, SHOP_BANNER_HEIGHT = 500, 150
CATEGORY_CARD_WIDTH, CATEGORY_CARD_HEIGHT = 300, 120
CHAR_PREVIEW_WIDTH, CHAR_PREVIEW_HEIGHT = 600, 500

# ============================================================================
# LOGGING & UTILITIES
# ============================================================================

def log(level: str, msg: str) -> None:
    """Log message with timestamp and level."""
    ts_str = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts_str}] [{level:8}] {msg}")

def log_debug(msg: str) -> None:
    """Log debug message."""
    log("DEBUG", msg)

def log_info(msg: str) -> None:
    """Log info message."""
    log("INFO", msg)

def log_warn(msg: str) -> None:
    """Log warning message."""
    log("WARN", msg)

def log_error(msg: str) -> None:
    """Log error message."""
    log("ERROR", msg)

# ============================================================================
# 🎨 VISUALS + MULTI-STAT ITEM-ROLL + LUCK-SCALED RNG ENGINE
# ----------------------------------------------------------------------------
# Everything lives in the `V` namespace so it's easy to find and call.
#   ART    -> rarity colors, item cards, animated drop reveals, fancy bars
#   ITEMS  -> every drop rolls HP/ATK/DEF/CRIT + prefix/suffix affixes
#   RNG    -> one luck-scaled rarity roller (luck pushes odds toward higher tiers)
# ============================================================================


@dataclass(frozen=True)
class Rarity:
    key: str
    label: str
    color: int
    emoji: str
    glyph: str
    aura: str
    weight: float
    stat_mult: float
    affixes: Tuple[int, int]


@dataclass
class RolledItem:
    base_name: str
    display_name: str
    item_type: str
    rarity: str
    ilvl: int
    hp: int = 0
    atk: int = 0
    defense: int = 0
    crit: float = 0.0
    quality: float = 1.0
    affixes: List[str] = field(default_factory=list)
    element: str = ""
    sockets: int = 0
    gems: List[str] = field(default_factory=list)
    set_name: str = ""

    @property
    def power(self) -> int:
        base = self.hp * 0.25 + self.atk * 2.0 + self.defense * 1.6 + self.crit * 12.0
        base *= (1.0 + 0.08 * len(self.gems))          # socketed gems add power
        if self.element:
            base *= 1.06                                # elemental items hit harder
        return int(base)

    @property
    def value(self) -> int:
        mult = 1.0 + V.RARITY_RANK[self.rarity] * 0.6
        return max(1, int(self.power * 9 * mult * self.quality))

    @property
    def dust(self) -> int:
        """Arcane dust returned when salvaged."""
        return max(1, int((5 + self.ilvl) * (1 + V.RARITY_RANK[self.rarity] ** 2) * self.quality))


class V:
    """Self-contained visuals + RNG engine. All members are static."""

    # ---- rarity table: color / emoji / glyph / aura / odds / power -------
    RARITIES: Dict[str, Rarity] = {
        "common":    Rarity("common",    "Common",    0x9E9E9E, "⚪", "─",  "·",            1000.0, 1.00, (0, 1)),
        "uncommon":  Rarity("uncommon",  "Uncommon",  0x4CAF50, "🟢", "═",  "✦",            420.0,  1.18, (0, 2)),
        "rare":      Rarity("rare",      "Rare",      0x2196F3, "🔵", "━",  "✦ ✧",          150.0,  1.45, (1, 2)),
        "epic":      Rarity("epic",      "Epic",      0x9C27B0, "🟣", "▔",  "✦ ✧ ✦",        45.0,   1.85, (1, 3)),
        "legendary": Rarity("legendary", "Legendary", 0xFF9800, "🟠", "❰❱", "★ ✦ ✧ ✦ ★",   9.0,    2.40, (2, 3)),
        "mythic":    Rarity("mythic",    "Mythic",    0xF44336, "🔴", "✶",  "🌟 ✦ ✶ ✦ 🌟",   1.6,    3.20, (2, 4)),
        "secret":    Rarity("secret",    "Secret",    0xE91E63, "🔐", "🜲",  "🔮 ✦ 🜲 ✦ 🔮",  0.25,   4.30, (3, 4)),
        "chromatic": Rarity("chromatic", "Chromatic", 0x00E5FF, "🌈", "✺",  "🌈✨🌟✨🌈",     0.04,   6.00, (3, 5)),
    }
    RARITY_ORDER: List[str] = list(RARITIES.keys())
    RARITY_RANK: Dict[str, int] = {k: i for i, k in enumerate(RARITY_ORDER)}

    _BAR_SHADES = ["░", "▒", "▓", "█"]

    PREFIX_AFFIXES = [
        ("Vicious", {"atk": 1.0}), ("Brutal", {"atk": 1.3, "crit": 0.4}),
        ("Bloodthirsty", {"atk": 0.8, "hp": 0.4}), ("Savage", {"atk": 1.1, "crit": 0.6}),
        ("Tempered", {"atk": 0.6, "def": 0.6}), ("Fortified", {"def": 1.2}),
        ("Bulwark", {"def": 1.0, "hp": 0.6}), ("Vital", {"hp": 1.3}),
        ("Stalwart", {"hp": 1.0, "def": 0.5}), ("Precise", {"crit": 1.0}),
        ("Deadly", {"crit": 1.2, "atk": 0.5}), ("Balanced", {"atk": 0.5, "def": 0.5, "hp": 0.5}),
    ]
    SUFFIX_AFFIXES = [
        ("of Power", {"atk": 1.0}), ("of the Bear", {"hp": 1.2}),
        ("of the Titan", {"hp": 0.8, "def": 0.8}), ("of Warding", {"def": 1.2}),
        ("of the Fox", {"crit": 1.0}), ("of Slaying", {"atk": 0.8, "crit": 0.6}),
        ("of Vitality", {"hp": 1.0, "def": 0.4}), ("of the Void", {"atk": 0.7, "crit": 0.5, "def": 0.3}),
        ("of Eternity", {"hp": 0.6, "atk": 0.6, "def": 0.6}), ("of Doom", {"atk": 1.3, "crit": 0.7}),
    ]
    TYPE_PROFILE = {
        "weapon":    {"atk": 0.62, "crit": 0.18, "hp": 0.10, "def": 0.10},
        "armor":     {"def": 0.55, "hp": 0.33, "atk": 0.07, "crit": 0.05},
        "accessory": {"atk": 0.30, "crit": 0.28, "hp": 0.22, "def": 0.20},
    }
    _BUDGET_PER_ILVL = 2.6
    _BUDGET_BASE = 8.0

    _WORD_ICONS = {
        "sword": "🗡️", "blade": "🗡️", "katana": "🗡️", "rapier": "🤺", "claymore": "⚔️",
        "axe": "🪓", "cleaver": "🪓", "dagger": "🔪", "spear": "🔱", "lance": "🔱",
        "trident": "🔱", "mace": "🔨", "warhammer": "🔨", "hammer": "🔨", "bow": "🏹",
        "staff": "🪄", "wand": "🪄", "scepter": "👑", "scythe": "💀", "glaive": "⚜️",
        "halberd": "⚜️", "helm": "⛑️", "plate": "🛡️", "chestguard": "🛡️", "shield": "🛡️",
        "robe": "🥋", "cloak": "🧥", "greaves": "🦿", "gauntlets": "🥊", "bracers": "🥊",
        "ring": "💍", "amulet": "📿", "pendant": "📿", "charm": "🧿", "talisman": "🧿",
        "crown": "👑", "circlet": "👑", "relic": "🗿", "sigil": "🔯", "idol": "🗿",
    }

    # ---- elements: imbue gear with a damage type --------------------------
    # `strong` = element this one is super-effective against (1.5x in the model)
    ELEMENTS = {
        "fire":    {"emoji": "🔥", "adj": "Flaming",   "color": 0xFF5722, "strong": "nature"},
        "ice":     {"emoji": "❄️", "adj": "Frozen",    "color": 0x29B6F6, "strong": "fire"},
        "thunder": {"emoji": "⚡", "adj": "Storm",      "color": 0xFFEB3B, "strong": "water"},
        "nature":  {"emoji": "🌿", "adj": "Verdant",    "color": 0x66BB6A, "strong": "thunder"},
        "water":   {"emoji": "💧", "adj": "Tidal",      "color": 0x42A5F5, "strong": "fire"},
        "shadow":  {"emoji": "🌑", "adj": "Shadow",     "color": 0x5E35B1, "strong": "light"},
        "light":   {"emoji": "✨", "adj": "Radiant",    "color": 0xFFF59D, "strong": "shadow"},
        "void":    {"emoji": "🕳️", "adj": "Void-Touched","color": 0x311B92, "strong": "arcane"},
        "arcane":  {"emoji": "🔮", "adj": "Arcane",     "color": 0xAB47BC, "strong": "void"},
        "blood":   {"emoji": "🩸", "adj": "Bloodforged", "color": 0xB71C1C, "strong": "nature"},
    }

    # ---- gems: socket into gear for flat bonuses --------------------------
    GEMS = {
        "ruby":     {"emoji": "🔴", "stat": "atk",  "amount": 12, "name": "Ruby"},
        "sapphire": {"emoji": "🔵", "stat": "def",  "amount": 11, "name": "Sapphire"},
        "emerald":  {"emoji": "🟢", "stat": "hp",   "amount": 80, "name": "Emerald"},
        "diamond":  {"emoji": "💎", "stat": "crit", "amount": 3,  "name": "Diamond"},
        "onyx":     {"emoji": "⚫", "stat": "atk",  "amount": 20, "name": "Onyx"},
        "topaz":    {"emoji": "🟡", "stat": "crit", "amount": 5,  "name": "Topaz"},
        "opal":     {"emoji": "🌈", "stat": "all",  "amount": 6,  "name": "Opal"},
    }

    # ---- item sets: equip multiple pieces for escalating bonuses ----------
    # base item-name -> set key. Bonuses keyed by pieces-equipped count.
    ITEM_SETS = {
        "dragon": {
            "name": "Dragonlord",
            "members": {"dragon axe", "dragon scale", "dragon helm", "dragon blade", "ring of power"},
            "bonuses": {2: {"atk": 25, "label": "+25 ATK"},
                        3: {"atk": 60, "crit": 5, "label": "+60 ATK, +5% CRIT"}},
        },
        "void": {
            "name": "Voidwalker",
            "members": {"void staff", "void chestplate", "void serpent", "cosmic gem", "void shard"},
            "bonuses": {2: {"def": 30, "hp": 200, "label": "+30 DEF, +200 HP"},
                        3: {"def": 80, "hp": 600, "crit": 4, "label": "+80 DEF, +600 HP, +4% CRIT"}},
        },
        "celestial": {
            "name": "Celestial",
            "members": {"celestial plate", "celestial fragment", "omega ring", "armor of legends"},
            "bonuses": {2: {"hp": 400, "atk": 30, "label": "+400 HP, +30 ATK"},
                        3: {"hp": 1200, "atk": 90, "def": 60, "label": "+1.2K HP, +90 ATK, +60 DEF"}},
        },
    }

    @staticmethod
    def set_of(base_name):
        low = (base_name or "").lower()
        for key, s in V.ITEM_SETS.items():
            if low in s["members"]:
                return key
        return ""

    @staticmethod
    def set_bonus(set_counts):
        """set_counts: {set_key: pieces_equipped} -> merged bonus dict + labels."""
        total = {"atk": 0, "def": 0, "hp": 0, "crit": 0.0}
        labels = []
        for key, n in set_counts.items():
            s = V.ITEM_SETS.get(key)
            if not s:
                continue
            best = None
            for need in sorted(s["bonuses"]):
                if n >= need:
                    best = s["bonuses"][need]
            if best:
                for k in ("atk", "def", "hp", "crit"):
                    total[k] += best.get(k, 0)
                labels.append(f"🔗 {s['name']} ({n}pc): {best['label']}")
        return total, labels

    # ---- rarity lookups --------------------------------------------------
    @staticmethod
    def rarity(key):
        return V.RARITIES.get((key or "").lower(), V.RARITIES["common"])

    @staticmethod
    def rarity_color(key):
        return V.rarity(key).color

    @staticmethod
    def rarity_emoji(key):
        return V.rarity(key).emoji

    @staticmethod
    def rarity_label(key):
        return V.rarity(key).label

    @staticmethod
    def next_rarity(key):
        i = V.RARITY_RANK.get((key or "").lower(), 0)
        return V.RARITY_ORDER[min(i + 1, len(V.RARITY_ORDER) - 1)]

    # ---- number formatting ----------------------------------------------
    @staticmethod
    def fmt(n):
        try:
            n = float(n)
        except (TypeError, ValueError):
            return str(n)
        neg = n < 0
        n = abs(n)
        for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if n >= div:
                s = f"{n / div:.2f}".rstrip("0").rstrip(".") + suf
                return ("-" + s) if neg else s
        s = f"{int(n):,}"
        return ("-" + s) if neg else s

    @staticmethod
    def fmt_full(n):
        try:
            return f"{int(n):,}"
        except (TypeError, ValueError):
            return str(n)

    # ---- bars ------------------------------------------------------------
    @staticmethod
    def gradient_bar(frac, width=16, fill="█", empty="░"):
        width = max(1, width)
        frac = max(0.0, min(1.0, frac))
        exact = frac * width
        full = int(exact)
        rem = exact - full
        out = fill * full
        if full < width:
            if rem > 0.0:
                idx = min(len(V._BAR_SHADES) - 1, max(0, int(rem * len(V._BAR_SHADES))))
                out += V._BAR_SHADES[idx]
                full += 1
            out += empty * (width - full)
        return out[:width]

    @staticmethod
    def stat_bar(value, max_value, width=16, label=""):
        max_value = max(1.0, float(max_value))
        bar = V.gradient_bar(value / max_value, width)
        head = f"{label} " if label else ""
        return f"{head}▕{bar}▏ {V.fmt(value)}/{V.fmt(max_value)}"

    @staticmethod
    def xp_bar(current, total, slots=16):
        total = max(1, int(total))
        current = max(0, int(current))
        frac = min(1.0, current / total)
        return f"▕{V.gradient_bar(frac, slots)}▏ {frac * 100:4.1f}%"

    @staticmethod
    def power_bar(power, ref=1000, width=18):
        p = max(0, int(power))
        frac = math.log10(p + 1) / math.log10(max(10, ref) + 1)
        return f"▕{V.gradient_bar(min(1.0, frac), width)}▏ ⚡{V.fmt(p)}"

    @staticmethod
    def hp_color_bar(cur, mx, width=16):
        mx = max(1, mx)
        frac = cur / mx
        fill = "💚" if frac > 0.5 else ("💛" if frac > 0.25 else "❤️")
        filled = int(round(frac * width))
        return fill * filled + "🖤" * (width - filled)

    @staticmethod
    def class_emoji(class_name):
        return {
            "warrior": "⚔️", "mage": "🔮", "rogue": "🗡️", "paladin": "🛡️",
            "ranger": "🏹", "druid": "🌿", "berserker": "🪓", "knight": "🐴",
            "assassin": "🥷", "necromancer": "💀", "monk": "🧘", "voidreaper": "🌀",
            "celestial": "👼",
        }.get((class_name or "").lower(), "🎭")

    # ---- luck-scaled rarity roller --------------------------------------
    @staticmethod
    def luck_score(level=1, crit=0.0, accessory_power=0, event_luck=1.0, bonus=0.0):
        base = (math.log10(max(1, level)) * 0.9 + crit * 4.0
                + math.log10(accessory_power + 1) * 0.6 + bonus)
        return max(0.0, base * max(0.1, event_luck))

    @staticmethod
    def rarity_weights(luck=0.0, floor=None, cap=None):
        lo = V.RARITY_RANK.get((floor or "common").lower(), 0)
        hi = V.RARITY_RANK.get((cap or "chromatic").lower(), len(V.RARITY_ORDER) - 1)
        weights = {}
        for key in V.RARITY_ORDER:
            rank = V.RARITY_RANK[key]
            if rank < lo or rank > hi:
                continue
            weights[key] = V.RARITIES[key].weight * (1.0 + luck * 0.62) ** rank
        return weights

    @staticmethod
    def roll_rarity(luck=0.0, floor=None, cap=None, rng=None):
        rng = rng or random
        weights = V.rarity_weights(luck, floor, cap)
        keys = list(weights.keys())
        total = sum(weights.values())
        if total <= 0:
            return floor or "common"
        pick = rng.random() * total
        upto = 0.0
        for k in keys:
            upto += weights[k]
            if pick <= upto:
                return k
        return keys[-1]

    # ---- multi-stat item roll -------------------------------------------
    @staticmethod
    def _quality_stars(quality):
        if quality >= 1.18:
            return "★★★★★"
        if quality >= 1.10:
            return "★★★★☆"
        if quality >= 1.02:
            return "★★★☆☆"
        if quality >= 0.94:
            return "★★☆☆☆"
        return "★☆☆☆☆"

    @staticmethod
    def roll_item(base_name, item_type, rarity_key, ilvl, luck=0.0, rng=None):
        rng = rng or random
        r = V.rarity(rarity_key)
        profile = V.TYPE_PROFILE.get(item_type, V.TYPE_PROFILE["accessory"])

        budget = (V._BUDGET_BASE + ilvl * V._BUDGET_PER_ILVL) * r.stat_mult
        quality = rng.uniform(0.85, 1.15) + min(0.15, luck * 0.05)
        budget *= quality

        n_aff = rng.randint(r.affixes[0], r.affixes[1])
        pool_prefix = V.PREFIX_AFFIXES[:]
        pool_suffix = V.SUFFIX_AFFIXES[:]
        rng.shuffle(pool_prefix)
        rng.shuffle(pool_suffix)
        chosen = []
        use_prefix = True
        while len(chosen) < n_aff and (pool_prefix or pool_suffix):
            if use_prefix and pool_prefix:
                chosen.append(pool_prefix.pop())
            elif pool_suffix:
                chosen.append(pool_suffix.pop())
            elif pool_prefix:
                chosen.append(pool_prefix.pop())
            use_prefix = not use_prefix

        dist = dict(profile)
        affix_budget = budget * (0.12 * len(chosen))
        for _name, ad in chosen:
            tot = sum(ad.values()) or 1.0
            for stat, w in ad.items():
                dist[stat] = dist.get(stat, 0.0) + (w / tot) * 0.5
        norm = sum(dist.values()) or 1.0
        dist = {k: v / norm for k, v in dist.items()}

        total_budget = budget + affix_budget
        hp = int(total_budget * dist.get("hp", 0.0) * 6.0)
        atk = int(total_budget * dist.get("atk", 0.0) * 1.0)
        defense = int(total_budget * dist.get("def", 0.0) * 0.9)
        crit = round(total_budget * dist.get("crit", 0.0) * 0.06, 1)

        crit = round(crit * rng.uniform(0.9, 1.1) + luck * 0.2, 1)
        atk = max(0, int(atk * rng.uniform(0.95, 1.05)))
        defense = max(0, int(defense * rng.uniform(0.95, 1.05)))
        hp = max(0, int(hp * rng.uniform(0.95, 1.05)))

        prefix_names = {a for a, _ in V.PREFIX_AFFIXES}
        suffix_names = {a for a, _ in V.SUFFIX_AFFIXES}
        prefixes = [n for n, _ in chosen if n in prefix_names]
        suffixes = [n for n, _ in chosen if n in suffix_names]
        title = base_name.title()
        if prefixes:
            title = f"{prefixes[0]} {title}"
        if suffixes:
            title = f"{title} {suffixes[0]}"

        # elemental imbue — chance & tier scale with rarity
        element = ""
        if rng.random() < 0.18 + 0.07 * V.RARITY_RANK[r.key]:
            element = rng.choice(list(V.ELEMENTS.keys()))
            title = f"{V.ELEMENTS[element]['adj']} {title}"

        # sockets — rarer gear has more potential sockets (empty on drop)
        max_sock = min(3, V.RARITY_RANK[r.key] // 2)
        sockets = rng.randint(0, max_sock) if max_sock else 0

        # set membership (for set bonuses when several pieces equipped)
        set_name = V.set_of(base_name)

        return RolledItem(
            base_name=base_name, display_name=title, item_type=item_type,
            rarity=r.key, ilvl=ilvl, hp=hp, atk=atk, defense=defense, crit=crit,
            quality=round(quality, 3), affixes=[n for n, _ in chosen],
            element=element, sockets=sockets, gems=[], set_name=set_name,
        )

    @staticmethod
    def roll_drop(item_pool_by_rarity, level, luck=0.0, floor=None, cap=None,
                  zone_bonus=1.0, rng=None):
        rng = rng or random
        chosen_rarity = V.roll_rarity(luck, floor, cap, rng)
        order = [chosen_rarity] + list(reversed(V.RARITY_ORDER[:V.RARITY_RANK[chosen_rarity]]))
        for key in order:
            pool = item_pool_by_rarity.get(key)
            if pool:
                base_name, item_type = rng.choice(list(pool))
                ilvl = max(1, int(level * zone_bonus) + V.RARITY_RANK[key] * 4)
                return V.roll_item(base_name, item_type, key, ilvl, luck, rng)
        return None

    # ---- item icons / cards / reveals -----------------------------------
    @staticmethod
    def item_icon(name, item_type="", rarity_key="common"):
        low = (name or "").lower()
        for word, icon in V._WORD_ICONS.items():
            if word in low:
                return icon
        type_icon = {"weapon": "⚔️", "armor": "🛡️", "accessory": "💍",
                     "consumable": "🧪", "material": "🔩"}.get(item_type)
        return type_icon or V.rarity_emoji(rarity_key)

    @staticmethod
    def _stat_line(emoji, label, value, width=10, maxv=0):
        if maxv:
            bar = V.gradient_bar(min(1.0, float(value) / maxv), width)
            return f"{emoji} {label:<4} ▕{bar}▏ +{V.fmt(value)}"
        return f"{emoji} {label:<4} +{V.fmt(value)}"

    @staticmethod
    def item_card(item, enchant=0, ref_stat=0):
        r = V.rarity(item.rarity)
        icon = V.item_icon(item.base_name, item.item_type, item.rarity)
        elem = V.ELEMENTS.get(item.element)
        border = (r.glyph * 18)[:24]
        enchant_tag = f"  ✦{enchant}" if enchant else ""
        ref = ref_stat or max(50, item.power)
        title = f"{icon}  {item.display_name}{enchant_tag}"
        sub = f"{r.emoji} {r.label} {item.item_type.title()}  •  iLvl {item.ilvl}  •  {V._quality_stars(item.quality)}"
        if elem:
            sub += f"  •  {elem['emoji']} {item.element.title()}"
        lines = [border, title, sub, ""]
        gem_bonus = V.gem_stats(item.gems)
        if item.atk or gem_bonus["atk"]:
            lines.append(V._stat_line("⚔️", "ATK", item.atk + gem_bonus["atk"], maxv=ref))
        if item.defense or gem_bonus["def"]:
            lines.append(V._stat_line("🛡️", "DEF", item.defense + gem_bonus["def"], maxv=ref))
        if item.hp or gem_bonus["hp"]:
            lines.append(V._stat_line("❤️", "HP", item.hp + gem_bonus["hp"], maxv=ref * 5))
        if item.crit or gem_bonus["crit"]:
            lines.append(f"💫 CRIT +{round(item.crit + gem_bonus['crit'], 1)}%")
        if item.affixes:
            lines.append("")
            lines.append("✨ " + "  ".join(f"[{a}]" for a in item.affixes))
        if item.sockets:
            slots = "".join(V.GEMS[g]["emoji"] if i < len(item.gems) else "⬡"
                            for i, g in enumerate((item.gems + [None] * item.sockets)[:item.sockets]))
            lines.append(f"💠 Sockets: {slots}")
        if item.set_name and item.set_name in V.ITEM_SETS:
            lines.append(f"🔗 Set: {V.ITEM_SETS[item.set_name]['name']}")
        lines.append("")
        lines.append(f"⚡ Power {V.fmt(item.power)}   💰 Value {V.fmt(item.value)}   🏅 {V.power_rank_label(item.power)}")
        lines.append(border)
        return "```\n" + "\n".join(lines) + "\n```"

    @staticmethod
    def drop_reveal_frames(item):
        r = V.rarity(item.rarity)
        rank = V.RARITY_RANK[item.rarity]
        icon = V.item_icon(item.base_name, item.item_type, item.rarity)
        spin = ["⚪", "🟢", "🔵", "🟣", "🟠", "🔴", "🔐", "🌈"]
        frames = []
        for i in range(2 + rank):
            cycler = " ".join(spin[(i + j) % len(spin)] for j in range(5))
            frames.append(f"🎁 **Opening...**\n{cycler}")
        if rank >= 4:
            frames.append(f"{r.aura}\n❓ ❓ ❓\n{r.aura}")
        elem = V.ELEMENTS.get(item.element)
        etag = f"  {elem['emoji']}" if elem else ""
        frames.append(
            f"{r.aura}\n{icon}  **{item.display_name}**{etag}\n"
            f"{r.emoji} **{r.label.upper()}**  •  {V._quality_stars(item.quality)}\n"
            f"⚡ Power **{V.fmt(item.power)}**  •  🏅 {V.power_rank_label(item.power)}\n{r.aura}"
        )
        return frames

    @staticmethod
    def drop_banner(item):
        r = V.rarity(item.rarity)
        icon = V.item_icon(item.base_name, item.item_type, item.rarity)
        elem = V.ELEMENTS.get(item.element)
        etag = f"{elem['emoji']} " if elem else ""
        return f"{r.aura}  {etag}{icon} **{item.display_name}** — {r.emoji} {r.label} • ⚡{V.fmt(item.power)}  {r.aura}"

    # ---- gems / sockets ---------------------------------------------------
    @staticmethod
    def gem_stats(gems):
        out = {"atk": 0, "def": 0, "hp": 0, "crit": 0.0}
        for g in (gems or []):
            data = V.GEMS.get(g)
            if not data:
                continue
            if data["stat"] == "all":
                out["atk"] += data["amount"]
                out["def"] += data["amount"]
                out["hp"] += data["amount"] * 10
                out["crit"] += data["amount"] * 0.3
            elif data["stat"] == "crit":
                out["crit"] += data["amount"]
            else:
                out[data["stat"]] += data["amount"]
        out["crit"] = round(out["crit"], 1)
        return out

    # ---- power tiers / ranks ---------------------------------------------
    _RANK_TIERS = [
        (0, "Bronze", "🥉"), (300, "Silver", "🥈"), (700, "Gold", "🥇"),
        (1500, "Platinum", "💎"), (3000, "Diamond", "💠"), (6000, "Master", "🔱"),
        (12000, "Grandmaster", "👑"), (25000, "Mythic", "🌟"), (60000, "Godslayer", "⚡"),
    ]

    @staticmethod
    def power_rank_label(power):
        label, emoji = "Bronze", "🥉"
        for need, name, em in V._RANK_TIERS:
            if power >= need:
                label, emoji = name, em
        return f"{emoji} {label}"

    @staticmethod
    def sparkline(values):
        blocks = "▁▂▃▄▅▆▇█"
        if not values:
            return ""
        mx = max(values) or 1
        return "".join(blocks[min(len(blocks) - 1, int(v / mx * (len(blocks) - 1)))] for v in values)

    # ---- elemental damage model ------------------------------------------
    @staticmethod
    def element_matchup(attacker, defender):
        a = V.ELEMENTS.get(attacker)
        if a and a.get("strong") == defender:
            return 1.5
        d = V.ELEMENTS.get(defender)
        if d and d.get("strong") == attacker:
            return 0.75
        return 1.0

    @staticmethod
    def damage_calc(atk, crit_chance, defender_def=0, att_elem="", def_elem="", rng=None):
        rng = rng or random
        base = rng.randint(int(atk * 0.75), int(atk * 1.25)) - int(defender_def * 0.5)
        base = max(1, base)
        mult = V.element_matchup(att_elem, def_elem)
        base = int(base * mult)
        is_crit = rng.random() < max(0.0, crit_chance)
        if is_crit:
            base = int(base * 1.75)
        return max(1, base), is_crit, mult

    # ---- reforge / craft economy -----------------------------------------
    @staticmethod
    def reforge_roll(base_name, item_type, rarity_key, ilvl, luck=0.0, rng=None):
        """Reroll an item's stats, keeping identity (rarity/ilvl/type)."""
        return V.roll_item(base_name, item_type, rarity_key, ilvl, luck, rng)

    @staticmethod
    def reforge_cost(rarity_key, ilvl):
        return int((50 + ilvl * 8) * (1 + V.RARITY_RANK[rarity_key]))

    @staticmethod
    def craft_cost(rarity_key):
        return int(40 * (2 ** V.RARITY_RANK[rarity_key]))   # dust cost, doubles per tier

    @staticmethod
    def gem_combine_cost():
        return 3   # 3 identical gems -> next-tier behaviour handled in bot

    # ---- procedural unique names (legendary+ flavor) ---------------------
    _UNIQUE_PRE = ["Doom", "Star", "Blood", "Frost", "Storm", "Soul", "Dread", "Dawn",
                   "Night", "Hell", "Sky", "Ember", "Grave", "Wyrm", "Rune", "Abyss"]
    _UNIQUE_MID = ["bringer", "render", "weaver", "piercer", "song", "fang", "edge",
                   "bane", "heart", "caller", "ward", "reaver", "splitter", "binder"]
    _UNIQUE_SUF = ["of the Fallen", "of Ages", "of the Eclipse", "of Ruin", "of the Maelstrom",
                   "of Embers", "of the Forgotten King", "of Infinity", "of the Last Star"]

    @staticmethod
    def unique_name(rng=None):
        rng = rng or random
        name = rng.choice(V._UNIQUE_PRE) + rng.choice(V._UNIQUE_MID)
        if rng.random() < 0.5:
            name += " " + rng.choice(V._UNIQUE_SUF)
        return name

    # ---- transparency: odds table + loot simulation ----------------------
    @staticmethod
    def odds_table(luck=0.0, floor=None, cap=None):
        weights = V.rarity_weights(luck, floor, cap)
        total = sum(weights.values()) or 1.0
        lines = [f"🎲 **DROP ODDS** (luck {luck:.1f})", "```"]
        for key in V.RARITY_ORDER:
            if key not in weights:
                continue
            r = V.rarity(key)
            pct = 100.0 * weights[key] / total
            bar = V.gradient_bar(min(1.0, pct / 60.0), 14)
            lines.append(f"{r.emoji} {r.label:<10} {bar} {pct:6.3f}%")
        lines.append("```")
        return "\n".join(lines)

    @staticmethod
    def loot_sim(n=10000, luck=0.0, floor=None, cap=None, rng=None):
        rng = rng or random
        counts = {k: 0 for k in V.RARITY_ORDER}
        for _ in range(n):
            counts[V.roll_rarity(luck, floor, cap, rng)] += 1
        return counts

    # ---- item comparison (equipped vs candidate) -------------------------
    @staticmethod
    def compare_stats(old, new_item):
        """old: dict(atk,def,hp,crit,power). Returns a delta block with arrows."""
        def arrow(d):
            if d > 0:
                return f"🔺+{V.fmt(d)}"
            if d < 0:
                return f"🔻{V.fmt(d)}"
            return "▪️0"
        ng = V.gem_stats(new_item.gems)
        rows = [
            ("ATK", new_item.atk + ng["atk"], old.get("atk", 0)),
            ("DEF", new_item.defense + ng["def"], old.get("def", 0)),
            ("HP", new_item.hp + ng["hp"], old.get("hp", 0)),
            ("CRIT", round(new_item.crit + ng["crit"], 1), old.get("crit", 0)),
            ("PWR", new_item.power, old.get("power", 0)),
        ]
        out = ["```", f"{'STAT':<5}{'NEW':>10}{'OLD':>10}   Δ"]
        for name, nv, ov in rows:
            out.append(f"{name:<5}{V.fmt(nv):>10}{V.fmt(ov):>10}   {arrow(nv - ov)}")
        out.append("```")
        return "\n".join(out)

    # ---- class skills: auto-cast when mana fills --------------------------
    # kind: damage (bonus burst), heal (restore HP), shield (reduce next hit),
    #       execute (extra dmg vs low-HP), lifesteal (heal % of dmg dealt)
    CLASS_SKILLS = {
        "warrior":     {"name": "Shield Slam",   "emoji": "🛡️", "kind": "damage",    "power": 1.4, "element": "",       "cost": 1.0},
        "mage":        {"name": "Arcane Nova",    "emoji": "🔮", "kind": "damage",    "power": 2.2, "element": "arcane", "cost": 1.0},
        "rogue":       {"name": "Backstab",       "emoji": "🗡️", "kind": "execute",   "power": 2.0, "element": "shadow", "cost": 1.0},
        "paladin":     {"name": "Holy Light",     "emoji": "✨", "kind": "heal",      "power": 0.35, "element": "light",  "cost": 1.0},
        "ranger":      {"name": "Piercing Shot",  "emoji": "🏹", "kind": "damage",    "power": 1.7, "element": "nature", "cost": 1.0},
        "druid":       {"name": "Regrowth",       "emoji": "🌿", "kind": "heal",      "power": 0.30, "element": "nature", "cost": 1.0},
        "berserker":   {"name": "Bloodrage",      "emoji": "🪓", "kind": "lifesteal", "power": 2.0, "element": "blood",  "cost": 1.0},
        "knight":      {"name": "Bulwark",        "emoji": "🛡️", "kind": "shield",    "power": 0.6, "element": "",       "cost": 1.0},
        "assassin":    {"name": "Death Mark",     "emoji": "🥷", "kind": "execute",   "power": 2.6, "element": "shadow", "cost": 1.0},
        "necromancer": {"name": "Soul Drain",     "emoji": "💀", "kind": "lifesteal", "power": 1.8, "element": "void",   "cost": 1.0},
        "monk":        {"name": "Chi Burst",      "emoji": "🧘", "kind": "damage",    "power": 1.6, "element": "light",  "cost": 1.0},
        "voidreaper":  {"name": "Void Collapse",  "emoji": "🌀", "kind": "execute",   "power": 3.2, "element": "void",   "cost": 1.0},
        "celestial":   {"name": "Judgment",       "emoji": "👼", "kind": "damage",    "power": 3.0, "element": "light",  "cost": 1.0},
    }

    @staticmethod
    def class_skill(class_name):
        return V.CLASS_SKILLS.get((class_name or "").lower(), V.CLASS_SKILLS["warrior"])

    @staticmethod
    def cast_skill(class_name, atk, enemy_hp, enemy_max_hp, att_elem="", def_elem="", rng=None):
        """Resolve an auto-cast skill. Returns dict with damage, heal, shield, text."""
        rng = rng or random
        sk = V.class_skill(class_name)
        elem = sk["element"] or att_elem
        mult = V.element_matchup(elem, def_elem) if elem else 1.0
        res = {"damage": 0, "heal": 0, "shield": 0.0, "lifesteal": 0,
               "name": sk["name"], "emoji": sk["emoji"], "element": elem, "matchup": mult}
        kind = sk["kind"]
        if kind == "damage":
            res["damage"] = int(atk * sk["power"] * mult * rng.uniform(0.9, 1.1))
        elif kind == "execute":
            low = 1.0 + (1.0 - max(0, enemy_hp) / max(1, enemy_max_hp)) * 1.5  # up to +150% on low HP
            res["damage"] = int(atk * sk["power"] * mult * low * rng.uniform(0.9, 1.1))
        elif kind == "lifesteal":
            dmg = int(atk * sk["power"] * mult * rng.uniform(0.9, 1.1))
            res["damage"] = dmg
            res["lifesteal"] = int(dmg * 0.4)
            res["heal"] = res["lifesteal"]
        elif kind == "heal":
            res["heal"] = int(atk * sk["power"] * 10)  # heal scales off power budget
        elif kind == "shield":
            res["shield"] = sk["power"]  # fraction of next hit blocked
        et = f" {V.ELEMENTS[elem]['emoji']}" if elem in V.ELEMENTS else ""
        tag = "  💥SUPER-EFFECTIVE!" if mult > 1.0 else ("  …resisted" if mult < 1.0 else "")
        res["text"] = f"{sk['emoji']} **{sk['name']}**{et}!{tag}"
        return res

    # ---- enemy elements & multi-phase bosses ------------------------------
    @staticmethod
    def enemy_element(name):
        """Deterministically assign an element to an enemy/boss by name."""
        keys = list(V.ELEMENTS.keys())
        h = sum(ord(c) for c in (name or "x"))
        return keys[h % len(keys)]

    BOSS_PHASE_NAMES = ["Awakened", "Enraged", "Final Form"]

    @staticmethod
    def boss_phase(cur_hp, max_hp, n_phases=3):
        """Return (phase_index 0-based, phase_label, atk_multiplier) from HP%."""
        max_hp = max(1, max_hp)
        frac = max(0.0, min(1.0, cur_hp / max_hp))
        # phase 0 while >66%, 1 while >33%, 2 below
        idx = 0
        if frac <= 1.0 / 3:
            idx = 2
        elif frac <= 2.0 / 3:
            idx = 1
        idx = min(idx, n_phases - 1)
        atk_mult = 1.0 + idx * 0.45  # hits harder each phase
        label = V.BOSS_PHASE_NAMES[min(idx, len(V.BOSS_PHASE_NAMES) - 1)]
        return idx, label, atk_mult

    @staticmethod
    def boss_phase_banner(name, phase_label, element):
        elem = V.ELEMENTS.get(element)
        et = f"{elem['emoji']} " if elem else ""
        flair = "🔥" * (V.BOSS_PHASE_NAMES.index(phase_label) + 1 if phase_label in V.BOSS_PHASE_NAMES else 1)
        return f"{flair} **{name}** enters **{phase_label}**! {et}{flair}"


# ============================================================================
# CONFIG & PATHS
# ============================================================================

BOT_DIR = Path(__file__).parent
DB_PATH = BOT_DIR / "rpg.db"
CONFIG_PATH = BOT_DIR / "bot_config.json"
TOKEN_PATH = BOT_DIR / ".discord_token"
SERVER_PATH = BOT_DIR / ".server_created"
SAVE_INTERVAL_SECONDS = 5

# ============================================================================
# IMAGE GENERATION CONSTANTS & HELPERS
# ============================================================================

RARITY_COLORS = {
    "common": (158, 158, 158),
    "uncommon": (76, 175, 80),
    "rare": (33, 150, 243),
    "epic": (156, 39, 176),
    "legendary": (255, 152, 0),
    "mythic": (244, 67, 54),
    "secret": (233, 30, 99),
    "chromatic": (0, 229, 255),
}

TYPE_EMOJIS = {
    "weapon": "⚔️",
    "armor": "🛡️",
    "accessory": "💍",
    "consumable": "🧪",
    "material": "🪨",
}

def load_fonts(title_size: int = 24, text_size: int = 16, small_size: int = 12) -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    """Load fonts with fallback to defaults."""
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", title_size)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", text_size)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", small_size)
    except (FileNotFoundError, OSError):
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    return title_font, text_font, small_font

def get_rarity_color(rarity: str) -> tuple:
    """Get RGB color tuple for rarity tier."""
    return RARITY_COLORS.get(rarity, (158, 158, 158))

# ============================================================================
# IMAGE GENERATION WITH PILLOW
# ============================================================================

def generate_item_card(item_name: str, rarity: str, item_type: str, price: int, seller_name: str, power: int = 0) -> BytesIO:
    """Generate a beautiful item card image using Pillow with detailed gear visuals."""
    bg_color = get_rarity_color(rarity)
    
    # Create image
    img = Image.new('RGB', (ITEM_CARD_WIDTH, ITEM_CARD_HEIGHT), color=(20, 20, 30))
    draw = ImageDraw.Draw(img)
    
    title_font, text_font, small_font = load_fonts(24, 16, 12)
    
    # Draw main header with rarity color
    draw.rectangle([(0, 0), (500, 100)], fill=bg_color)
    draw.rectangle([(2, 2), (498, 98)], outline=(255, 255, 255), width=3)
    
    # Draw item title
    draw.text((20, 15), f"{TYPE_EMOJIS.get(item_type, '📦')} {item_name}", fill=(255, 255, 255), font=title_font)
    draw.text((20, 50), f"⭐ {rarity.upper()}", fill=(255, 215, 0), font=text_font)
    
    # Draw gear visualization box with border
    draw.rectangle([(30, 120), (230, 320)], fill=(40, 40, 60), outline=bg_color, width=3)
    
    # Generate gear visual based on item type
    draw_gear_visual(draw, item_type, rarity, 30, 120, 200, 200)
    
    # Draw stats panel on the right
    draw.rectangle([(250, 120), (470, 320)], outline=bg_color, width=2)
    
    draw.text((265, 130), "━━━ STATS ━━━", fill=bg_color, font=text_font)
    
    draw.text((265, 170), f"💰 Price: {price:,}g", fill=(255, 215, 0), font=text_font)
    draw.text((265, 205), f"⚡ Power: {power}", fill=(150, 200, 255), font=text_font)
    draw.text((265, 240), f"👤 Seller:", fill=(200, 200, 200), font=small_font)
    draw.text((265, 260), f"{seller_name[:25]}", fill=(150, 200, 255), font=small_font)
    
    # Convert to bytes
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


def draw_gear_visual(draw, item_type: str, rarity: str, x: int, y: int, width: int, height: int) -> None:
    """Draw detailed gear visualization based on item type and rarity."""
    center_x = x + width // 2
    center_y = y + height // 2
    color = get_rarity_color(rarity)
    glow_color = tuple(min(255, c + 50) for c in color)
    
    if item_type == "weapon":
        # Draw sword
        draw.line([(center_x, center_y - 60), (center_x, center_y + 40)], fill=color, width=8)  # Blade
        draw.polygon([(center_x - 5, center_y - 60), (center_x + 5, center_y - 60), (center_x, center_y - 70)], fill=glow_color)  # Tip
        draw.rectangle([(center_x - 12, center_y + 35), (center_x + 12, center_y + 50)], fill=(139, 69, 19))  # Handle
        # Crossguard
        draw.line([(center_x - 25, center_y + 30), (center_x + 25, center_y + 30)], fill=color, width=6)
        
    elif item_type == "armor":
        # Draw shield/chestplate
        draw.ellipse([(center_x - 40, center_y - 45), (center_x + 40, center_y + 45)], fill=color, outline=glow_color, width=3)
        # Center circle
        draw.ellipse([(center_x - 20, center_y - 25), (center_x + 20, center_y + 25)], fill=(100, 100, 120), outline=color, width=2)
        # Details
        draw.rectangle([(center_x - 5, center_y - 30), (center_x + 5, center_y + 30)], outline=glow_color, width=2)
        
    elif item_type == "accessory":
        # Draw ring/amulet
        draw.ellipse([(center_x - 35, center_y - 35), (center_x + 35, center_y + 35)], outline=color, width=5)
        draw.ellipse([(center_x - 25, center_y - 25), (center_x + 25, center_y + 25)], fill=(30, 30, 50), outline=color, width=2)
        # Sparkles
        for i in range(4):
            angle = (i * 90) * 3.14159 / 180
            px = int(center_x + 45 * math.cos(angle))
            py = int(center_y + 45 * math.sin(angle))
            draw.polygon([(px - 3, py), (px, py - 3), (px + 3, py), (px, py + 3)], fill=glow_color)
        
    elif item_type == "consumable":
        # Draw potion bottle
        draw.rectangle([(center_x - 15, center_y - 5), (center_x + 15, center_y + 45)], fill=color, outline=glow_color, width=2)
        draw.rectangle([(center_x - 12, center_y - 8), (center_x + 12, center_y - 3)], fill=(139, 69, 19))  # Cork
        draw.rectangle([(center_x - 5, center_y - 10), (center_x + 5, center_y - 6)], fill=(200, 200, 200))  # Shine
        # Liquid inside
        draw.rectangle([(center_x - 13, center_y + 20), (center_x + 13, center_y + 43)], fill=(color[0]//2, color[1]//2, color[2]//2))
        
    elif item_type == "material":
        # Draw ore/crystal
        draw.polygon([(center_x, center_y - 40), (center_x + 35, center_y + 10), (center_x - 35, center_y + 10)], fill=color, outline=glow_color, width=3)
        # Inner shine
        draw.polygon([(center_x - 10, center_y - 10), (center_x + 10, center_y - 10), (center_x, center_y + 15)], fill=glow_color)
    
    else:
        # Default treasure chest
        draw.rectangle([(center_x - 30, center_y - 20), (center_x + 30, center_y + 25)], fill=color, outline=glow_color, width=3)
        # Lid
        draw.rectangle([(center_x - 32, center_y - 25), (center_x + 32, center_y - 18)], fill=(200, 150, 100), outline=glow_color, width=2)
        # Gold coins
        draw.ellipse([(center_x - 12, center_y - 5), (center_x - 2, center_y + 5)], fill=(255, 215, 0))
        draw.ellipse([(center_x + 2, center_y - 5), (center_x + 12, center_y + 5)], fill=(255, 215, 0))


def generate_character_gear_preview(equipped: dict, char_name: str, level: int, power: int) -> BytesIO:
    """Generate a character gear preview showing equipped items visually on character."""
    img = Image.new('RGB', (CHAR_PREVIEW_WIDTH, CHAR_PREVIEW_HEIGHT), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)
    
    title_font, text_font, small_font = load_fonts(28, 16, 12)
    
    # Header with character name and level
    draw.rectangle([(0, 0), (600, 80)], fill=(40, 40, 60))
    draw.rectangle([(2, 2), (598, 78)], outline=(255, 215, 0), width=2)
    draw.text((20, 20), f"⚔️ {char_name.upper()} - LVL {level}", fill=(255, 215, 0), font=title_font)
    
    # Main character area - larger and centered
    char_area_x1, char_area_y1 = 50, 110
    char_area_x2, char_area_y2 = 550, 450
    draw.rectangle([(char_area_x1, char_area_y1), (char_area_x2, char_area_y2)], 
                   fill=(20, 20, 35), outline=(100, 150, 200), width=3)
    
    # Center of character
    center_x = (char_area_x1 + char_area_x2) // 2
    center_y = (char_area_y1 + char_area_y2) // 2 - 20
    
    # Draw character with equipped gear overlaid
    
    # Head
    draw.ellipse([(center_x - 20, center_y - 80), (center_x + 20, center_y - 35)], 
                 fill=(220, 190, 160), outline=(180, 140, 100), width=2)
    
    # Helmet/head decoration if equipped armor exists
    if equipped.get('armor'):
        # Armor affects head appearance - add helmet visor
        draw.rectangle([(center_x - 22, center_y - 75), (center_x + 22, center_y - 50)], 
                       fill=(150, 150, 180), outline=(200, 200, 255), width=2)
        draw.line([(center_x - 15, center_y - 65), (center_x + 15, center_y - 65)], 
                  fill=(100, 150, 255), width=2)
    
    # Main body (armor color)
    armor_color = (200, 100, 100) if not equipped.get('armor') else (100, 120, 180)
    draw.rectangle([(center_x - 25, center_y - 30), (center_x + 25, center_y + 60)], 
                   fill=armor_color, outline=(150, 150, 200), width=3)
    
    # Armor details if equipped
    if equipped.get('armor'):
        # Add armor plating details
        draw.rectangle([(center_x - 23, center_y - 10), (center_x - 15, center_y + 40)], 
                       fill=(120, 140, 200), outline=(180, 200, 255), width=1)
        draw.rectangle([(center_x + 15, center_y - 10), (center_x + 23, center_y + 40)], 
                       fill=(120, 140, 200), outline=(180, 200, 255), width=1)
    
    # Left arm + weapon
    arm_color = (220, 190, 160)
    draw.line([(center_x - 25, center_y - 15), (center_x - 55, center_y + 20)], 
              fill=arm_color, width=8)
    
    # Draw weapon in hand if equipped
    if equipped.get('weapon'):
        weapon_name = equipped['weapon'].lower()
        # Sword
        if 'sword' in weapon_name or 'blade' in weapon_name or 'claymore' in weapon_name:
            draw.line([(center_x - 55, center_y + 20), (center_x - 55, center_y - 60)], 
                      fill=(200, 200, 180), width=6)  # Blade
            draw.polygon([(center_x - 55, center_y - 60), (center_x - 58, center_y - 68), 
                         (center_x - 52, center_y - 68)], fill=(255, 215, 0))  # Tip
            draw.rectangle([(center_x - 58, center_y + 20), (center_x - 52, center_y + 35)], 
                          fill=(139, 69, 19))  # Handle
        # Axe
        elif 'axe' in weapon_name or 'cleaver' in weapon_name:
            draw.rectangle([(center_x - 62, center_y - 70), (center_x - 48, center_y - 50)], 
                          fill=(220, 100, 100), outline=(180, 50, 50), width=2)  # Axe head
            draw.rectangle([(center_x - 55, center_y - 50), (center_x - 52, center_y + 30)], 
                          fill=(139, 69, 19))  # Handle
        # Bow
        elif 'bow' in weapon_name:
            draw.arc([(center_x - 65, center_y - 70), (center_x - 45, center_y + 30)], 
                    0, 180, fill=(200, 150, 100), width=4)
            draw.line([(center_x - 55, center_y - 70), (center_x - 55, center_y + 30)], 
                     fill=(139, 69, 19), width=2)  # String
        # Staff/wand
        elif 'staff' in weapon_name or 'wand' in weapon_name or 'scepter' in weapon_name:
            draw.line([(center_x - 55, center_y + 20), (center_x - 55, center_y - 80)], 
                     fill=(200, 150, 100), width=4)  # Staff
            draw.ellipse([(center_x - 65, center_y - 85), (center_x - 45, center_y - 65)], 
                        fill=(100, 150, 255), outline=(150, 200, 255), width=2)  # Orb
        else:
            # Generic weapon
            draw.line([(center_x - 55, center_y + 20), (center_x - 55, center_y - 50)], 
                     fill=(200, 200, 180), width=5)
    
    # Right arm
    draw.line([(center_x + 25, center_y - 15), (center_x + 55, center_y + 20)], 
              fill=arm_color, width=8)
    
    # If accessory equipped, show it on right wrist
    if equipped.get('accessory'):
        draw.ellipse([(center_x + 48, center_y + 15), (center_x + 62, center_y + 30)], 
                    fill=(255, 215, 0), outline=(200, 150, 0), width=2)
    
    # Legs
    draw.line([(center_x - 12, center_y + 60), (center_x - 12, center_y + 140)], 
              fill=(100, 100, 120), width=8)
    draw.line([(center_x + 12, center_y + 60), (center_x + 12, center_y + 140)], 
              fill=(100, 100, 120), width=8)
    
    # Feet
    draw.rectangle([(center_x - 18, center_y + 140), (center_x - 5, center_y + 155)], 
                   fill=(80, 80, 100), outline=(120, 120, 140), width=1)
    draw.rectangle([(center_x + 5, center_y + 140), (center_x + 18, center_y + 155)], 
                   fill=(80, 80, 100), outline=(120, 120, 140), width=1)
    
    # Equipment stats panel on right side
    panel_x = 320
    draw.rectangle([(panel_x - 10, 110), (580, 450)], fill=(25, 25, 40), outline=(100, 150, 200), width=2)
    
    # Equipment list with colors
    equip_y = 130
    draw.text((panel_x, equip_y), "⚔️ EQUIPMENT", fill=(255, 215, 0), font=text_font)
    
    equip_y += 50
    # Weapon
    weapon_color = (255, 100, 100) if not equipped.get('weapon') else (100, 255, 100)
    draw.text((panel_x, equip_y), "⚔️ WEAPON:", fill=weapon_color, font=text_font)
    equip_y += 30
    if equipped.get('weapon'):
        draw.text((panel_x + 10, equip_y), equipped['weapon'][:25], fill=(200, 255, 200), font=small_font)
    else:
        draw.text((panel_x + 10, equip_y), "Empty", fill=(150, 100, 100), font=small_font)
    
    equip_y += 40
    # Armor
    armor_color = (255, 100, 100) if not equipped.get('armor') else (100, 150, 255)
    draw.text((panel_x, equip_y), "🛡️ ARMOR:", fill=armor_color, font=text_font)
    equip_y += 30
    if equipped.get('armor'):
        draw.text((panel_x + 10, equip_y), equipped['armor'][:25], fill=(150, 200, 255), font=small_font)
    else:
        draw.text((panel_x + 10, equip_y), "Empty", fill=(150, 100, 100), font=small_font)
    
    equip_y += 40
    # Accessory
    acc_color = (255, 100, 100) if not equipped.get('accessory') else (255, 215, 100)
    draw.text((panel_x, equip_y), "💍 ACCESSORY:", fill=acc_color, font=text_font)
    equip_y += 30
    if equipped.get('accessory'):
        draw.text((panel_x + 10, equip_y), equipped['accessory'][:25], fill=(255, 230, 150), font=small_font)
    else:
        draw.text((panel_x + 10, equip_y), "Empty", fill=(150, 100, 100), font=small_font)
    
    # Power stats at bottom
    draw.rectangle([(50, 460), (550, 490)], fill=(40, 40, 60), outline=(100, 200, 100), width=2)
    draw.text((60, 465), f"⚡ TOTAL POWER: {power:,}", fill=(100, 255, 100), font=text_font)
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


def generate_shop_banner(shop_name: str, item_count: int) -> BytesIO:
    """Generate a shop display banner."""
    img = Image.new('RGB', (SHOP_BANNER_WIDTH, SHOP_BANNER_HEIGHT), color=(30, 30, 50))
    draw = ImageDraw.Draw(img)
    
    title_font, text_font, _ = load_fonts(28, 16)
    
    # Gold gradient header
    draw.rectangle([(0, 0), (500, 60)], fill=(255, 152, 0))
    draw.rectangle([(2, 2), (498, 58)], outline=(255, 255, 255), width=2)
    
    # Shop name
    draw.text((20, 15), f"🏪 {shop_name}", fill=(20, 20, 30), font=title_font)
    
    # Stats
    draw.text((20, 75), f"📦 Items: {item_count}", fill=(200, 200, 200), font=text_font)
    draw.text((20, 105), "✨ High quality items ✨", fill=(150, 200, 255), font=text_font)
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


def generate_category_preview(category: str, item_count: int, cheapest_price: int) -> BytesIO:
    """Generate a category preview card."""
    category_info = {
        "weapon": ("⚔️ Weapons", (255, 100, 100)),
        "consumable": ("🧪 Potions", (100, 200, 100)),
        "armor": ("🛡️ Armor", (100, 150, 255)),
        "accessory": ("💍 Accessories", (255, 200, 100)),
        "material": ("🪨 Materials", (150, 150, 150)),
        "other": ("❔ Other", (200, 100, 200)),
    }
    
    label, color = category_info.get(category, ("❔ Unknown", (128, 128, 128)))
    
    img = Image.new('RGB', (CATEGORY_CARD_WIDTH, CATEGORY_CARD_HEIGHT), color=(25, 25, 40))
    draw = ImageDraw.Draw(img)
    
    title_font, text_font, _ = load_fonts(22, 14)
    
    # Category header with color
    draw.rectangle([(0, 0), (300, 60)], fill=color)
    draw.rectangle([(2, 2), (298, 58)], outline=(255, 255, 255), width=2)
    
    draw.text((15, 15), label, fill=(255, 255, 255), font=title_font)
    
    # Stats
    draw.text((15, 70), f"📊 {item_count} items available", fill=(200, 200, 200), font=text_font)
    draw.text((15, 95), f"💰 From {cheapest_price:,} gold", fill=(255, 215, 0), font=text_font)
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

# ============================================================================
# TOKEN SETUP
# ============================================================================

def get_or_setup_token() -> str:
    """First run: ask for token, save it. Subsequent runs: load from file."""
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text().strip()
        if token:
            print(f"✅ Loaded token from {TOKEN_PATH}")
            return token
    
    print("\n" + "="*60)
    print("🤖 DISCORD BOT - FIRST RUN SETUP")
    print("="*60)
    print("\nPaste your Discord bot token below:")
    print("(Get it from: https://discord.com/developers/applications)")
    print("-"*60)
    
    token = input("Enter your bot token: ").strip()
    
    if not token or len(token) < 20:
        raise SystemExit("❌ Invalid token. Exiting.")
    
    TOKEN_PATH.write_text(token)
    try:
        TOKEN_PATH.chmod(0o600)
    except (OSError, NotImplementedError):
        pass  # Termux may not support chmod; that's fine
    print(f"✅ Token saved to {TOKEN_PATH}")
    print("="*60 + "\n")
    
    return token

def load_config() -> dict:
    """Load or create default config."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    
    config = {
        "prefix": "!",
        "max_guild_members": 50,
        "trade_tax": 0.0227,
        "tax_owner_id": 0,
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    return config

CONFIG = load_config()
TOKEN = get_or_setup_token()

# ============================================================================
# AESTHETIC & CUSTOM LABELS
# ============================================================================

# Customizable labels used in displays
LABEL_CONFIG = {
    "gold": "💰 Gold",
    "level": "⚔️ Level",
    "hp": "💓 HP",
    "mana": "✨ Mana",
    "atk": "⚡ ATK",
    "defense": "🛡️ DEF",
    "crit": "💫 CRIT",
    "prestige": "👑 Prestige",
    "shards": "💠 Astral Shards",
    "kills": "🗡️ Kills",
    "zone": "🌍 Zone",
    "xp": "⭐ XP"
}

def get_label(key: str) -> str:
    return LABEL_CONFIG.get(key, key.title())

def starry_box(text: str) -> str:
    stars = "✧" * 40
    return f"```\n{stars}\n\n{text}\n\n{stars}\n```"

# ============================================================================
# INTENTS & BOT SETUP
# ============================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=CONFIG["prefix"], intents=intents, help_command=None)

db = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL;")
db.execute("PRAGMA synchronous=NORMAL;")
db.execute("PRAGMA foreign_keys=ON;")

db_lock = asyncio.Lock()
dirty_players: set[int] = set()
dirty_fights: set[int] = set()

# ============================================================================
# GAME CONSTANTS
# ============================================================================

CLASSES = {
    "warrior": {"hp": 120, "mana": 30, "atk": 16, "def": 12, "crit": 0.05, "desc": "Balanced fighter"},
    "mage": {"hp": 85, "mana": 75, "atk": 12, "def": 6, "crit": 0.08, "desc": "Burst caster"},
    "rogue": {"hp": 95, "mana": 40, "atk": 14, "def": 8, "crit": 0.16, "desc": "Crit specialist"},
    "paladin": {"hp": 110, "mana": 55, "atk": 13, "def": 14, "crit": 0.06, "desc": "Tank defender"},
    "ranger": {"hp": 100, "mana": 35, "atk": 15, "def": 9, "crit": 0.12, "desc": "Archer"},
    "druid": {"hp": 105, "mana": 65, "atk": 11, "def": 10, "crit": 0.07, "desc": "Healer"},
    # 5 extra obtainable classes
    "berserker": {"hp": 140, "mana": 20, "atk": 20, "def": 8, "crit": 0.10, "desc": "Glass-cannon brute"},
    "knight": {"hp": 150, "mana": 30, "atk": 14, "def": 18, "crit": 0.04, "desc": "Heavy juggernaut"},
    "assassin": {"hp": 90, "mana": 45, "atk": 17, "def": 7, "crit": 0.22, "desc": "Lethal crit-burst"},
    "necromancer": {"hp": 95, "mana": 90, "atk": 15, "def": 7, "crit": 0.09, "desc": "Dark summoner"},
    "monk": {"hp": 115, "mana": 60, "atk": 14, "def": 12, "crit": 0.13, "desc": "Balanced martial artist"},
    # 2 SECRET classes — only unlockable in the Astral Exchange (shards)
    "voidreaper": {"hp": 160, "mana": 80, "atk": 24, "def": 14, "crit": 0.20, "desc": "SECRET — devours the void", "secret": True},
    "celestial": {"hp": 175, "mana": 110, "atk": 22, "def": 18, "crit": 0.15, "desc": "SECRET — ascended being", "secret": True},
}
SECRET_CLASSES = {k for k, v in CLASSES.items() if v.get("secret")}

SHOP_ITEMS = {
    # CONSUMABLES - HEALING
    "potion": {"price": 45, "type": "consumable", "rarity": "common", "heal": 60, "power": 0},
    "hi-potion": {"price": 140, "type": "consumable", "rarity": "rare", "heal": 180, "power": 0},
    "mega-potion": {"price": 350, "type": "consumable", "rarity": "epic", "heal": 400, "power": 0},
    "ultra-potion": {"price": 850, "type": "consumable", "rarity": "legendary", "heal": 800, "power": 0},
    "celestial elixir": {"price": 2500, "type": "consumable", "rarity": "chromatic", "heal": 2000, "power": 0},
    
    # CONSUMABLES - MANA
    "mana potion": {"price": 55, "type": "consumable", "rarity": "common", "heal": 0, "power": 0},
    "mega-mana": {"price": 160, "type": "consumable", "rarity": "rare", "heal": 0, "power": 0},
    "mana surge": {"price": 420, "type": "consumable", "rarity": "epic", "heal": 0, "power": 0},
    "void essence": {"price": 1200, "type": "consumable", "rarity": "legendary", "heal": 0, "power": 0},
    
    # CONSUMABLES - BUFFS
    "scroll of power": {"price": 300, "type": "consumable", "rarity": "uncommon", "heal": 0, "power": 0},
    "elixir of strength": {"price": 500, "type": "consumable", "rarity": "rare", "heal": 0, "power": 0},
    "blessing of gods": {"price": 2000, "type": "consumable", "rarity": "legendary", "heal": 0, "power": 0},
    
    # WEAPONS - BASIC
    "wooden sword": {"price": 50, "type": "weapon", "rarity": "common", "power": 3},
    "iron sword": {"price": 120, "type": "weapon", "rarity": "uncommon", "power": 8},
    "steel sword": {"price": 310, "type": "weapon", "rarity": "rare", "power": 18},
    "diamond sword": {"price": 650, "type": "weapon", "rarity": "epic", "power": 28},
    "legendary blade": {"price": 800, "type": "weapon", "rarity": "epic", "power": 30},
    
    # WEAPONS - MAGICAL
    "apprentice wand": {"price": 100, "type": "weapon", "rarity": "common", "power": 5},
    "mage staff": {"price": 320, "type": "weapon", "rarity": "rare", "power": 16},
    "arcane scepter": {"price": 700, "type": "weapon", "rarity": "epic", "power": 32},
    "void staff": {"price": 950, "type": "weapon", "rarity": "epic", "power": 35},
    "celestial rod": {"price": 3000, "type": "weapon", "rarity": "legendary", "power": 55},
    
    # WEAPONS - SPECIAL
    "shadow dagger": {"price": 200, "type": "weapon", "rarity": "rare", "power": 14},
    "executioner axe": {"price": 900, "type": "weapon", "rarity": "epic", "power": 38},
    "cursed scythe": {"price": 2000, "type": "weapon", "rarity": "legendary", "power": 50},
    "secret scroll": {"price": 3500, "type": "weapon", "rarity": "secret", "power": 60},
    "temporal blade": {"price": 6000, "type": "weapon", "rarity": "chromatic", "atk_bonus": 75000, "hp_bonus": 50000},
    "ak-47": {"price": 0, "type": "weapon", "rarity": "secret", "atk_bonus": 1000000, "hp_bonus": 500000, "admin_only": True},
    
    # ARMOR - BASIC
    "cloth robe": {"price": 80, "type": "armor", "rarity": "common", "power": 3},
    "leather armor": {"price": 150, "type": "armor", "rarity": "uncommon", "power": 6},
    "iron armor": {"price": 300, "type": "armor", "rarity": "uncommon", "power": 12},
    "steel plate": {"price": 500, "type": "armor", "rarity": "rare", "power": 20},
    
    # ARMOR - HEAVY
    "guardian armor": {"price": 420, "type": "armor", "rarity": "epic", "power": 15},
    "dragon scale": {"price": 800, "type": "armor", "rarity": "epic", "power": 26},
    "legendary plate": {"price": 1200, "type": "armor", "rarity": "epic", "power": 25},
    "void armor": {"price": 4500, "type": "armor", "rarity": "secret", "power": 45},
    
    # ARMOR - MAGICAL
    "mystic robe": {"price": 350, "type": "armor", "rarity": "rare", "power": 14},
    "arcane cloak": {"price": 750, "type": "armor", "rarity": "epic", "power": 22},
    "celestial vestments": {"price": 2500, "type": "armor", "rarity": "legendary", "power": 40},
    
    # ACCESSORIES - RINGS
    "ring of defense": {"price": 200, "type": "accessory", "rarity": "uncommon", "power": 4},
    "ring of attack": {"price": 250, "type": "accessory", "rarity": "uncommon", "power": 5},
    "ring of wisdom": {"price": 300, "type": "accessory", "rarity": "rare", "power": 7},
    "ring of power": {"price": 500, "type": "accessory", "rarity": "epic", "power": 12},
    "ring of eternity": {"price": 2000, "type": "accessory", "rarity": "legendary", "power": 28},
    
    # ACCESSORIES - AMULETS
    "amulet of luck": {"price": 260, "type": "accessory", "rarity": "rare", "power": 5},
    "amulet of protection": {"price": 400, "type": "accessory", "rarity": "rare", "power": 9},
    "amulet of fury": {"price": 600, "type": "accessory", "rarity": "epic", "power": 14},
    "amulet of ancients": {"price": 2200, "type": "accessory", "rarity": "legendary", "power": 30},
    
    # ACCESSORIES - SPECIAL
    "chromatic crystal": {"price": 8000, "type": "accessory", "rarity": "chromatic", "power": 90},
    "cosmic gem": {"price": 5000, "type": "accessory", "rarity": "secret", "power": 50},
    "infinity stone": {"price": 10000, "type": "accessory", "rarity": "chromatic", "power": 100},
    
    # ULTRA-ENDGAME WEAPONS (MILLIONS)
    "sword of oblivion": {"price": 50000000, "type": "weapon", "rarity": "chromatic", "power": 500},
    "staff of infinity": {"price": 75000000, "type": "weapon", "rarity": "chromatic", "power": 600},
    "gauntlets of eternity": {"price": 60000000, "type": "weapon", "rarity": "chromatic", "power": 550},
    "abyssal reaper": {"price": 100000000, "type": "weapon", "rarity": "chromatic", "power": 750},
    
    # ULTRA-ENDGAME ARMOR (MILLIONS)
    "armor of legends": {"price": 80000000, "type": "armor", "rarity": "chromatic", "power": 400},
    "celestial titan plate": {"price": 120000000, "type": "armor", "rarity": "chromatic", "power": 500},
    "void sovereign robes": {"price": 100000000, "type": "armor", "rarity": "chromatic", "power": 450},
    
    # ULTRA-ENDGAME ACCESSORIES (MILLIONS)
    "crown of gods": {"price": 150000000, "type": "accessory", "rarity": "chromatic", "power": 600},
    "eternal nexus stone": {"price": 200000000, "type": "accessory", "rarity": "chromatic", "power": 750},
    "omega essence": {"price": 250000000, "type": "accessory", "rarity": "chromatic", "power": 900},
}

# ============================================================================
# MASSIVE ITEM CATALOG  (auto-generated hundreds of items + secret + pvp items)
# These names are deterministic so the persistent economy stays stable.
# ============================================================================

_RARITY_TIERS = {
    "common":    {"power": (2, 9),     "price": (40, 160)},
    "uncommon":  {"power": (8, 20),    "price": (120, 450)},
    "rare":      {"power": (18, 40),   "price": (300, 1400)},
    "epic":      {"power": (35, 80),   "price": (1200, 7000)},
    "legendary": {"power": (70, 150),  "price": (6000, 50000)},
    "mythic":    {"power": (140, 280), "price": (40000, 400000)},
    "secret":    {"power": (250, 480), "price": (250000, 3000000)},
    "chromatic": {"power": (450, 999), "price": (6000000, 600000000)},
}
_RARITY_ORDER = list(_RARITY_TIERS.keys())

_WEAPON_BASES = ["Sword", "Blade", "Axe", "Dagger", "Spear", "Mace", "Bow", "Staff", "Wand",
                 "Scepter", "Katana", "Halberd", "Warhammer", "Glaive", "Scythe", "Rapier",
                 "Claymore", "Trident", "Cleaver", "Lance"]
_ARMOR_BASES = ["Helm", "Plate", "Chestguard", "Greaves", "Gauntlets", "Shield", "Robe",
                "Cloak", "Chainmail", "Vest", "Cuirass", "Pauldrons", "Bracers", "Tunic"]
_ACCESSORY_BASES = ["Ring", "Amulet", "Pendant", "Charm", "Talisman", "Band", "Locket",
                    "Sigil", "Relic", "Idol", "Brooch", "Circlet"]
_PREFIXES = ["Rusty", "Sturdy", "Fine", "Sharp", "Gleaming", "Runed", "Blessed", "Cursed",
             "Ancient", "Draconic", "Astral", "Void", "Infernal", "Frost", "Storm", "Radiant",
             "Shadow", "Eternal", "Primordial", "Celestial", "Abyssal", "Molten", "Verdant",
             "Spectral", "Obsidian", "Crystalline", "Golden", "Phantom", "Savage", "Hallowed"]


def _lerp_int(lo: int, hi: int, frac: float) -> int:
    return int(lo + (hi - lo) * max(0.0, min(1.0, frac)))


def _generate_catalog() -> Dict[str, Dict]:
    items = {}
    type_bases = [("weapon", _WEAPON_BASES), ("armor", _ARMOR_BASES), ("accessory", _ACCESSORY_BASES)]
    for r_idx, rarity in enumerate(_RARITY_ORDER):
        tier = _RARITY_TIERS[rarity]
        prefixes = _PREFIXES[r_idx::len(_RARITY_ORDER)]
        for itype, bases in type_bases:
            n = len(bases)
            for b_idx, base in enumerate(bases):
                for p_idx, prefix in enumerate(prefixes):
                    name = f"{prefix} {base}".lower()
                    if name in items or name in SHOP_ITEMS:
                        continue
                    frac = (b_idx + (p_idx / max(1, len(prefixes)))) / max(1, n)
                    items[name] = {
                        "price": _lerp_int(tier["price"][0], tier["price"][1], frac),
                        "type": itype,
                        "rarity": rarity,
                        "power": _lerp_int(tier["power"][0], tier["power"][1], frac),
                    }
    return items


SECRET_ITEMS = {
    "whisper of the void": {"price": 4500000, "type": "weapon", "rarity": "secret", "power": 420, "secret": True},
    "heart of a dead star": {"price": 9000000, "type": "accessory", "rarity": "secret", "power": 480, "secret": True},
    "blade of forgotten kings": {"price": 6500000, "type": "weapon", "rarity": "secret", "power": 460, "secret": True},
    "mask of the faceless god": {"price": 7200000, "type": "armor", "rarity": "secret", "power": 440, "secret": True},
    "the last ember": {"price": 12000000, "type": "weapon", "rarity": "chromatic", "power": 700, "secret": True},
    "crown of the nameless": {"price": 20000000, "type": "accessory", "rarity": "chromatic", "power": 820, "secret": True},
    "fragment of creation": {"price": 50000000, "type": "accessory", "rarity": "chromatic", "power": 950, "secret": True},
    "glitched blade": {"price": 7777777, "type": "weapon", "rarity": "secret", "power": 333, "secret": True},
    "shard of eternity": {"price": 8888888, "type": "armor", "rarity": "secret", "power": 410, "secret": True},
    "404 not found": {"price": 1, "type": "accessory", "rarity": "secret", "power": 404, "secret": True},
    "null pointer": {"price": 99999999, "type": "weapon", "rarity": "chromatic", "power": 999, "secret": True},
    "devs lost coffee": {"price": 13371337, "type": "accessory", "rarity": "secret", "power": 365, "secret": True},
}

PVP_ITEMS = {
    "gladiators edge": {"price": 25000, "type": "weapon", "rarity": "epic", "power": 60, "pvp": True, "pvp_power": 40},
    "duelists rapier": {"price": 40000, "type": "weapon", "rarity": "epic", "power": 70, "pvp": True, "pvp_power": 55},
    "arena crown": {"price": 75000, "type": "accessory", "rarity": "legendary", "power": 80, "pvp": True, "pvp_power": 70},
    "champions plate": {"price": 90000, "type": "armor", "rarity": "legendary", "power": 110, "pvp": True, "pvp_power": 65},
    "warlords banner": {"price": 150000, "type": "accessory", "rarity": "legendary", "power": 120, "pvp": True, "pvp_power": 100},
    "bloodthirster": {"price": 300000, "type": "weapon", "rarity": "mythic", "power": 200, "pvp": True, "pvp_power": 160},
    "nemesis guard": {"price": 350000, "type": "armor", "rarity": "mythic", "power": 220, "pvp": True, "pvp_power": 150},
    "kingslayer": {"price": 1000000, "type": "weapon", "rarity": "secret", "power": 380, "pvp": True, "pvp_power": 300},
}

SHOP_ITEMS.update(_generate_catalog())
SHOP_ITEMS.update(SECRET_ITEMS)
SHOP_ITEMS.update(PVP_ITEMS)

ITEMS_BY_RARITY = {}
for _nm, _d in SHOP_ITEMS.items():
    if _d.get("type") in ("weapon", "armor", "accessory"):
        ITEMS_BY_RARITY.setdefault(_d["rarity"], []).append(_nm)


def _stable_hash(s) -> int:
    h = 2166136261
    for c in str(s):
        h = (h * 16777619 + ord(c)) & 0xFFFFFFFF
    return h


def price_window() -> int:
    return int(time.time() // 3600)


def dynamic_price(item_name: str) -> int:
    base = SHOP_ITEMS.get(item_name, {}).get("price", 100)
    seed = _stable_hash(f"{item_name}:{price_window()}")
    factor = 0.75 + (seed % 1000) / 1000.0 * 0.6
    return max(1, int(base * factor))


def daily_merchant_stock(count: int = 10) -> list:
    day = int(time.time() // 86400)
    names = sorted(
        n for n, d in SHOP_ITEMS.items()
        if not d.get("secret") and not d.get("pvp")
        and 0 < d.get("price", 0) <= 2000000
        and d.get("type") in ("weapon", "armor", "accessory", "consumable")
    )
    if not names:
        return []
    stock = []
    i = 0
    while len(stock) < count and i < count * 6:
        nm = names[_stable_hash(f"{day}:{i}") % len(names)]
        if nm not in stock:
            stock.append(nm)
        i += 1
    return stock


def random_item_by_rarity(rarity: str) -> Optional[str]:
    pool = ITEMS_BY_RARITY.get(rarity)
    return random.choice(pool) if pool else None


LOOTBOXES = {
    "wood": {"price": 150, "tier": 1},
    "copper": {"price": 300, "tier": 1.5},
    "iron": {"price": 450, "tier": 2},
    "silver": {"price": 750, "tier": 2.5},
    "gold": {"price": 1200, "tier": 3},
    "platinum": {"price": 2500, "tier": 3.5},
    "mythic": {"price": 5000, "tier": 4},
    "eternal": {"price": 8000, "tier": 4.5},
    "legendary": {"price": 12000, "tier": 5},
    "chromatic": {"price": 25000, "tier": 6},
}

ZONES = {
    "meadows": {"min_level": 1, "enemy": ["Slime", "Rat", "Wild Boar"], "loot_bonus": 1.0},
    "forest": {"min_level": 3, "enemy": ["Goblin", "Wolf", "Bandit"], "loot_bonus": 1.1},
    "caves": {"min_level": 8, "enemy": ["Cave Bat", "Stone Golem", "Spider"], "loot_bonus": 1.2},
    "desert": {"min_level": 15, "enemy": ["Sand Raider", "Scorpion", "Wraith"], "loot_bonus": 1.35},
    "volcano": {"min_level": 25, "enemy": ["Lava Imp", "Magma Beast", "Dragon"], "loot_bonus": 1.5},
    "void": {"min_level": 50, "enemy": ["Void Shade", "Warped Knight", "Serpent"], "loot_bonus": 1.8},
    "celestial": {"min_level": 75, "enemy": ["Celestial Guardian", "Star Wraith", "Leviathan"], "loot_bonus": 2.0},
    "abyss": {"min_level": 100, "enemy": ["Abyssal Horror", "Chaos Titan", "Destroyer"], "loot_bonus": 2.3},
    "eternal realm": {"min_level": 150, "enemy": ["Eternal Sentinel", "Void King", "Primordial Beast"], "loot_bonus": 2.8},
    "shadow nexus": {"min_level": 200, "enemy": ["Shadow Lord", "Dimensional Rift", "Oblivion"], "loot_bonus": 3.2},
}

BOSSES = {
    "forest_guardian": {"name": "Forest Guardian", "level": 20, "hp": 500, "atk": 25, "def": 15, "xp": 5000, "gold": 2000, "min_level": 15},
    "volcano_lord": {"name": "Volcano Lord", "level": 40, "hp": 1000, "atk": 40, "def": 20, "xp": 15000, "gold": 5000, "min_level": 35},
    "void_king": {"name": "Void King", "level": 60, "hp": 2000, "atk": 60, "def": 30, "xp": 30000, "gold": 10000, "min_level": 55},
    "celestial_titan": {"name": "Celestial Titan", "level": 100, "hp": 5000, "atk": 80, "def": 50, "xp": 100000, "gold": 50000, "min_level": 90},
    "shadow_overlord": {"name": "Shadow Overlord", "level": 150, "hp": 8000, "atk": 120, "def": 70, "xp": 250000, "gold": 100000, "min_level": 140},
    "eternal_warden": {"name": "Eternal Warden", "level": 200, "hp": 12000, "atk": 160, "def": 100, "xp": 500000, "gold": 250000, "min_level": 190},
    "primordial_chaos": {"name": "Primordial Chaos", "level": 250, "hp": 20000, "atk": 220, "def": 140, "xp": 1000000, "gold": 500000, "min_level": 240},
    "god_of_oblivion": {"name": "God of Oblivion", "level": 300, "hp": 30000, "atk": 300, "def": 180, "xp": 2000000, "gold": 1000000, "min_level": 290},
}

CRAFTING_RECIPES = {
    # BASIC WEAPONS
    "iron sword": {"materials": [("iron ore", 3), ("copper ore", 2)], "xp": 500, "level": 5},
    "steel sword": {"materials": [("iron ore", 5), ("silver bar", 3)], "xp": 1000, "level": 15},
    "diamond sword": {"materials": [("diamond", 4), ("silver bar", 5)], "xp": 2000, "level": 30},
    "shadow dagger": {"materials": [("void shard", 3), ("obsidian", 2)], "xp": 1500, "level": 25},
    
    # MAGIC WEAPONS
    "mage robe": {"materials": [("cloth", 4), ("crystal", 2)], "xp": 800, "level": 10},
    "arcane scepter": {"materials": [("crystal", 5), ("silver bar", 4)], "xp": 1800, "level": 22},
    "void staff": {"materials": [("void shard", 6), ("mana stone", 5)], "xp": 3500, "level": 40},
    "celestial rod": {"materials": [("celestial fragment", 8), ("godly essence", 4)], "xp": 5000, "level": 60},
    
    # ARMOR
    "leather armor": {"materials": [("leather", 5), ("iron ore", 2)], "xp": 600, "level": 8},
    "steel plate": {"materials": [("steel bar", 4), ("iron ore", 3)], "xp": 1200, "level": 18},
    "dragon scale": {"materials": [("dragon scale", 8), ("silver bar", 5)], "xp": 3000, "level": 45},
    "void armor": {"materials": [("void shard", 10), ("mythic core", 3)], "xp": 6000, "level": 70},
    
    # ACCESSORIES
    "ring of wisdom": {"materials": [("gold bar", 3), ("crystal", 2)], "xp": 700, "level": 12},
    "ring of power": {"materials": [("gold bar", 5), ("mana stone", 4)], "xp": 2000, "level": 35},
    "amulet of protection": {"materials": [("silver bar", 4), ("crystal", 3)], "xp": 1200, "level": 20},
    "ring of eternity": {"materials": [("godly essence", 5), ("celestial fragment", 6)], "xp": 7000, "level": 80},
    
    # LEGENDARY
    "legendary blade": {"materials": [("mythic core", 2), ("godly essence", 3)], "xp": 5000, "level": 50},
    "legendary armor": {"materials": [("mythic core", 2), ("godly essence", 3)], "xp": 5000, "level": 50},
    "infinity stone": {"materials": [("void shard", 15), ("godly essence", 10), ("celestial fragment", 10)], "xp": 15000, "level": 100},
    "temporal blade": {"materials": [("temporal essence", 8), ("void shard", 10), ("celestial fragment", 8)], "xp": 10000, "level": 90},
}

PETS = {
    "wolf": {"name": "Wolf", "atk_bonus": 5, "def_bonus": 2, "cost": 1000},

    "phoenix": {"name": "Phoenix", "atk_bonus": 12, "def_bonus": 8, "cost": 8000},
    "sphinx": {"name": "Sphinx", "atk_bonus": 18, "def_bonus": 12, "cost": 15000},
    "gryphon": {"name": "Gryphon", "atk_bonus": 14, "def_bonus": 11, "cost": 9500},
    "basilisk": {"name": "Basilisk", "atk_bonus": 16, "def_bonus": 9, "cost": 11000},
    "leviathan": {"name": "Leviathan", "atk_bonus": 20, "def_bonus": 15, "cost": 20000},
    "cerberus": {"name": "Cerberus", "atk_bonus": 17, "def_bonus": 13, "cost": 12000},
    "unicorn": {"name": "Unicorn", "atk_bonus": 10, "def_bonus": 14, "cost": 7000},
    "chimera": {"name": "Chimera", "atk_bonus": 19, "def_bonus": 14, "cost": 18000},
    "wraith": {"name": "Wraith", "atk_bonus": 22, "def_bonus": 8, "cost": 16000},
    "void serpent": {"name": "Void Serpent", "atk_bonus": 25, "def_bonus": 10, "cost": 25000},
}

# WORLDS: gated channels everyone can SEE but only role-holders can ENTER (send).
# Requirements escalate hard (level + prestige + rebirth) so the top worlds take ages.
WORLDS = [
    {"key": "meadows",   "name": "🌿 Meadows",         "role": "🌿 Meadow Wanderer",     "level": 1,   "prestige": 0, "rebirth": 0},
    {"key": "forest",    "name": "🌲 Forest",          "role": "🌲 Forest Walker",       "level": 5,   "prestige": 0, "rebirth": 0},
    {"key": "caves",     "name": "🕳️ Caves",           "role": "🕳️ Cave Delver",        "level": 15,  "prestige": 0, "rebirth": 0},
    {"key": "desert",    "name": "🏜️ Desert",          "role": "🏜️ Desert Nomad",       "level": 30,  "prestige": 0, "rebirth": 0},
    {"key": "volcano",   "name": "🌋 Volcano",         "role": "🌋 Volcano Conqueror",   "level": 50,  "prestige": 0, "rebirth": 0},
    {"key": "void",      "name": "🌀 The Void",        "role": "🌀 Void Touched",        "level": 80,  "prestige": 1, "rebirth": 0},
    {"key": "celestial", "name": "✨ Celestial Plane", "role": "✨ Celestial Ascendant", "level": 120, "prestige": 2, "rebirth": 0},
    {"key": "abyss",     "name": "🕋 The Abyss",       "role": "🕋 Abyss Lord",          "level": 160, "prestige": 3, "rebirth": 1},
    {"key": "eternal",   "name": "♾️ Eternal Realm",   "role": "♾️ Eternal Sovereign",   "level": 220, "prestige": 5, "rebirth": 2},
    {"key": "shadow",    "name": "🌑 Shadow Nexus",    "role": "🌑 Shadow God",          "level": 300, "prestige": 8, "rebirth": 3},
    {"key": "titan",     "name": "🗿 Titan Bastion",    "role": "🗿 Titan Breaker",       "level": 450, "prestige": 12, "rebirth": 4},
    {"key": "cosmos",    "name": "🌌 Cosmic Expanse",   "role": "🌌 Cosmic Overlord",     "level": 650, "prestige": 18, "rebirth": 6},
    {"key": "genesis",   "name": "🌟 Genesis Core",     "role": "🌟 Genesis Architect",   "level": 900, "prestige": 25, "rebirth": 8},
    {"key": "omega",     "name": "🔺 Omega Singularity", "role": "🔺 Omega Ascendant",     "level": 1500, "prestige": 40, "rebirth": 12},
]

# ENCHANTING: escalating cost + falling success chance. Maxing every item takes a very long time.
ENCHANT_MAX = 20
ENCHANT_BASE_COST = 500
ENCHANT_GROWTH = 1.7

# Distinct hoisted colors for each world role (index-matched to WORLDS).
WORLD_COLORS = [
    0x8BC34A, 0x2E7D32, 0x6D4C41, 0xF9A825, 0xE64A19,
    0x7E57C2, 0x29B6F6, 0x455A64, 0x00BCD4, 0x212121,
]

# ============================================================================
# STAFF (ADMIN / OWNER) + EVENTS CONFIG
# ============================================================================

ADMIN_ROLE_NAME = "ADMIN"
OWNER_ROLE_NAME = "OWNER"
ADMIN_ROLE_COLOR = 0xFF0000   # red
OWNER_ROLE_COLOR = 0xFFD700   # gold

ADMIN_CHANNEL_NAME = "🛡️-admin"
EVENTS_CHANNEL_NAME = "🎉-events"
PLANNING_CHANNEL_NAME = "🗓️-planning"
UPDATE_CHANNEL_NAME = "🔄-update-control"

# Server-wide events that staff can trigger / schedule. field drives which multiplier it boosts.
EVENT_TYPES = {
    "luck2":   {"name": "2× Luck",        "field": "luck",  "mult": 2.0, "emoji": "🍀"},
    "luck3":   {"name": "3× Luck",        "field": "luck",  "mult": 3.0, "emoji": "🍀"},
    "xp2":     {"name": "2× XP",          "field": "xp",    "mult": 2.0, "emoji": "⭐"},
    "xp3":     {"name": "3× XP",          "field": "xp",    "mult": 3.0, "emoji": "⭐"},
    "xp5":     {"name": "5× XP (rare!)",  "field": "xp",    "mult": 5.0, "emoji": "🌟"},
    "gold2":   {"name": "2× Gold",        "field": "gold",  "mult": 2.0, "emoji": "💰"},
    "gold3":   {"name": "3× Gold",        "field": "gold",  "mult": 3.0, "emoji": "💰"},
    "drops2":  {"name": "2× Drops",       "field": "drops", "mult": 2.0, "emoji": "🎁"},
    "drops3":  {"name": "3× Drops",       "field": "drops", "mult": 3.0, "emoji": "🎁"},
    "double":  {"name": "2× Everything",  "field": "all",   "mult": 2.0, "emoji": "🌈"},
    "triple":  {"name": "3× Everything",  "field": "all",   "mult": 3.0, "emoji": "💫"},
    "weekend": {"name": "Weekend Madness (2× XP+Gold)", "field": "xpgold", "mult": 2.0, "emoji": "🎉"},
}

EVENT_DURATIONS = {
    "10 minutes": 600, "30 minutes": 1800, "1 hour": 3600, "3 hours": 10800,
    "6 hours": 21600, "12 hours": 43200, "1 day": 86400, "3 days": 259200,
}

PLAN_DELAYS = {
    "in 10 minutes": 600, "in 30 minutes": 1800, "in 1 hour": 3600, "in 2 hours": 7200,
    "in 6 hours": 21600, "in 12 hours": 43200, "in 1 day": 86400, "in 2 days": 172800,
}

# ============================================================================
# AESTHETICS: dark-matter theme, per-item emojis, enchant tiers, fuzzy keywords
# ============================================================================

THEME_COLOR = 0x0B0B14          # near-black "dark matter"
THEME_PNG_PATH = BOT_DIR / "darkmatter.png"

# Per-item display emojis so every item looks unique. Falls back to rarity emoji.
ITEM_EMOJIS = {
    "potion": "🧪", "hi-potion": "🧴", "mega-potion": "⚗️", "ultra-potion": "🍶", "celestial elixir": "🌟",
    "iron sword": "🗡️", "steel sword": "⚔️", "flame blade": "🔥", "frost blade": "❄️", "void blade": "🌀",
    "excalibur": "🗡️", "dragon slayer": "🐉", "soul reaper": "💀", "thunder spear": "⚡", "shadow dagger": "🌑",
    "wooden bow": "🏹", "longbow": "🏹", "phoenix bow": "🔥", "leather armor": "🦺", "iron armor": "🛡️",
    "steel armor": "🛡️", "dragon armor": "🐲", "void armor": "🌌", "celestial plate": "✨",
    "ring of power": "💍", "amulet of wisdom": "📿", "crown of kings": "👑", "cloak of shadows": "🧥",
    "iron ore": "🪨", "copper ore": "🟤", "silver ore": "⚪", "mithril ore": "🔹", "void ore": "🟣",
    "herbs": "🌿", "cloth": "🧵", "leather": "🟫", "silver bar": "🪙", "ancient coin": "🟡", "wolf fang": "🦷",
    "void shard": "🔮", "crystal": "💎", "dragon scale": "🐉", "mana stone": "🔵", "mythic core": "☄️",
    "godly essence": "🌟", "elder rune": "ᚱ", "celestial fragment": "✨", "void crystal": "🟪",
    "legendary essence": "🌠", "ancient tome": "📜", "ancient rune": "🗿",
    "common fish": "🐟", "golden fish": "🟡", "void fish": "🌀", "legendary leviathan": "🐋",
}

# Enchant tiers — each ✦ band gets a name + glow so high enchants look insane.
ENCHANT_TIERS = [
    (0, "", ""),
    (1, "Honed", "✦"), (3, "Glowing", "✨"), (6, "Radiant", "🌟"),
    (10, "Blazing", "🔥"), (14, "Celestial", "💫"), (18, "Godforged", "🌌"), (20, "TRANSCENDENT", "♾️"),
]

# Canonical command keywords used for fuzzy misspelling correction.
COMMAND_KEYWORDS = {
    "attack", "fight", "hunt", "strike", "status", "stats", "profile", "inventory", "items",
    "equip", "shop", "buy", "sell", "market", "guild", "world", "worlds", "dungeon", "boss",
    "team", "lobby", "pvp", "duel", "zone", "explore", "leaderboard", "quest", "daily", "pet",
    "rebirth", "prestige", "craft", "enchant", "upgrade", "gamble", "fish", "mine", "bounty",
    "alchemy", "lootbox", "menu", "help", "private", "heal", "bank", "trade", "join", "create",
    "leave", "list", "setup",
}
COMMAND_KEYWORDS |= {"merge", "offer", "accept", "decline", "cancel", "currency", "astralshop", "shards", "config", "settings", "apply", "class", "classes"}

# ============================================================================
# CURRENCY (Astral Shards), endgame gear, custom 7-tier enchants, big potion list
# ============================================================================

CURRENCY_NAME = "Astral Shards"
CURRENCY_EMOJI = "💠"
LAST_ZONE = "shadow nexus"   # only here (and future areas) do shards drop


def _generate_potions() -> Dict[str, Dict]:
    elements = [
        ("Health", "heal"), ("Greater Health", "heal"), ("Mana", "mana"), ("Strength", "atk"),
        ("Defense", "def"), ("Luck", "luck"), ("Swiftness", "spd"), ("Fire Resist", "def"),
        ("Frost Resist", "def"), ("Void Resist", "def"), ("Holy", "heal"), ("Regeneration", "heal"),
        ("Giant", "atk"), ("Berserker", "atk"), ("Vitality", "heal"), ("Focus", "mana"),
        ("Fortune", "luck"), ("Iron Skin", "def"), ("Phoenix", "heal"), ("Shadow", "atk"),
    ]
    grades = [
        ("Minor", "common", 1), ("Lesser", "common", 2), ("", "uncommon", 3), ("Greater", "uncommon", 4),
        ("Major", "rare", 6), ("Superior", "rare", 8), ("Grand", "epic", 11), ("Supreme", "epic", 15),
        ("Mythic", "mythic", 22),
    ]
    out = {}
    for el_name, stat in elements:
        for prefix, rarity, mag in grades:
            label = f"{prefix} {el_name} Potion".strip()
            name = label.lower()
            if name in SHOP_ITEMS or name in out:
                continue
            out[name] = {
                "price": 40 * mag + 30,
                "type": "consumable",
                "rarity": rarity,
                "heal": mag * 25 if stat == "heal" else 0,
                "power": 0,
                "boost": stat,
                "boost_amt": mag,
            }
    return out


EXTRA_CONSUMABLES = _generate_potions()
SHOP_ITEMS.update(EXTRA_CONSUMABLES)

# Endgame gear bought ONLY with Astral Shards (magma + void sets).
CURRENCY_GEAR = {
    "magma helmet":     {"type": "armor",     "rarity": "mythic", "power": 180, "shards": 120, "price": 0},
    "magma chestplate": {"type": "armor",     "rarity": "mythic", "power": 260, "shards": 200, "price": 0},
    "magma pants":      {"type": "armor",     "rarity": "mythic", "power": 210, "shards": 160, "price": 0},
    "magma boots":      {"type": "armor",     "rarity": "mythic", "power": 150, "shards": 110, "price": 0},
    "void helmet":      {"type": "armor",     "rarity": "secret", "power": 320, "shards": 320, "price": 0},
    "void chestplate":  {"type": "armor",     "rarity": "secret", "power": 460, "shards": 500, "price": 0},
    "void pants":       {"type": "armor",     "rarity": "secret", "power": 380, "shards": 420, "price": 0},
    "void boots":       {"type": "armor",     "rarity": "secret", "power": 300, "shards": 300, "price": 0},
}
SHOP_ITEMS.update(CURRENCY_GEAR)

# Buyable cosmetic roles (Astral Shards). name -> (cost, hex color)
CURRENCY_ROLES = {
    "💠 Shard Initiate":   (50,   0x80DEEA),
    "💠 Shard Adept":      (120,  0x4DD0E1),
    "💠 Shard Knight":     (250,  0x26C6DA),
    "🌋 Magma Lord":       (400,  0xE64A19),
    "🌌 Void Walker":      (600,  0x7E57C2),
    "⚡ Storm Bringer":     (800,  0xFFCA28),
    "👑 Astral Noble":     (1200, 0xFFD700),
    "🐉 Dragon Sovereign": (2000, 0xD32F2F),
    "♾️ Eternal One":      (3500, 0x00BCD4),
    "🌑 Shadow Deity":     (6000, 0x212121),
}

# Custom enchant families — 7 tiers each, merge 2×T(n) -> 1×T(n+1).
ENCHANT_FAMILIES = [
    "Inferno Protection", "Frost Ward", "Storm Aegis", "Void Barrier",
    "Radiant Shield", "Earthen Guard", "Phantom Veil",
]
ENCHANT_TIER_MAX = 7

# Secret classes unlockable only via the Astral Exchange (shard cost).
CURRENCY_CLASS_UNLOCKS = {"voidreaper": 800, "celestial": 1500}

# ============================================================================
# PROFILE CONFIG: name-color titles, updates opt-in, per-user settings
# ============================================================================

PROFILE_CHANNEL_NAME = "🪪-profile-config"
UPDATES_ROLE_NAME = "🔔 Updates"

# Selectable name titles: a colored role + a [TAG] nickname prefix.
TITLES = {
    "shadow":  {"name": "Shadow",  "tag": "SHADOW",  "color": 0x2C2C2C},
    "inferno": {"name": "Inferno", "tag": "INFERNO", "color": 0xE53935},
    "frost":   {"name": "Frost",   "tag": "FROST",   "color": 0x4FC3F7},
    "void":    {"name": "Void",    "tag": "VOID",    "color": 0x7E57C2},
    "holy":    {"name": "Holy",    "tag": "HOLY",    "color": 0xFFD700},
    "storm":   {"name": "Storm",   "tag": "STORM",   "color": 0xFFCA28},
    "toxic":   {"name": "Toxic",   "tag": "TOXIC",   "color": 0x7CB342},
    "blood":   {"name": "Blood",   "tag": "BLOOD",   "color": 0x8E0000},
    "royal":   {"name": "Royal",   "tag": "ROYAL",   "color": 0x3F51B5},
    "ghost":   {"name": "Ghost",   "tag": "GHOST",   "color": 0xB0BEC5},
}
TITLE_ROLE_NAMES = {f"✦ {t['name']}" for t in TITLES.values()}

# ============================================================================
# INFO CHANNELS: announcements, changelog, guide
# ============================================================================

BOT_VERSION = "v2.1"
ANNOUNCE_CHANNEL_NAME = "📢-announcements"
CHANGELOG_CHANNEL_NAME = "📜-changelog"
GUIDE_CHANNEL_NAME = "📖-guide"
# Channels where the RPG engine stays silent (read-only / chat-only)
NONRPG_CHANNELS = {"announcements", "changelog", "guide", "chat"}

# Newest first. Future updates: append a new dict at the TOP.
CHANGELOG = [
    {
        "v": "v2.1",
        "title": "🏪 THE MERCHANT REVOLUTION 🏪",
        "added": [
            "🏪 **Player Shop System:** Create personal vendor stalls with `playershop setup` to sell items to other players.",
            "🎯 **Smart Category Browsing:** Browse all player shops by category (⚔️ Weapons, 🧪 Potions, 🛡️ Armor, 💍 Accessories, 🪨 Materials, ❔ Other).",
            "💰 **Dynamic Price Sorting:** All items automatically sorted by LOWEST PRICE FIRST — find the best deals instantly!",
            "📊 **Shop Inventory Management:** Stock your shop with `playershop stock` — add up to 5 item types per batch.",
            "🎨 **Beautiful Item Cards (Pillow):** Every purchase displays a professionally rendered item card showing rarity, stats, price, and seller.",
            "🖼️ **Shop Banners & Previews:** Category previews with gorgeous PNG banners showing item count and cheapest prices.",
            "👥 **Player-to-Player Trading:** Direct purchases fund seller gold accounts — earn passive income by stocking your shop!",
            "🔄 **Instant Inventory Updates:** Bought items instantly appear in your inventory; sold items vanish from display.",
            "📱 **Interactive Shop UI:** Tap category buttons → see all items in that category → dropdown select to buy with one click.",
            "✨ **Rarity-Coded Visuals:** Item cards color-coded by rarity (Common gray → Chromatic cyan) with premium gradients.",
            "🎁 **Shop Discovery:** List all active player shops with item counts and seller info (`playershop list`).",
        ],
        "upgraded": [
            "🎨 **Visual Overhaul:** Integrated Pillow library for dynamic PNG image generation throughout the shop system.",
            "🏪 **Marketplace Enhancement:** Player shops complement the existing marketplace — two parallel trading systems now.",
            "💳 **Transaction System:** Streamlined gold transfer — sellers instantly receive payment, buyers instantly get items.",
            "📦 **Shop Persistence:** Shops remain active until manually closed; inventory persists across sessions.",
            "🌈 **Color Gradients:** All item cards use rarity-specific color schemes (fire orange for legendary, pink for secret, cyan for chromatic).",
            "📸 **Image Caching:** Pillow images generated on-demand and efficiently streamed as Discord attachments.",
        ],
        "fixed": [
            "🐛 **Shop Inventory Schema:** Added `item_type` and `rarity` columns to shop_inventory table for proper filtering.",
            "🔧 **Database Timestamps:** Player shops now properly track `created_at` and shop inventory tracks `listed_at`.",
            "⚙️ **Button Callback Logic:** Fixed category button interactions to properly fetch and display items without freezing.",
            "🎯 **Price Sorting:** Implemented proper ORDER BY price ASC in queries to ensure cheapest items appear first.",
            "✅ **Purchase Validation:** Added full player existence checks, gold validation, and proper error messages.",
        ],
        "backend": [
            "💾 **New Tables:** `player_shops` (shop_id, user_id, shop_name, active, created_at) and `shop_inventory` (item_id, shop_id, item_name, item_type, rarity, qty, price, listed_at).",
            "🎨 **Image Generation Functions:** Added `generate_item_card()`, `generate_shop_banner()`, and `generate_category_preview()` using Pillow.",
            "📱 **UI Classes:** `PlayerShopMainView`, `PlayerShopCategoryButton`, `PlayerShopItemSelectView`, `PlayerShopItemSelect`.",
            "🔌 **Import Updates:** Added `from PIL import Image, ImageDraw, ImageFont` and `from io import BytesIO` for image handling.",
            "🗄️ **Database Schema:** All shop queries optimized with proper JOINs and filtering by `item_type`.",
        ],
        "stats": [
            "📈 **Brand New Economy Layer:** Player-to-player transactions create dynamic pricing based on supply/demand.",
            "💎 **Items in Circulation:** First time players can sell items without waiting for drops — bootstrap the economy!",
            "🎯 **User Engagement:** Shop management (stocking, pricing) adds 'producer' role alongside traditional 'consumer' gameplay.",
            "💰 **Gold Sink & Faucet:** Items move between players, encouraging repeated marketplace visits and discoveries.",
        ],
    },
    {
        "v": "v2.0",
        "title": "⚔️ THE EVOLUTION UPDATE ⚔️",
        "added": [
            "👹 **Mega Boss World Event:** 20M HP Arena Boss spawning every 3 minutes.",
            "🏰 **Guild Diplomacy & Pacts:** Formal treaties (Peace/Alliance/Tribute) with automated hourly gold treasury deductions.",
            "🤝 **Guild Treasury Heist:** War winners now automatically steal 10% of the losing guild's treasury.",
            "🎟️ **Guild Promotion Ticketing:** Persistent 🎫-ticketing channel for negotiating @everyone guild broadcasts.",
            "⚙️ **V2.0 Command System:** New strict, exact-match command parsing for absolute reliability.",
            "💠 **RNG Crafting Engine:** Rare Celestial Crystal drops (0.02% base) required to forge Chromatic gear.",
            "🔫 **Secret Staff Arsenal:** Added the staff-only AK-47 weapon with custom combat flavor text and massive scaling.",
            "🎨 **Visual Drop Engine:** Rarity color gradients, animated slot-machine lootbox reveals, full item **cards**, and power-rank badges (🥉 Bronze → ⚡ Godslayer).",
            "🔥 **Elemental Gear:** 10 elements (Fire/Ice/Thunder/Nature/Water/Shadow/Light/Void/Arcane/Blood) imbue gear with damage-type matchups (super-effective ×1.5).",
            "💠 **Gems & Sockets:** Gear rolls sockets; buy gems with Stardust and `socket`/`infuse` them for permanent stat boosts (Ruby/Sapphire/Emerald/Diamond/Onyx/Topaz/Opal).",
            "🔗 **Item Sets:** Dragonlord, Voidwalker & Celestial sets grant escalating bonuses for equipping multiple matching pieces.",
            "🛠️ **Reforge & Salvage:** Reroll an item's stats for gold, or salvage unwanted gear into ✨ Stardust.",
            "🔍 **Inspect & Compare:** `inspect <item>` shows a full card; `compare <item>` shows side-by-side stat deltas vs your equipped gear (🔺/🔻).",
            "🎲 **Drop Odds Transparency:** `odds` command shows your live, luck-scaled rarity chances.",
            "🎰 **Gamble & Fortune Wheel:** Risk gold on `gamble`, or take a free daily `spin` on the fortune wheel.",
            "📖 **Loot Codex:** Tracks the rarities and gear you've discovered.",
            "🍀 **Luck Scaling:** Level, crit and equipped power now push your rarity odds higher — no more flat drop rates.",
            "👑 **Multi-Phase Elemental Bosses:** Bosses now enter **Awakened → Enraged → Final Form** at HP thresholds, hitting up to ×1.9 harder and announcing each phase.",
            "🔥 **Combat Elements:** Every enemy has an element; your weapon's element triggers **super-effective (×1.5)** or **resisted (×0.75)** hits with on-screen tags.",
            "✨ **Class Skills (auto-cast):** Each class auto-fires its signature ability when mana fills — Arcane Nova, Backstab, Holy Light, Bloodrage, Bulwark, Judgment and more (damage/heal/shield/execute/lifesteal)."
        ],
        "upgraded": [
            "📦 **Drop-Only Lootboxes:** Lootboxes are now exclusively obtained via combat drops; shop access disabled.",
            "🏪 **Marketplace UI:** Modern 2x3 grid button navigation with category-based filtering.",
            "✨ **Starry Aesthetic:** Implemented starry-box UI for Status and Character creation.",
            "📊 **Stat System:** Shifted to multi-stat gear (HP/ATK/DEF) with million-scale power potential.",
            "🎲 **Multi-Stat Roll Engine:** Every drop now rolls full HP/ATK/DEF/CRIT with prefix/suffix **affixes**, a quality roll (★ stars) and item-level scaling — true ARPG gear.",
            "⚔️ **Combat Now Uses Your Gear:** Equipped weapon/armor/accessory ATK/DEF/HP **and** active set bonuses now actually apply in fights (previously cosmetic).",
            "❤️ **Fancy Bars & Numbers:** Gradient XP bars, color-shifting HP hearts (💚→💛→❤️), and compact K/M/B number formatting everywhere.",
            "🪪 **Profile Glow-Up:** Shows effective stats (base + gear with 🔥 bonus tags), a ⚡ Power score, rank badge, and your active set bonuses.",
            "🎁 **Lootbox Reveals:** All 10 box tiers (wood → chromatic) now roll rich gear with rarity floors and an animated reveal.",
            "🎚️ **Rarity Rebalance:** Top tiers are now much rarer trophies (mythic/secret/chromatic odds cut) while **luck** has a far bigger pull toward them.",
            "❤️ **Persistent Combat HP:** Your HP now carries between turns, so healing skills, shields and big hits genuinely matter.",
            "🖼️ **Embed Overhaul:** Inventory (rarity-colored, gear-power rank), Shop (icons + stat previews + compact prices) and Battle/Victory cards (HP bars, element colors, phase & skill lines).",
            "⏰ **Auto-Purge System:** Hourly cleanup task keeps event/planning channels clean while preserving interactive control panels."
        ],
        "fixed": [
            "Resolved command trigger conflicts (fixed false 'Create Character' loops)",
            "Fixed Mute permission issues using role hierarchy re-ordering",
            "Improved server auto-wipe stability with channel/role deletion delays",
            "🐛 **Gear Bonuses Bug:** Equipped gear stats were never added to combat — now correctly applied to attack & defense.",
            "🔀 **Unified RNG:** Merged three inconsistent loot systems into one luck-scaled drop engine for consistent, transparent odds."
        ],
        "removed": [
            "❌ **Fuzzy Keyword Detection:** Fully disabled in favor of exact matching to prevent command hijacking.",
            "❌ **Shop-purchased Lootboxes:** Removed from the Wandering Merchant shop to focus on combat-only progression.",
            "❌ **Redundant Welcome Messages:** Cleaned up server setup flow to prevent spam."
        ]
    },
    {"v": "v1.12", "title": "Guild Overhaul + Marketplace UI + Staff Tools",
     "added": [
         "Guild Treasury system (`guild donate`) and treasury-funded upgrades",
         "Automated private guild channels (automatic access)",
         "Interactive DM guild invites (Accept/Dismiss) with optional custom messages",
         "Taxed Player Marketplace (2.27% tax to Owner) with 2x3 category button UI",
         "Interactive Update Countdown clock for staff",
         "Auto-purge system for Event/Planning channels"
     ],
     "upgraded": [
         "Aesthetic 'starry box' UI for Status and Character creation",
         "Configurable display labels for all stats",
         "Improved fuzzy command keyword detection"
     ],
     "fixed": [
         "Mute permission issues",
         "Give command targeting"
     ]},
    {"v": "v1.11", "title": "Level & Rebirth Caps",
     "upgraded": ["Level cap increased to 100,000", "Rebirth cap increased to 1,000"],
     "fixed": ["Removed auto-wipe on startup"]},
    {"v": "v1.10", "title": "Guilds Reborn + Ambushes",
     "added": ["Guild ranks (Leader/Admin/Senior/Member) + promote/demote/kick", "`guild upgrade` (Lvl 1-10, up to 2× money & XP for all members)", "Ambush encounters with Run / Fight / Ping-Guild buttons", "Co-op `help @user` to join a friend's fight", "Announcements, Changelog & Guide channels"],
     "upgraded": ["Guild create now costs 💰10M & is capped at 1 per person", "Guild channel is now visible to members", "Faster autosave + WAL checkpoints"],
     "fixed": ["Treasury showing a Discord ID instead of gold"]},
    {"v": "v1.9", "title": "Profile Config",
     "added": ["🪪 Profile config channel (private ephemeral panel)", "Name titles: color + `[TAG]`", "Tradeable & update-ping toggles"],
     "upgraded": ["Event pings now respect your opt-in"], "fixed": ["Various permission guards"]},
    {"v": "v1.8", "title": "Endgame Economy",
     "added": ["💠 Astral Shards currency (drops in Shadow Nexus)", "Astral Exchange: magma/void armor, roles, secret classes", "7-tier custom enchants with `merge`/`apply`"],
     "upgraded": ["Hundreds of new potions"], "fixed": ["Shard balance display"]},
    {"v": "v1.7", "title": "Classes & Leaderboards",
     "added": ["5 new classes + 2 secret classes", "`g.m` message stats", "Daily/Weekly/Monthly/Yearly/All-time leaderboards"],
     "upgraded": ["`class [name]` switching"], "fixed": ["Inventory now shows equipped gear"]},
    {"v": "v1.6", "title": "Private Trading",
     "added": ["`trade @user` private trade rooms", "Offer/accept/decline, multi-item & quantity offers", "Auto-deleting trade channels"],
     "upgraded": ["Trade worth calculation"], "fixed": ["Trade ownership validation"]},
    {"v": "v1.5", "title": "Events System",
     "added": ["Staff event launcher & planner", "Server-wide 2×/3× XP/Gold/Luck events", "Scheduled events with auto start/stop"],
     "upgraded": ["Event multipliers apply in combat"], "fixed": ["Event timing edge cases"]},
    {"v": "v1.4", "title": "Staff & Moderation",
     "added": ["ADMIN (red) & OWNER (gold) roles", "`s!warn/kick/ban/mute` moderation suite", "Update broadcast button"],
     "upgraded": ["Staff-only channels"], "fixed": ["Permission checks"]},
    {"v": "v1.3", "title": "Worlds & Aesthetics",
     "added": ["Gated World channels with auto-roles", "Dark-matter embed theme", "Custom item emojis & enchant tiers"],
     "upgraded": ["Real XP curve + level-up rewards"], "fixed": ["Fuzzy typo correction"]},
    {"v": "v1.2", "title": "Dropdowns Everywhere",
     "added": ["Clickable menus for shop/sell/equip/enchant/pets/lootboxes", "Main `menu` hub"],
     "upgraded": ["Guild join now actually works"], "fixed": ["`guild create` no longer names the guild 'create ...'"]},
    {"v": "v1.1", "title": "Player Marketplace",
     "added": ["Player marketplace with player-set prices", "Equip & sell dropdowns"],
     "upgraded": ["Inventory UI"], "fixed": ["Broken reaction buttons"]},
]

GUIDE_COMMANDS = [
    ("👤 Character", [
        ("start [class]", "Create your character (warrior, mage, rogue, paladin, ranger, druid, berserker, knight, assassin, necromancer, monk)"),
        ("status / me", "View your full stats, level, gold, shards & XP bar"),
        ("class / class [name]", "List classes or switch class (adjusts stats)"),
        ("inventory / bag", "See your items + equipped gear"),
        ("equip [item]", "Equip a weapon/armor/accessory"),
        ("rebirth / prestige", "Reset for permanent power at high level"),
        ("config / settings", "Open your private profile config (titles, tradeable, pings)"),
    ]),
    ("⚔️ Combat", [
        ("attack / fight / hunt", "Start or continue a battle (watch for ambushes!)"),
        ("help @user", "Join a guildmate's fight in co-op help mode"),
        ("heal / potion", "Use a potion to restore HP"),
        ("boss", "Challenge a powerful boss"),
        ("dungeon", "Crawl dungeon floors"),
        ("pvp / duel [bet]", "Battle another player"),
        ("bounty", "Take a bounty for rewards"),
    ]),
    ("💰 Economy", [
        ("shop / buy [item]", "Wandering merchant (rotating daily stock)"),
        ("sell", "Sell items for gold"),
        ("market / market sell [item] [price]", "Player marketplace"),
        ("astralshop", "Spend 💠 Astral Shards on endgame gear, roles & secret classes"),
        ("merge [enchant] [tier]", "Fuse 2 enchants into the next tier (max T7)"),
        ("apply [enchant] [tier]", "Apply a custom enchant to your armor"),
        ("daily", "Claim your daily reward"),
        ("gamble [amount]", "Risk gold for a payout"),
        ("lootbox", "Open loot boxes"),
        ("trade @user", "Open a private trade room"),
    ]),
    ("⛏️ Gathering & Quests", [
        ("fish / mine", "Gather resources for gold"),
        ("craft", "Forge gear from materials"),
        ("alchemy", "Brew potions"),
        ("quest", "Take a quest"),
    ]),
    ("🌍 Worlds & Zones", [
        ("worlds", "See world unlocks & auto-earn roles"),
        ("zone / zone list / zone [name]", "Travel between zones"),
    ]),
    ("👥 Guilds", [
        ("guild", "View/manage your guild"),
        ("guild create [name]", "Found a guild (costs 💰10,000,000, 1 per person)"),
        ("guild join [name] / guild join", "Join a guild (or pick from a menu)"),
        ("guild leave / guild disband", "Leave, or (Leader) disband"),
        ("guild upgrade", "(Leader) Upgrade guild — +0.1× money & XP per level"),
        ("guild promote/demote/kick @user", "(Leader/Admin) Manage members"),
    ]),
    ("📊 Social & Stats", [
        ("g.m / g.m @user", "Message activity stats"),
        ("g.m leaderboard / leaderboard daily|weekly|monthly|yearly|alltime", "Leaderboards"),
        ("leaderboard", "Top players by level"),
        ("team / lobby", "Group up with others"),
        ("private", "Make your own quiet channel"),
        ("menu / help", "Browse all commands"),
    ]),
    ("🛡️ Staff (ADMIN/OWNER only)", [
        ("s!warn/unwarn/warnings @user", "Warning system"),
        ("s!kick/ban/unban/mute/unmute @user", "Moderation"),
        ("event (in events channel)", "Launch a server-wide event"),
        ("planning (in planning channel)", "Schedule a future event"),
        ("world setup", "Re-create world channels & roles"),
    ]),
]

# Co-op help-mode state: helper_id -> owner_id, owner_id -> set(helper_ids)
helping = {}
fight_helpers = {}


def enchant_item_name(family: str, tier: int) -> str:
    return f"{family} T{tier}".lower()


def is_enchant_item(name: str):
    """Return (family, tier) if name is a custom enchant item, else None."""
    n = (name or "").lower().strip()
    for fam in ENCHANT_FAMILIES:
        for t in range(1, ENCHANT_TIER_MAX + 1):
            if n == enchant_item_name(fam, t):
                return fam, t
    return None


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db():
    """Initialize database with full schema."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY,
        guild_id INTEGER DEFAULT 0,
        name TEXT NOT NULL,
        class_name TEXT NOT NULL,
        level INTEGER NOT NULL DEFAULT 1,
        xp INTEGER NOT NULL DEFAULT 0,
        gold INTEGER NOT NULL DEFAULT 0,
        hp INTEGER NOT NULL,
        max_hp INTEGER NOT NULL,
        mana INTEGER NOT NULL,
        max_mana INTEGER NOT NULL,
        atk INTEGER NOT NULL,
        defense INTEGER NOT NULL,
        crit REAL NOT NULL,
        zone TEXT NOT NULL DEFAULT 'meadows',
        rebirths INTEGER NOT NULL DEFAULT 0,
        last_action INTEGER NOT NULL DEFAULT 0,
        kills INTEGER NOT NULL DEFAULT 0,
        deaths INTEGER NOT NULL DEFAULT 0,
        total_gold_earned INTEGER NOT NULL DEFAULT 0,
        total_damage_dealt INTEGER NOT NULL DEFAULT 0,
        pvp_wins INTEGER NOT NULL DEFAULT 0,
        pvp_losses INTEGER NOT NULL DEFAULT 0,
        pvp_rating INTEGER NOT NULL DEFAULT 1000,
        playtime_seconds INTEGER NOT NULL DEFAULT 0,
        prestige INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        item_type TEXT NOT NULL,
        rarity TEXT NOT NULL,
        qty INTEGER NOT NULL DEFAULT 1,
        hp_bonus INTEGER NOT NULL DEFAULT 0,
        atk_bonus INTEGER NOT NULL DEFAULT 0,
        def_bonus INTEGER NOT NULL DEFAULT 0,
        value INTEGER NOT NULL DEFAULT 0,
        enchantments TEXT,
        UNIQUE(user_id, item_name),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS equipment (
        user_id INTEGER PRIMARY KEY,
        weapon TEXT,
        armor TEXT,
        accessory TEXT,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fights (
        user_id INTEGER PRIMARY KEY,
        enemy_name TEXT NOT NULL,
        enemy_level INTEGER NOT NULL,
        enemy_hp INTEGER NOT NULL,
        enemy_max_hp INTEGER NOT NULL,
        enemy_atk INTEGER NOT NULL,
        enemy_def INTEGER NOT NULL,
        enemy_xp INTEGER NOT NULL,
        enemy_gold INTEGER NOT NULL,
        started_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        defending INTEGER NOT NULL DEFAULT 0,
        damage_taken INTEGER NOT NULL DEFAULT 0,
        damage_dealt INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS quests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quest_key TEXT NOT NULL,
        progress INTEGER DEFAULT 0,
        target INTEGER NOT NULL,
        status TEXT DEFAULT 'active',
        UNIQUE(user_id, quest_key),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS guild_pacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild1_id INTEGER NOT NULL,
        guild2_id INTEGER NOT NULL,
        pact_type TEXT NOT NULL,
        cost_per_hour INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        status TEXT DEFAULT 'active'
    );

    CREATE TABLE IF NOT EXISTS guilds (
        guild_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_name TEXT NOT NULL UNIQUE,
        leader_id INTEGER NOT NULL,
        description TEXT,
        tier INTEGER NOT NULL DEFAULT 1,
        level INTEGER NOT NULL DEFAULT 1,
        treasury INTEGER NOT NULL DEFAULT 0,
        channel_id INTEGER,
        member_count INTEGER NOT NULL DEFAULT 1,
        total_power INTEGER NOT NULL DEFAULT 0,
        influence INTEGER NOT NULL DEFAULT 0,
        aggressiveness INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        FOREIGN KEY(leader_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS guild_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        rank TEXT NOT NULL DEFAULT 'member',
        joined_at INTEGER NOT NULL,
        contribution INTEGER NOT NULL DEFAULT 0,
        UNIQUE(guild_id, user_id),
        FOREIGN KEY(guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS characters (
        char_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        char_name TEXT UNIQUE NOT NULL,
        level INTEGER DEFAULT 1,
        created_at INTEGER NOT NULL,
        UNIQUE(user_id, guild_id),
        FOREIGN KEY(user_id) REFERENCES players(user_id),
        FOREIGN KEY(guild_id) REFERENCES guilds(guild_id)
    );

    CREATE TABLE IF NOT EXISTS guild_permissions (
        perm_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        channel_id INTEGER,
        permission_type TEXT NOT NULL,
        access_level TEXT DEFAULT 'member',
        created_at INTEGER NOT NULL,
        UNIQUE(guild_id, user_id, channel_id, permission_type),
        FOREIGN KEY(guild_id) REFERENCES guilds(guild_id),
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS channel_access_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        access_type TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        FOREIGN KEY(guild_id) REFERENCES guilds(guild_id)
    );

    CREATE TABLE IF NOT EXISTS seasons (
        season_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        season_number INTEGER NOT NULL,
        tier INTEGER DEFAULT 0,
        tier_xp INTEGER DEFAULT 0,
        rewards_claimed TEXT DEFAULT '[]',
        created_at INTEGER NOT NULL,
        UNIQUE(user_id, season_number),
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS quests (
        quest_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quest_type TEXT NOT NULL,
        quest_name TEXT NOT NULL,
        progress INTEGER DEFAULT 0,
        target INTEGER NOT NULL,
        reward_gold INTEGER DEFAULT 0,
        reward_xp INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS collections (
        collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        rarity TEXT NOT NULL,
        times_pulled INTEGER DEFAULT 1,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES players(user_id),
        UNIQUE(user_id, item_name)
    );

    CREATE TABLE IF NOT EXISTS prestige_ranks (
        rank_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        prestige_level INTEGER DEFAULT 0,
        prestige_xp INTEGER DEFAULT 0,
        title TEXT DEFAULT 'Novice',
        created_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS leaderboards (
        lb_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        stat_type TEXT NOT NULL,
        value INTEGER DEFAULT 0,
        rank_position INTEGER,
        updated_at INTEGER NOT NULL,
        UNIQUE(guild_id, user_id, stat_type),
        FOREIGN KEY(guild_id) REFERENCES guilds(guild_id),
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS battle_pass (
        bp_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        season_number INTEGER NOT NULL,
        free_tier INTEGER DEFAULT 0,
        premium_tier INTEGER DEFAULT 0,
        progress INTEGER DEFAULT 0,
        purchased INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL,
        UNIQUE(user_id, season_number),
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS rivals (
        rival_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        rival_user_id INTEGER NOT NULL,
        rivalry_score INTEGER DEFAULT 0,
        head_to_head INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL,
        UNIQUE(user_id, rival_user_id),
        FOREIGN KEY(user_id) REFERENCES players(user_id),
        FOREIGN KEY(rival_user_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS clan_wars (
        war_id INTEGER PRIMARY KEY AUTOINCREMENT,
        attacker_guild_id INTEGER NOT NULL,
        defender_guild_id INTEGER NOT NULL,
        war_status TEXT DEFAULT 'active',
        attacker_score INTEGER DEFAULT 0,
        defender_score INTEGER DEFAULT 0,
        started_at INTEGER NOT NULL,
        ended_at INTEGER,
        rewards_distributed INTEGER DEFAULT 0,
        FOREIGN KEY(attacker_guild_id) REFERENCES guilds(guild_id),
        FOREIGN KEY(defender_guild_id) REFERENCES guilds(guild_id)
    );

    CREATE TABLE IF NOT EXISTS clan_war_participants (
        participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
        war_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        kills INTEGER DEFAULT 0,
        damage_dealt INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(war_id) REFERENCES clan_wars(war_id),
        FOREIGN KEY(user_id) REFERENCES players(user_id),
        FOREIGN KEY(guild_id) REFERENCES guilds(guild_id)
    );

    CREATE TABLE IF NOT EXISTS advanced_trading (
        trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
        initiator_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        initiator_items TEXT NOT NULL,
        receiver_items TEXT NOT NULL,
        escrow_gold INTEGER DEFAULT 0,
        trade_status TEXT DEFAULT 'pending',
        expires_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(initiator_id) REFERENCES players(user_id),
        FOREIGN KEY(receiver_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS trade_ratings (
        rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rater_id INTEGER NOT NULL,
        rated_id INTEGER NOT NULL,
        rating INTEGER DEFAULT 5,
        comment TEXT,
        created_at INTEGER NOT NULL,
        UNIQUE(rater_id, rated_id),
        FOREIGN KEY(rater_id) REFERENCES players(user_id),
        FOREIGN KEY(rated_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS trades (
        trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
        initiator_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        initiator_item TEXT,
        receiver_item TEXT,
        initiator_gold INTEGER DEFAULT 0,
        receiver_gold INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at INTEGER NOT NULL,
        completed_at INTEGER,
        FOREIGN KEY(initiator_id) REFERENCES players(user_id),
        FOREIGN KEY(receiver_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS quests (
        quest_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quest_key TEXT NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        completed INTEGER NOT NULL DEFAULT 0,
        started_at INTEGER NOT NULL,
        completed_at INTEGER,
        UNIQUE(user_id, quest_key),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS achievements (
        achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        achievement_key TEXT NOT NULL,
        unlocked_at INTEGER NOT NULL,
        UNIQUE(user_id, achievement_key),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS seasons (
        season_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_time INTEGER NOT NULL,
        end_time INTEGER NOT NULL,
        rewards TEXT,
        active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS season_progress (
        user_id INTEGER NOT NULL,
        season_id INTEGER NOT NULL,
        points INTEGER NOT NULL DEFAULT 0,
        tier INTEGER NOT NULL DEFAULT 0,
        rewards_claimed INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, season_id),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE,
        FOREIGN KEY(season_id) REFERENCES seasons(season_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS economy_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,
        amount INTEGER NOT NULL,
        reason TEXT,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS pvp_battles (
        battle_id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id INTEGER NOT NULL,
        player2_id INTEGER NOT NULL,
        winner_id INTEGER NOT NULL,
        loser_id INTEGER NOT NULL,
        xp_gained INTEGER NOT NULL,
        gold_gained INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(player1_id) REFERENCES players(user_id),
        FOREIGN KEY(player2_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS crafting (
        craft_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        recipe_name TEXT NOT NULL,
        completed_count INTEGER NOT NULL DEFAULT 0,
        last_crafted INTEGER,
        UNIQUE(user_id, recipe_name),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS pets (
        pet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        pet_type TEXT NOT NULL,
        level INTEGER NOT NULL DEFAULT 1,
        xp INTEGER NOT NULL DEFAULT 0,
        obtained_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS boss_defeats (
        defeat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        boss_key TEXT NOT NULL,
        defeated_at INTEGER NOT NULL,
        xp_gained INTEGER NOT NULL,
        loot TEXT,
        UNIQUE(user_id, boss_key),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS dungeons (
        dungeon_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        dungeon_name TEXT NOT NULL,
        floor INTEGER NOT NULL DEFAULT 1,
        started_at INTEGER NOT NULL,
        last_floor_at INTEGER,
        UNIQUE(user_id, dungeon_name),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS teams (
        team_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT NOT NULL UNIQUE,
        leader_id INTEGER NOT NULL,
        member_count INTEGER NOT NULL DEFAULT 1,
        total_power INTEGER NOT NULL DEFAULT 0,
        treasury INTEGER NOT NULL DEFAULT 0,
        channel_id INTEGER,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        FOREIGN KEY(leader_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS team_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at INTEGER NOT NULL,
        UNIQUE(team_id, user_id),
        FOREIGN KEY(team_id) REFERENCES teams(team_id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS lobbies (
        lobby_id INTEGER PRIMARY KEY AUTOINCREMENT,
        lobby_name TEXT NOT NULL,
        creator_id INTEGER NOT NULL,
        max_players INTEGER NOT NULL DEFAULT 4,
        current_players INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'waiting',
        mode TEXT NOT NULL DEFAULT 'duel',
        created_at INTEGER NOT NULL,
        started_at INTEGER,
        FOREIGN KEY(creator_id) REFERENCES players(user_id)
    );

    CREATE TABLE IF NOT EXISTS lobby_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lobby_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at INTEGER NOT NULL,
        UNIQUE(lobby_id, user_id),
        FOREIGN KEY(lobby_id) REFERENCES lobbies(lobby_id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS market_listings (
        listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        item_type TEXT NOT NULL,
        rarity TEXT NOT NULL,
        power INTEGER NOT NULL DEFAULT 0,
        qty INTEGER NOT NULL DEFAULT 1,
        price INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(seller_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS warnings (
        warn_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        mod_id INTEGER NOT NULL,
        reason TEXT,
        created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS server_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        event_key TEXT NOT NULL,
        name TEXT NOT NULL,
        field TEXT NOT NULL,
        multiplier REAL NOT NULL DEFAULT 1.0,
        status TEXT NOT NULL DEFAULT 'scheduled',
        start_at INTEGER NOT NULL,
        end_at INTEGER NOT NULL,
        created_by INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS msg_stats (
        user_id INTEGER NOT NULL,
        day INTEGER NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, day)
    );

    CREATE TABLE IF NOT EXISTS player_shops (
        shop_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        shop_name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS shop_inventory (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        item_type TEXT DEFAULT 'other',
        rarity TEXT DEFAULT 'common',
        qty INTEGER NOT NULL DEFAULT 1,
        price INTEGER NOT NULL,
        listed_at INTEGER NOT NULL,
        FOREIGN KEY(shop_id) REFERENCES player_shops(shop_id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id);
    CREATE INDEX IF NOT EXISTS idx_fights_user ON fights(user_id);
    CREATE INDEX IF NOT EXISTS idx_log_user ON log(user_id);
    CREATE INDEX IF NOT EXISTS idx_guild_members ON guild_members(guild_id);
    CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
    CREATE INDEX IF NOT EXISTS idx_quests_user ON quests(user_id);
    CREATE INDEX IF NOT EXISTS idx_achievements_user ON achievements(user_id);
    CREATE INDEX IF NOT EXISTS idx_leaderboard_stat ON leaderboards(stat_type);
    CREATE INDEX IF NOT EXISTS idx_team_members ON team_members(team_id);
    CREATE INDEX IF NOT EXISTS idx_lobby_members ON lobby_members(lobby_id);
    """)
    db.commit()
    migrate_db()
    print("✅ Database initialized")


def migrate_db():
    """Add any columns missing from older rpg.db files (sqlite Row raises IndexError on missing cols)."""
    def existing_cols(table):
        try:
            return {r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        except sqlite3.Error:
            return set()

    player_cols = {
        "guild_id": "INTEGER DEFAULT 0",
        "level": "INTEGER NOT NULL DEFAULT 1",
        "xp": "INTEGER NOT NULL DEFAULT 0",
        "gold": "INTEGER NOT NULL DEFAULT 0",
        "hp": "INTEGER NOT NULL DEFAULT 100",
        "max_hp": "INTEGER NOT NULL DEFAULT 100",
        "mana": "INTEGER NOT NULL DEFAULT 50",
        "max_mana": "INTEGER NOT NULL DEFAULT 50",
        "atk": "INTEGER NOT NULL DEFAULT 10",
        "defense": "INTEGER NOT NULL DEFAULT 5",
        "crit": "REAL NOT NULL DEFAULT 0.05",
        "zone": "TEXT NOT NULL DEFAULT 'meadows'",
        "rebirths": "INTEGER NOT NULL DEFAULT 0",
        "last_action": "INTEGER NOT NULL DEFAULT 0",
        "kills": "INTEGER NOT NULL DEFAULT 0",
        "deaths": "INTEGER NOT NULL DEFAULT 0",
        "total_gold_earned": "INTEGER NOT NULL DEFAULT 0",
        "total_damage_dealt": "INTEGER NOT NULL DEFAULT 0",
        "pvp_wins": "INTEGER NOT NULL DEFAULT 0",
        "pvp_losses": "INTEGER NOT NULL DEFAULT 0",
        "pvp_rating": "INTEGER NOT NULL DEFAULT 1000",
        "playtime_seconds": "INTEGER NOT NULL DEFAULT 0",
        "prestige": "INTEGER NOT NULL DEFAULT 0",
        "astral_shards": "INTEGER NOT NULL DEFAULT 0",
        "title": "TEXT",
        "tradeable": "INTEGER NOT NULL DEFAULT 1",
        "notify": "INTEGER NOT NULL DEFAULT 1",
        "astral_unlocked": "INTEGER NOT NULL DEFAULT 0",
    }
    have = existing_cols("players")
    if have:
        for col, ddl in player_cols.items():
            if col not in have:
                try:
                    db.execute(f"ALTER TABLE players ADD COLUMN {col} {ddl}")
                    print(f"🔧 migrated players.{col}")
                except sqlite3.Error as e:
                    print(f"migrate players.{col} skipped: {e}")

    inv = existing_cols("inventory")
    if inv and "enchantments" not in inv:
        try:
            db.execute("ALTER TABLE inventory ADD COLUMN enchantments TEXT")
            print("🔧 migrated inventory.enchantments")
        except sqlite3.Error as e:
            print(f"migrate inventory.enchantments skipped: {e}")
    
    # Ensure inventory bonus columns exist
    if inv:
        for bonus_col in ["hp_bonus", "atk_bonus", "def_bonus", "value"]:
            if bonus_col not in inv:
                try:
                    default_val = "0"
                    db.execute(f"ALTER TABLE inventory ADD COLUMN {bonus_col} INTEGER NOT NULL DEFAULT {default_val}")
                    print(f"🔧 migrated inventory.{bonus_col}")
                except sqlite3.Error as e:
                    print(f"migrate inventory.{bonus_col} skipped: {e}")

    gd = existing_cols("guilds")
    if gd and "channel_id" not in gd:
        try:
            db.execute("ALTER TABLE guilds ADD COLUMN channel_id INTEGER")
            print("🔧 migrated guilds.channel_id")
        except sqlite3.Error as e:
            print(f"migrate guilds.channel_id skipped: {e}")

    # Cleanup: old versions accidentally stored a Discord snowflake (channel id) in treasury.
    if gd:
        try:
            db.execute("UPDATE guilds SET channel_id = treasury WHERE channel_id IS NULL AND treasury > 1000000000000000")
            db.execute("UPDATE guilds SET treasury = 0 WHERE treasury > 1000000000000000")
        except sqlite3.Error as e:
            print(f"treasury cleanup skipped: {e}")

    # Performance indexes (safe to re-run)
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_msg_stats_day ON msg_stats(day)",
        "CREATE INDEX IF NOT EXISTS idx_market_seller ON market_listings(seller_id)",
        "CREATE INDEX IF NOT EXISTS idx_events_status ON server_events(status)",
        "CREATE INDEX IF NOT EXISTS idx_players_level ON players(level)",
        "CREATE INDEX IF NOT EXISTS idx_players_guild ON players(guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings(user_id)",
    ):
        try:
            db.execute(idx_sql)
        except sqlite3.Error:
            pass

    db.commit()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def ts() -> int:
    return int(time.time())

def qexec(sql: str, params=()) -> sqlite3.Cursor:
    cur = db.execute(sql, params)
    db.commit()
    return cur

def rarity_emoji(rarity: str) -> str:
    return V.rarity_emoji(rarity)


def _norm_channel(name: str) -> str:
    return "".join(c for c in (name or "").lower() if c.isalpha())


def fuzzy_correct(text: str) -> str:
    """Fuzzy correction is disabled."""
    return text


def item_display(name: str, rarity: str = "common") -> str:
    return ITEM_EMOJIS.get((name or "").lower(), rarity_emoji(rarity))


def enchant_tier(level: int) -> Tuple[str, str]:
    name, glow = "", ""
    for threshold, t_name, t_glow in ENCHANT_TIERS:
        if level >= threshold:
            name, glow = t_name, t_glow
    return name, glow


def enchant_label(level: int) -> str:
    if level <= 0:
        return ""
    name, glow = enchant_tier(level)
    return f" {glow}✦{level} {name}".rstrip()


def ensure_theme_asset():
    """Generate a solid dark-matter PNG locally (no external URLs) for embed banners."""
    if THEME_PNG_PATH.exists():
        return
    try:
        w, h, rgb = 928, 160, (11, 11, 20)
        def _chunk(typ, data):
            c = typ + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        row = bytes(rgb) * w
        raw = bytearray()
        for _ in range(h):
            raw.append(0)
            raw += row
        idat = zlib.compress(bytes(raw), 9)
        THEME_PNG_PATH.write_bytes(sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b""))
    except Exception as e:
        print(f"theme asset error: {e}")


def apply_theme(embed):
    """Attach the dark-matter banner to an embed; returns a fresh discord.File (or None)."""
    try:
        if THEME_PNG_PATH.exists():
            embed.set_image(url="attachment://darkmatter.png")
            return discord.File(str(THEME_PNG_PATH), filename="darkmatter.png")
    except Exception:
        pass
    return None


# ----- Astral Shards currency, custom enchant merging, trading helpers -----

def get_shards(uid: int) -> int:
    p = get_player(uid)
    return p["astral_shards"] if p else 0


def add_shards(uid: int, n: int):
    qexec("UPDATE players SET astral_shards = astral_shards + ? WHERE user_id = ?", (n, uid))
    mark_player_dirty(uid)


def spend_shards(uid: int, n: int) -> bool:
    p = get_player(uid)
    if not p or p["astral_shards"] < n:
        return False
    qexec("UPDATE players SET astral_shards = astral_shards - ? WHERE user_id = ?", (n, uid))
    mark_player_dirty(uid)
    return True


def inv_qty(uid: int, name: str) -> int:
    row = db.execute("SELECT qty FROM inventory WHERE user_id=? AND item_name=?", (uid, (name or "").lower())).fetchone()
    return row["qty"] if row else 0


def item_worth(name: str) -> int:
    n = (name or "").lower()
    d = SHOP_ITEMS.get(n)
    if d and d.get("price"):
        return d["price"]
    row = db.execute("SELECT value FROM inventory WHERE item_name=? AND value>0 LIMIT 1", (n,)).fetchone()
    return row["value"] if row else 10


def _enchant_rarity(tier: int) -> str:
    return ["common", "uncommon", "rare", "epic", "mythic", "secret", "chromatic"][max(0, min(6, tier - 1))]


def merge_enchant(uid: int, family: str, tier: int):
    fam = next((f for f in ENCHANT_FAMILIES if f.lower() == family.lower()), None)
    if not fam:
        return False, "Unknown enchant family. Try `merge list`."
    if tier < 1 or tier >= ENCHANT_TIER_MAX:
        return False, f"You can only merge tiers 1–{ENCHANT_TIER_MAX - 1} (T{ENCHANT_TIER_MAX} is the cap)."
    src = enchant_item_name(fam, tier)
    have = inv_qty(uid, src)
    if have < 2:
        return False, f"Need **2× {fam} T{tier}** to merge (you have {have})."
    remove_item(uid, src, 2)
    dst = enchant_item_name(fam, tier + 1)
    add_item(uid, dst, "enchant", _enchant_rarity(tier + 1), 1, 0, 200 * (tier + 1))
    mark_player_dirty(uid)
    return True, f"🔮 Merged **2× {fam} T{tier}** → **1× {fam} T{tier + 1}**! ✨"


def apply_enchant(uid: int, family: str, tier: int):
    fam = next((f for f in ENCHANT_FAMILIES if f.lower() == family.lower()), None)
    if not fam:
        return False, "Unknown enchant family."
    src = enchant_item_name(fam, tier)
    if inv_qty(uid, src) < 1:
        return False, f"You don't have **{fam} T{tier}**."
    eq = db.execute("SELECT armor FROM equipment WHERE user_id=?", (uid,)).fetchone()
    if not eq or not eq["armor"]:
        return False, "Equip an armor piece first with `equip [armor]`."
    bonus = tier * 15
    remove_item(uid, src, 1)
    qexec("UPDATE inventory SET power = power + ? WHERE user_id=? AND item_name=?", (bonus, uid, eq["armor"].lower()))
    qexec("UPDATE players SET defense = defense + ? WHERE user_id=?", (bonus, uid))
    mark_player_dirty(uid)
    return True, f"🛡️ Applied **{fam} T{tier}** to **{eq['armor']}** (+{bonus} power & DEF)!"


# Trading sessions, keyed by the private trade channel id
active_trades = {}


def parse_offer(uid: int, text: str):
    """Parse an offer. Multiple items via commas; quantity via 'xN name' or 'N name'. Returns (list, error)."""
    items = []
    parts = [p.strip() for p in text.split(",")] if "," in text else [text.strip()]
    for part in parts:
        if not part:
            continue
        toks = part.split()
        qty = 1
        if toks and toks[0].lower().startswith("x") and toks[0][1:].isdigit():
            qty = int(toks[0][1:]); toks = toks[1:]
        elif toks and toks[0].isdigit():
            qty = int(toks[0]); toks = toks[1:]
        name = " ".join(toks).strip().lower()
        if not name:
            return [], "Tell me which item to offer, e.g. `offer x2 magma boots`."
        have = inv_qty(uid, name)
        if have <= 0:
            return [], f"You don't have **{name}**."
        if have < qty:
            return [], f"You only have {have}× **{name}**."
        items.append([qty, name])
    return items, ""


def offer_worth(offers) -> int:
    return sum(item_worth(name) * qty for qty, name in offers)


def transfer_offer(from_id: int, to_id: int, offers):
    for qty, name in offers:
        row = db.execute("SELECT * FROM inventory WHERE user_id=? AND item_name=?", (from_id, name)).fetchone()
        if not row or row["qty"] < qty:
            continue
        remove_item(from_id, name, qty)
        add_item(to_id, name, row["item_type"], row["rarity"], qty, row["power"], row["value"])
    mark_player_dirty(from_id)
    mark_player_dirty(to_id)


def updates_mention(guild) -> str:
    r = discord.utils.get(guild.roles, name=UPDATES_ROLE_NAME) if guild else None
    return r.mention if r else "@everyone"


def log_message(uid: int):
    qexec("INSERT INTO msg_stats(user_id, day, count) VALUES(?,?,1) ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1",
          (uid, ts() // 86400))


def msg_count(uid: int, days: int = 0) -> int:
    """days=0 -> today only; days=N -> last N days; days<0 -> all time."""
    today = ts() // 86400
    if days < 0:
        row = db.execute("SELECT COALESCE(SUM(count),0) AS c FROM msg_stats WHERE user_id=?", (uid,)).fetchone()
    elif days == 0:
        row = db.execute("SELECT COALESCE(SUM(count),0) AS c FROM msg_stats WHERE user_id=? AND day=?", (uid, today)).fetchone()
    else:
        row = db.execute("SELECT COALESCE(SUM(count),0) AS c FROM msg_stats WHERE user_id=? AND day>=?", (uid, today - days + 1)).fetchone()
    return row["c"] if row else 0


def msg_leaderboard(days: int, limit: int = 10):
    today = ts() // 86400
    if days < 0:
        return db.execute("SELECT user_id, SUM(count) AS c FROM msg_stats GROUP BY user_id ORDER BY c DESC LIMIT ?", (limit,)).fetchall()
    if days == 0:
        return db.execute("SELECT user_id, SUM(count) AS c FROM msg_stats WHERE day=? GROUP BY user_id ORDER BY c DESC LIMIT ?", (today, limit)).fetchall()
    return db.execute("SELECT user_id, SUM(count) AS c FROM msg_stats WHERE day>=? GROUP BY user_id ORDER BY c DESC LIMIT ?", (today - days + 1, limit)).fetchall()


# ----- Guild economy / ranks / upgrades -----

GUILD_CREATE_COST = 10_000_000
GUILD_MAX_LEVEL = 10
GUILD_RANKS = ["Member", "Senior", "Admin", "Leader"]


def guild_level_of(uid: int) -> int:
    p = get_player(uid)
    if not p or not p["guild_id"]:
        return 0
    g = db.execute("SELECT level FROM guilds WHERE guild_id=?", (p["guild_id"],)).fetchone()
    return g["level"] if g else 0


def guild_income_mult(uid: int) -> float:
    """+0.1x per guild level → level 10 = 2.0x money & xp for all members."""
    return 1.0 + 0.1 * guild_level_of(uid)


def guild_upgrade_cost(level: int) -> int:
    return max(1, level) * 10_000_000


def member_rank(guild_id: int, uid: int) -> str:
    row = db.execute("SELECT rank FROM guild_members WHERE guild_id=? AND user_id=?", (guild_id, uid)).fetchone()
    return row["rank"] if row else ""


def is_guild_officer(guild_id: int, uid: int) -> bool:
    return member_rank(guild_id, uid) in ("Leader", "Admin")


async def grant_guild_channel_access(dguild, channel_id, member, allow=True):
    """No separate role: give/remove a guild member's view of the private guild channel."""
    if not dguild or not channel_id or not member:
        return
    ch = dguild.get_channel(channel_id)
    if ch is None:
        return
    try:
        if allow:
            await ch.set_permissions(member, view_channel=True, send_messages=True)
        else:
            await ch.set_permissions(member, overwrite=None)
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"guild channel access error: {e}")


def strip_tag(display_name: str) -> str:
    return re.sub(r"^\[[^\]]*\]\s*", "", display_name or "").strip()


async def apply_title(member, key: str):
    """Give a colored title role + set nickname to '[TAG] name'. key='none' clears it."""
    guild = member.guild
    to_remove = [r for r in member.roles if r.name in TITLE_ROLE_NAMES]
    try:
        if to_remove:
            await member.remove_roles(*to_remove, reason="profile title change")
    except discord.Forbidden:
        pass
    base = strip_tag(member.display_name)
    if key == "none":
        try:
            await member.edit(nick=base[:32] or None)
        except (discord.Forbidden, discord.HTTPException):
            pass
        qexec("UPDATE players SET title=NULL WHERE user_id=?", (member.id,))
        mark_player_dirty(member.id)
        return True, "🧼 Title cleared."
    info = TITLES.get(key)
    if not info:
        return False, "Unknown title."
        
    role_name = f"✦ {info['name']}"
    
    # Check if user has the required role (or is staff for admin titles)
    has_role = discord.utils.get(member.roles, name=role_name)
    is_staff = any(r.name in [ADMIN_ROLE_NAME, OWNER_ROLE_NAME] for r in member.roles)
    
    if not has_role and not is_staff:
        return False, f"❌ You don't have the **{info['name']}** role!"

    try:
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            # If role doesn't exist, only owner can create it
            if not is_staff:
                return False, f"❌ The **{info['name']}** role hasn't been set up."
            role = await guild.create_role(name=role_name, colour=discord.Colour(info["color"]), hoist=False, mentionable=False)
        
        await member.add_roles(role, reason="profile title")
    except discord.Forbidden:
        return False, "I can't manage roles — give me **Manage Roles** and move my role up."
    qexec("UPDATE players SET title=? WHERE user_id=?", (key, member.id))
    mark_player_dirty(member.id)
    try:
        await member.edit(nick=f"[{info['tag']}] {base}"[:32])
    except (discord.Forbidden, discord.HTTPException):
        return True, f"Applied the **{info['name']}** name color! (I couldn't set your `[{info['tag']}]` tag — your role is above mine.)"
    return True, f"✨ You are now **[{info['tag']}] {base}** in **{info['name']}** color!"

def log_action(user_id: int, action: str, details: str):
    qexec("INSERT INTO log(user_id, action, details, created_at) VALUES(?,?,?,?)",
          (user_id, action, details[:500], ts()))

def mark_player_dirty(user_id: int):
    dirty_players.add(user_id)

def mark_fight_dirty(user_id: int):
    dirty_fights.add(user_id)

# ============================================================================
# PLAYER FUNCTIONS
# ============================================================================

def get_player(user_id: int) -> Optional[sqlite3.Row]:
    return db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()

def create_player(user: discord.User, class_name: str = "warrior") -> Optional[sqlite3.Row]:
    class_name = class_name.lower().strip()
    if class_name not in CLASSES:
        class_name = "warrior"
    
    existing = get_player(user.id)
    if existing:
        return existing
    
    base = CLASSES[class_name]
    now = ts()
    qexec(
        """INSERT INTO players
        (user_id, guild_id, name, class_name, level, xp, gold, hp, max_hp, mana, max_mana, atk, defense, crit, zone, rebirths, last_action, kills, deaths, total_gold_earned, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user.id, 0, user.name, class_name, 1, 0, DEFAULT_STARTING_GOLD, base["hp"], base["hp"], base["mana"], base["mana"], 
         base["atk"], base["def"], base["crit"], DEFAULT_STARTING_ZONE, 0, 0, 0, 0, DEFAULT_STARTING_GOLD, now, now)
    )
    qexec("INSERT OR IGNORE INTO equipment(user_id, weapon, armor, accessory) VALUES(?,?,?,?)", 
          (user.id, None, None, None))
    add_item(user.id, "rusty sword", "weapon", "common", 1, 3, STARTING_WEAPON_POWER)
    add_item(user.id, "small potion", "consumable", "common", DEFAULT_POTION_QUANTITY, 0, 15)
    mark_player_dirty(user.id)
    return get_player(user.id)

# ============================================================================
# INVENTORY
# ============================================================================

def add_item(user_id: int, item_name: str, item_type: str, rarity: str, qty: int, hp: int = 0, atk: int = 0, def_bonus: int = 0, value: int = 0) -> None:
    item_name = item_name.lower().strip()
    qexec(
        """INSERT INTO inventory(user_id, item_name, item_type, rarity, qty, hp_bonus, atk_bonus, def_bonus, value)
        VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id, item_name) DO UPDATE SET qty = qty + ?""",
        (user_id, item_name, item_type, rarity, qty, hp, atk, def_bonus, value, qty)
    )

def remove_item(user_id: int, item_name: str, qty: int = 1) -> None:
    """Remove quantity of item from user's inventory. Deletes if qty reaches 0."""
    item_name = item_name.lower().strip()
    qexec("UPDATE inventory SET qty = MAX(0, qty - ?) WHERE user_id = ? AND item_name = ?", 
          (qty, user_id, item_name))
    qexec("DELETE FROM inventory WHERE user_id = ? AND qty <= 0", (user_id,))

def get_inventory(user_id: int) -> List[sqlite3.Row]:
    """Get all items in user's inventory, sorted by rarity."""
    return db.execute("SELECT * FROM inventory WHERE user_id = ? ORDER BY rarity DESC", (user_id,)).fetchall()

def get_equipment(user_id: int) -> Dict[str, Optional[str]]:
    """Get equipped items (weapon, armor, accessory) for user."""
    row = db.execute("SELECT * FROM equipment WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else {"weapon": None, "armor": None, "accessory": None}

def equip_item(user_id: int, item_name: str) -> Tuple[bool, str]:
    item_name = item_name.lower().strip()
    item = db.execute("SELECT * FROM inventory WHERE user_id = ? AND item_name = ?", 
                     (user_id, item_name)).fetchone()
    if not item:
        return False, "Item not in inventory."
    if item["item_type"] not in ["weapon", "armor", "accessory"]:
        return False, "Can't equip that."
    
    slot = item["item_type"]
    qexec(f"UPDATE equipment SET {slot} = ? WHERE user_id = ?", (item_name, user_id))
    mark_player_dirty(user_id)
    return True, f"Equipped **{item_name}**"


# ----- Multi-stat gear bonuses + unified luck-scaled drop engine -----

# Creative bonus catalog. Names only — the engine rolls the actual stats,
# affixes and quality, so every "iron sword" you find is still unique.
BONUS_GEAR = {
    "common": [
        ("training sword", "weapon"), ("wooden club", "weapon"), ("hunting knife", "weapon"),
        ("padded vest", "armor"), ("traveler cloak", "armor"), ("leather cap", "armor"),
        ("copper ring", "accessory"), ("bone charm", "accessory"), ("string bracelet", "accessory"),
    ],
    "uncommon": [
        ("bronze blade", "weapon"), ("hatchet", "weapon"), ("oak staff", "weapon"),
        ("chainmail", "armor"), ("scout leathers", "armor"), ("kite shield", "armor"),
        ("jade pendant", "accessory"), ("silver band", "accessory"), ("hawk talisman", "accessory"),
    ],
    "rare": [
        ("frost rapier", "weapon"), ("storm bow", "weapon"), ("ember dagger", "weapon"),
        ("knight plate", "armor"), ("ranger garb", "armor"), ("tower shield", "armor"),
        ("ruby amulet", "accessory"), ("sapphire ring", "accessory"), ("wolf sigil", "accessory"),
    ],
    "epic": [
        ("thunder glaive", "weapon"), ("venom scythe", "weapon"), ("inferno warhammer", "weapon"),
        ("dragonbone plate", "armor"), ("shadowweave robe", "armor"), ("aegis bulwark", "armor"),
        ("phoenix charm", "accessory"), ("titan crown", "accessory"), ("void pendant", "accessory"),
    ],
    "legendary": [
        ("excalibur", "weapon"), ("gungnir spear", "weapon"), ("ragnarok cleaver", "weapon"),
        ("mjolnir warhammer", "weapon"), ("celestial aegis", "armor"), ("dragonlord plate", "armor"),
        ("eclipse robe", "armor"), ("crown of kings", "accessory"), ("heart of the mountain", "accessory"),
    ],
    "mythic": [
        ("worldsplitter", "weapon"), ("soulreaper scythe", "weapon"), ("starforged blade", "weapon"),
        ("titanforged plate", "armor"), ("god-king regalia", "armor"), ("aurora mantle", "armor"),
        ("eye of eternity", "accessory"), ("phoenix heart", "accessory"), ("crown of dominion", "accessory"),
    ],
    "secret": [
        ("the last word", "weapon"), ("oblivion edge", "weapon"), ("voidmaw glaive", "weapon"),
        ("armor of the forgotten", "armor"), ("shroud of nightmares", "armor"),
        ("sigil of the architect", "accessory"), ("whisper of the deep", "accessory"),
    ],
    "chromatic": [
        ("genesis", "weapon"), ("entropy reaver", "weapon"), ("prism of creation", "weapon"),
        ("carapace of the cosmos", "armor"), ("mantle of infinity", "armor"),
        ("omega core", "accessory"), ("singularity gem", "accessory"), ("crown of the universe", "accessory"),
    ],
}

_DROP_POOL_CACHE: dict = {}


def _build_drop_pool() -> dict:
    """rarity -> [(base_name, item_type)] built from the full SHOP catalog
    PLUS a big creative bonus catalog. Cached after first build."""
    if _DROP_POOL_CACHE:
        return _DROP_POOL_CACHE
    for name, d in SHOP_ITEMS.items():
        itype = d.get("type")
        if itype not in ("weapon", "armor", "accessory"):
            continue
        if d.get("admin_only") or d.get("secret"):
            continue
        rk = d.get("rarity", "common")
        if rk not in V.RARITY_ORDER:
            continue
        _DROP_POOL_CACHE.setdefault(rk, []).append((name, itype))
    # creative bonus base-names (stats are rolled by the engine, not fixed)
    for rk, entries in BONUS_GEAR.items():
        for base_name, itype in entries:
            _DROP_POOL_CACHE.setdefault(rk, []).append((base_name, itype))
    return _DROP_POOL_CACHE


def gear_bonuses(user_id: int) -> dict:
    """Sum HP/ATK/DEF granted by equipped weapon/armor/accessory + active set bonuses."""
    bonus = {"hp": 0, "atk": 0, "def": 0, "crit": 0.0}
    eq = get_equipment(user_id)
    names = [eq.get("weapon"), eq.get("armor"), eq.get("accessory")]
    set_counts = {}
    for nm in names:
        if not nm:
            continue
        row = db.execute(
            "SELECT hp_bonus, atk_bonus, def_bonus FROM inventory WHERE user_id = ? AND item_name = ?",
            (user_id, nm)).fetchone()
        if row:
            bonus["hp"] += (row["hp_bonus"] if row["hp_bonus"] else 0)
            bonus["atk"] += (row["atk_bonus"] if row["atk_bonus"] else 0)
            bonus["def"] += (row["def_bonus"] if row["def_bonus"] else 0)
        sk = V.set_of(nm)
        if sk:
            set_counts[sk] = set_counts.get(sk, 0) + 1
    # equipped item-set bonuses
    sb, labels = V.set_bonus(set_counts)
    bonus["hp"] += sb["hp"]
    bonus["atk"] += sb["atk"]
    bonus["def"] += sb["def"]
    bonus["crit"] += sb["crit"]
    bonus["set_labels"] = labels
    return bonus


def equipped_set_labels(user_id: int) -> list:
    return gear_bonuses(user_id).get("set_labels", [])


def effective_stats(p) -> dict:
    """Player base stats + equipped-gear bonuses + set bonuses."""
    uid = p["user_id"]
    b = gear_bonuses(uid)
    return {
        "atk": (p["atk"] or 0) + b["atk"],
        "defense": (p["defense"] or 0) + b["def"],
        "max_hp": (p["max_hp"] or 0) + b["hp"],
        "crit": (p["crit"] or 0.0) + b["crit"] / 100.0,   # set crit is in %-points
    }


def player_luck(p, event_luck: float = 1.0) -> float:
    """Derive a luck score from the player's level, crit and equipped power."""
    b = gear_bonuses(p["user_id"])
    acc_power = b["atk"] + b["def"] + b["hp"] // 5
    return V.luck_score(level=p["level"], crit=p["crit"] or 0.0,
                        accessory_power=acc_power, event_luck=event_luck)


def grant_rich_drop(user_id: int, level: int, zone: str = "meadows",
                    event_luck: float = 1.0, floor: str = None, cap: str = None):
    """Unified drop: luck-scaled rarity, multi-stat roll, persisted with its
    HP/ATK/DEF bonuses. Returns a rpg_visuals.RolledItem (or None)."""
    p = get_player(user_id)
    if not p:
        return None
    pool = _build_drop_pool()
    luck = player_luck(p, event_luck)
    zb = ZONES.get((zone or "").lower(), {}).get("loot_bonus", 1.0)
    item = V.roll_drop(pool, level=level, luck=luck, floor=floor, cap=cap,
                       zone_bonus=zb)
    if not item:
        return None
    # Store under the affixed display name so each roll is its own line, with
    # its rolled stats persisted into the existing bonus columns.
    add_item(user_id, item.display_name, item.item_type, item.rarity, 1,
             item.hp, item.atk, item.defense, item.value)
    mark_player_dirty(user_id)
    return item


# ----- Creative extras: reforge, salvage, codex, gamble, fortune wheel -----

def inventory_line(row) -> str:
    """Pretty one-line inventory entry with icon + rolled bonuses."""
    ic = V.item_icon(row["item_name"], row["item_type"], row["rarity"])
    line = f"  {ic} {V.rarity_emoji(row['rarity'])} **{row['item_name']}** ×{row['qty']}"
    if row["item_type"] in ("weapon", "armor", "accessory"):
        bits = []
        if row["atk_bonus"]:
            bits.append(f"⚔️{V.fmt(row['atk_bonus'])}")
        if row["def_bonus"]:
            bits.append(f"🛡️{V.fmt(row['def_bonus'])}")
        if row["hp_bonus"]:
            bits.append(f"❤️{V.fmt(row['hp_bonus'])}")
        if bits:
            line += " — " + " ".join(bits)
    return line


def reforge_item(user_id: int, item_name: str) -> Tuple[bool, str]:
    """Re-roll an item's stats/affixes for gold. Keeps the same name so any
    equipped reference stays valid."""
    p = get_player(user_id)
    if not p:
        return False, "Create a character first."
    if not item_name:
        return False, "🔨 Usage: `reforge <item name>`"
    row = db.execute("SELECT * FROM inventory WHERE user_id=? AND item_name=?",
                     (user_id, item_name)).fetchone()
    if not row:
        return False, "❌ You don't have that item."
    if row["item_type"] not in ("weapon", "armor", "accessory"):
        return False, "❌ Only weapons, armor & accessories can be reforged."
    cost = max(50, (row["value"] or 50) // 2)
    if p["gold"] < cost:
        return False, f"💰 Reforging costs {V.fmt(cost)} gold (you have {V.fmt(p['gold'])})."
    new = V.roll_item(item_name, row["item_type"], row["rarity"], max(1, p["level"]), player_luck(p))
    new.display_name = item_name.title()
    qexec("UPDATE players SET gold = gold - ? WHERE user_id=?", (cost, user_id))
    qexec("UPDATE inventory SET hp_bonus=?, atk_bonus=?, def_bonus=?, value=? WHERE user_id=? AND item_name=?",
          (new.hp, new.atk, new.defense, new.value, user_id, item_name))
    mark_player_dirty(user_id)
    return True, f"🔨 **Reforged for {V.fmt(cost)} gold!**\n{V.item_card(new)}"


def salvage_item(user_id: int, item_name: str) -> Tuple[bool, str]:
    """Destroy one of an item for gold + stardust (scales with rarity/value)."""
    p = get_player(user_id)
    if not p:
        return False, "Create a character first."
    if not item_name:
        return False, "♻️ Usage: `salvage <item name>`"
    row = db.execute("SELECT * FROM inventory WHERE user_id=? AND item_name=?",
                     (user_id, item_name)).fetchone()
    if not row:
        return False, "❌ You don't have that item."
    rank = V.RARITY_RANK.get(row["rarity"], 0)
    gold = max(5, (row["value"] or 10) // 3)
    dust = max(1, rank * 2 + random.randint(0, 2))
    remove_item(user_id, item_name, 1)
    qexec("UPDATE players SET gold = gold + ? WHERE user_id=?", (gold, user_id))
    add_item(user_id, "stardust", "material", "rare", dust, 0, 0, 0, 50)
    mark_player_dirty(user_id)
    return True, f"♻️ Salvaged {V.rarity_emoji(row['rarity'])} **{item_name}** → 💰{V.fmt(gold)} + ✨{dust} stardust"


def build_codex_embed(user_id: int):
    """Show the player's CURRENT luck-adjusted drop odds with rarity colors."""
    p = get_player(user_id)
    luck = player_luck(p) if p else 0.0
    weights = V.rarity_weights(luck)
    total = sum(weights.values()) or 1.0
    lines = [f"{V.RARITIES[k].emoji} **{V.RARITIES[k].label}** — `{100.0 * weights.get(k, 0) / total:6.3f}%`"
             for k in V.RARITY_ORDER]
    emb = discord.Embed(
        title="📖 LOOT CODEX",
        description="Your live drop odds (boosted by luck):\n\n" + "\n".join(lines),
        color=discord.Colour(0x00E5FF))
    emb.add_field(name="🍀 Your Luck", value=f"`{luck:.2f}` — raised by level, crit & equipped gear", inline=False)
    emb.set_footer(text="reforge • salvage • gamble • spin • lootbox open <tier>")
    return emb


def gamble_gold(user_id: int, amount_str: str) -> str:
    """A 3-reel slot machine. Match 3 = ×5/×10, match 2 = ×2."""
    p = get_player(user_id)
    if not p:
        return "Create a character first."
    try:
        amount = p["gold"] if amount_str in ("all", "max") else int((amount_str or "0").replace(",", ""))
    except ValueError:
        return "🎰 Usage: `gamble <amount|all>`"
    if amount <= 0:
        return "🎰 Bet must be positive."
    if amount > p["gold"]:
        return f"💰 You only have {V.fmt(p['gold'])} gold."
    symbols = ["🍒", "🍋", "🔔", "💎", "7️⃣", "🌟"]
    reel = [random.choice(symbols) for _ in range(3)]
    line = " | ".join(reel)
    qexec("UPDATE players SET gold = gold - ? WHERE user_id=?", (amount, user_id))
    if reel[0] == reel[1] == reel[2]:
        mult = 10 if reel[0] in ("💎", "7️⃣", "🌟") else 5
        win = amount * mult
        qexec("UPDATE players SET gold = gold + ? WHERE user_id=?", (win, user_id))
        mark_player_dirty(user_id)
        return f"🎰 [ {line} ]\n💥 **JACKPOT ×{mult}!** +{V.fmt(win)} gold!"
    if reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
        win = amount * 2
        qexec("UPDATE players SET gold = gold + ? WHERE user_id=?", (win, user_id))
        mark_player_dirty(user_id)
        return f"🎰 [ {line} ]\n✨ Two match — ×2! +{V.fmt(win)} gold!"
    mark_player_dirty(user_id)
    return f"🎰 [ {line} ]\n💸 No match. Lost {V.fmt(amount)} gold."


def fortune_wheel(user_id: int) -> str:
    """Free spin: gold, gear, stardust, or a jackpot."""
    p = get_player(user_id)
    if not p:
        return "Create a character first."
    wheel = "🎡 " + " ".join(random.sample(["💰", "⚔️", "✨", "🎁", "💎", "🍀", "🔮", "🪙"], 6))
    pick = random.choices(
        ["gold_small", "gold_big", "gear", "stardust", "nothing", "jackpot"],
        weights=[35, 15, 25, 13, 7, 5])[0]
    if pick == "gold_small":
        g = random.randint(50, 300) + p["level"] * 5
        qexec("UPDATE players SET gold=gold+? WHERE user_id=?", (g, user_id)); mark_player_dirty(user_id)
        return f"{wheel}\n💰 Won **{V.fmt(g)} gold**!"
    if pick == "gold_big":
        g = random.randint(500, 2000) + p["level"] * 25
        qexec("UPDATE players SET gold=gold+? WHERE user_id=?", (g, user_id)); mark_player_dirty(user_id)
        return f"{wheel}\n💰💰 **BIG WIN!** +{V.fmt(g)} gold!"
    if pick == "gear":
        d = grant_rich_drop(user_id, p["level"], p["zone"])
        return f"{wheel}\n{V.drop_banner(d)}" if d else f"{wheel}\n💨 The wheel sputtered..."
    if pick == "stardust":
        n = random.randint(3, 12)
        add_item(user_id, "stardust", "material", "rare", n, 0, 0, 0, 50); mark_player_dirty(user_id)
        return f"{wheel}\n✨ Won **{n} stardust**!"
    if pick == "jackpot":
        g = random.randint(2000, 8000)
        qexec("UPDATE players SET gold=gold+? WHERE user_id=?", (g, user_id))
        d = grant_rich_drop(user_id, p["level"], p["zone"], floor="epic")
        mark_player_dirty(user_id)
        extra = f"\n{V.drop_banner(d)}" if d else ""
        return f"{wheel}\n🎉🎉 **MEGA JACKPOT!** +{V.fmt(g)} gold!{extra}"
    return f"{wheel}\n💨 Nothing this time — spin again!"


# ----- Item inspection, comparison & the gem/socket system -----

def row_to_rolled(row) -> "RolledItem":
    """Reconstruct a RolledItem from a stored inventory row (for cards/compare)."""
    name = row["item_name"]
    rarity = row["rarity"] or "common"
    itype = row["item_type"] or "accessory"
    hp = row["hp_bonus"] or 0
    atk = row["atk_bonus"] or 0
    dfb = row["def_bonus"] or 0
    element = ""
    low = name.lower()
    for ek, ed in V.ELEMENTS.items():
        if ed["adj"].lower() in low:
            element = ek
            break
    power_est = hp * 0.25 + atk * 2 + dfb * 1.6
    ilvl = max(1, int(power_est / (V.rarity(rarity).stat_mult * 5)))
    try:
        enchant = int(row["enchantments"]) if row["enchantments"] else 0
    except (ValueError, TypeError, KeyError, IndexError):
        enchant = 0
    it = RolledItem(base_name=name, display_name=name.title(), item_type=itype,
                    rarity=rarity, ilvl=ilvl, hp=hp, atk=atk, defense=dfb, crit=0.0,
                    quality=1.0, affixes=[], element=element, sockets=0, gems=[],
                    set_name=V.set_of(name))
    it._enchant = enchant
    return it


def inspect_item(user_id: int, item_name: str) -> Tuple[bool, str]:
    if not item_name:
        return False, "🔍 Usage: `inspect <item name>`"
    row = db.execute("SELECT * FROM inventory WHERE user_id=? AND item_name=?",
                     (user_id, item_name)).fetchone()
    if not row:
        return False, "❌ You don't have that item."
    it = row_to_rolled(row)
    return True, V.item_card(it, enchant=getattr(it, "_enchant", 0))


def compare_item(user_id: int, item_name: str) -> Tuple[bool, str]:
    """Compare an inventory item against what's equipped in the same slot."""
    if not item_name:
        return False, "⚖️ Usage: `compare <item name>`"
    row = db.execute("SELECT * FROM inventory WHERE user_id=? AND item_name=?",
                     (user_id, item_name)).fetchone()
    if not row:
        return False, "❌ You don't have that item."
    if row["item_type"] not in ("weapon", "armor", "accessory"):
        return False, "⚖️ Only weapons, armor & accessories can be compared."
    new_it = row_to_rolled(row)
    eq = get_equipment(user_id)
    equipped_name = eq.get(row["item_type"])
    old = {"atk": 0, "def": 0, "hp": 0, "crit": 0, "power": 0}
    header = f"⚖️ **{item_name.title()}** vs *(nothing equipped)*"
    if equipped_name:
        erow = db.execute("SELECT * FROM inventory WHERE user_id=? AND item_name=?",
                          (user_id, equipped_name)).fetchone()
        if erow:
            old_it = row_to_rolled(erow)
            old = {"atk": old_it.atk, "def": old_it.defense, "hp": old_it.hp,
                   "crit": old_it.crit, "power": old_it.power}
            header = f"⚖️ **{item_name.title()}** vs equipped **{equipped_name.title()}**"
    return True, f"{header}\n{V.compare_stats(old, new_it)}"


GEM_PRICE_STARDUST = {"ruby": 10, "sapphire": 10, "emerald": 10,
                      "diamond": 16, "onyx": 18, "topaz": 16, "opal": 35}


def _gem_to_storable(gem_key: str) -> dict:
    """Gem bonus expressed in the 3 storable columns (crit -> atk-equivalent)."""
    b = V.gem_stats([gem_key])
    return {"atk": b["atk"] + int(b["crit"] * 8), "def": b["def"], "hp": b["hp"]}


def gem_shop_text() -> str:
    lines = ["💠 **GEM EXCHANGE** — pay with ✨stardust (from `salvage`)", "```"]
    for key, data in V.GEMS.items():
        eff = _gem_to_storable(key)
        bits = ", ".join(f"+{v} {k.upper()}" for k, v in eff.items() if v)
        lines.append(f"{data['emoji']} {data['name']:<9} {GEM_PRICE_STARDUST[key]:>3}✨   ({bits})")
    lines.append("```")
    lines.append("Buy: `gem buy <name>`  •  Socket: `socket <item> | <gem>`")
    return "\n".join(lines)


def buy_gem(user_id: int, gem_key: str) -> Tuple[bool, str]:
    gem_key = (gem_key or "").lower().strip()
    if gem_key not in V.GEMS:
        return False, f"❌ Unknown gem. Options: {', '.join(V.GEMS)}"
    cost = GEM_PRICE_STARDUST[gem_key]
    have = db.execute("SELECT qty FROM inventory WHERE user_id=? AND item_name='stardust'",
                      (user_id,)).fetchone()
    have = have["qty"] if have else 0
    if have < cost:
        return False, f"✨ Need {cost} stardust (you have {have}). Salvage gear for stardust!"
    remove_item(user_id, "stardust", cost)
    data = V.GEMS[gem_key]
    grarity = "epic" if gem_key in ("diamond", "opal") else "rare"
    add_item(user_id, f"{gem_key} gem", "material", grarity, 1, 0, 0, 0, cost * 50)
    mark_player_dirty(user_id)
    return True, f"{data['emoji']} Bought a **{data['name']}** for {cost}✨! Socket it with `socket <item> | {gem_key}`"


def socket_gem(user_id: int, item_name: str, gem_key: str) -> Tuple[bool, str]:
    item_name = (item_name or "").lower().strip()
    gem_key = (gem_key or "").lower().strip()
    if gem_key not in V.GEMS:
        return False, f"❌ Unknown gem. Options: {', '.join(V.GEMS)}"
    row = db.execute("SELECT * FROM inventory WHERE user_id=? AND item_name=?",
                     (user_id, item_name)).fetchone()
    if not row:
        return False, "❌ You don't have that item."
    if row["item_type"] not in ("weapon", "armor", "accessory"):
        return False, "💠 Only weapons, armor & accessories can be socketed."
    gem_row = db.execute("SELECT qty FROM inventory WHERE user_id=? AND item_name=?",
                         (user_id, f"{gem_key} gem")).fetchone()
    if not gem_row or gem_row["qty"] < 1:
        return False, f"❌ You don't own a {V.GEMS[gem_key]['name']}. Buy one with `gem buy {gem_key}`."
    add = _gem_to_storable(gem_key)
    remove_item(user_id, f"{gem_key} gem", 1)
    qexec("""UPDATE inventory SET hp_bonus = hp_bonus + ?, atk_bonus = atk_bonus + ?,
             def_bonus = def_bonus + ?, value = value + ? WHERE user_id=? AND item_name=?""",
          (add["hp"], add["atk"], add["def"], 300, user_id, item_name))
    mark_player_dirty(user_id)
    new_row = db.execute("SELECT * FROM inventory WHERE user_id=? AND item_name=?",
                         (user_id, item_name)).fetchone()
    card = V.item_card(row_to_rolled(new_row))
    return True, f"{V.GEMS[gem_key]['emoji']} Infused **{item_name.title()}** with a {V.GEMS[gem_key]['name']}!\n{card}"


# ============================================================================
# COMBAT
# ============================================================================

def get_fight(user_id: int):
    return db.execute("SELECT * FROM fights WHERE user_id = ?", (user_id,)).fetchone()

def make_enemy(level: int, zone: str):
    enemy_list = ZONES[zone]["enemy"]
    name = random.choice(enemy_list)
    enemy_level = max(level, random.randint(level - 2, level + 3))
    scaling = 1 + (enemy_level - 1) * 0.15
    return {
        "name": name,
        "level": enemy_level,
        "hp": int(50 * scaling),
        "max_hp": int(50 * scaling),
        "atk": int(8 * scaling),
        "def": int(3 * scaling),
        "xp": int(50 + enemy_level * 20),
        "gold": int(30 + enemy_level * 8),
    }

def save_fight(user_id: int, enemy: dict):
    now = ts()
    qexec(
        """INSERT OR REPLACE INTO fights(user_id, enemy_name, enemy_level, enemy_hp, enemy_max_hp, enemy_atk, enemy_def, enemy_xp, enemy_gold, started_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, enemy["name"], enemy["level"], enemy["hp"], enemy["max_hp"], enemy["atk"], 
         enemy["def"], enemy["xp"], enemy["gold"], now, now)
    )
    mark_fight_dirty(user_id)

def pick_zone(level: int, current_zone: str) -> str:
    available = [z for z, info in ZONES.items() if info["min_level"] <= level]
    return random.choice(available) if available else current_zone

def maybe_grant_loot(user_id: int, level: int, zone: str) -> tuple:
    rarities = ["common", "uncommon", "rare", "epic"]
    rarity = random.choices(rarities, weights=[50, 30, 15, 5])[0]

    # ~30% of drops are real equipment pulled from the huge catalog
    if random.random() < 0.30:
        gear_rarity = random.choices(
            ["common", "uncommon", "rare", "epic", "legendary", "mythic"],
            weights=[40, 28, 18, 9, 4, 1],
        )[0]
        gear = random_item_by_rarity(gear_rarity)
        if gear:
            gd = SHOP_ITEMS[gear]
            add_item(user_id, gear, gd["type"], gd["rarity"], 1, gd.get("power", 0), gd.get("price", 10))
            return gear, gd["type"], gd["rarity"], 1, gd.get("power", 0), gd.get("price", 10)

    loot_table = {
        "common": ["iron ore", "copper ore", "herbs", "cloth"],
        "uncommon": ["silver bar", "leather", "ancient coin"],
        "rare": ["void shard", "crystal", "dragon scale"],
        "epic": ["mythic core", "ancient rune", "godly essence"],
    }
    item_name = random.choice(loot_table[rarity])
    qty = random.randint(1, 3) if rarity == "common" else 1
    power = {"common": 0, "uncommon": 2, "rare": 5, "epic": 10}.get(rarity, 0)
    value = {"common": 25, "uncommon": 75, "rare": 250, "epic": 500}.get(rarity, 10)
    add_item(user_id, item_name, "material", rarity, qty, power, value)
    return item_name, "material", rarity, qty, power, value

# ============================================================================
# LEVELING / ENCHANT / WORLD HELPERS
# ============================================================================

def xp_to_next(level: int) -> int:
    """Real escalating XP curve for the next level."""
    return int(100 + (level ** 2) * 50 + level * 100)


def resolve_levels(user_id: int) -> list:
    """Convert accumulated XP into level-ups with stat growth. Returns list of new levels reached."""
    p = get_player(user_id)
    if not p:
        return []
    level = p["level"]
    xp = p["xp"]
    max_hp, max_mana, atk, defense = p["max_hp"], p["max_mana"], p["atk"], p["defense"]
    gained = []
    while xp >= xp_to_next(level) and level < 100000:
        xp -= xp_to_next(level)
        level += 1
        max_hp += 12 + level // 5
        max_mana += 5 + level // 10
        atk += 3
        defense += 2
        gained.append(level)
    if gained:
        qexec(
            "UPDATE players SET level=?, xp=?, max_hp=?, max_mana=?, atk=?, defense=?, hp=? WHERE user_id=?",
            (level, xp, max_hp, max_mana, atk, defense, max_hp, user_id),
        )
        mark_player_dirty(user_id)
    return gained


def world_reqs_met(player, w) -> Tuple[bool, list]:
    unmet = []
    if player["level"] < w["level"]:
        unmet.append(f"Level {w['level']}")
    if player["prestige"] < w["prestige"]:
        unmet.append(f"Prestige {w['prestige']}")
    if player["rebirths"] < w["rebirth"]:
        unmet.append(f"Rebirth {w['rebirth']}")
    return (len(unmet) == 0, unmet)


def get_enchant_level(item) -> int:
    try:
        return int(item["enchantments"]) if item["enchantments"] else 0
    except (ValueError, TypeError, KeyError):
        return 0


def enchant_cost(level: int) -> int:
    return int(ENCHANT_BASE_COST * (ENCHANT_GROWTH ** level))


def enchant_success_chance(level: int) -> float:
    return max(0.05, 0.95 - level * 0.045)


# ============================================================================
# PVP SYSTEM
# ============================================================================

def initiate_pvp(challenger_id: int, opponent_id: int) -> Tuple[bool, str]:
    """Start PvP battle between players."""
    challenger = get_player(challenger_id)
    opponent = get_player(opponent_id)
    
    if not challenger or not opponent:
        return False, "Player not found"
    if challenger_id == opponent_id:
        return False, "Can't battle yourself"
    if get_fight(challenger_id):
        return False, "Already in combat"
    if get_fight(opponent_id):
        return False, "Opponent in combat"
    
    # Simple PvP: both players, random winner based on stats
    challenger_power = challenger["atk"] + challenger["defense"]
    opponent_power = opponent["atk"] + opponent["defense"]
    
    if random.random() * challenger_power > random.random() * opponent_power:
        winner_id = challenger_id
        loser_id = opponent_id
    else:
        winner_id = opponent_id
        loser_id = challenger_id
    
    xp_reward = 500
    gold_reward = 250
    
    qexec("UPDATE players SET pvp_wins = pvp_wins + 1, pvp_rating = pvp_rating + 50, xp = xp + ?, gold = gold + ? WHERE user_id = ?",
          (xp_reward, gold_reward, winner_id))
    qexec("UPDATE players SET pvp_losses = pvp_losses + 1, pvp_rating = MAX(500, pvp_rating - 25) WHERE user_id = ?",
          (loser_id,))
    
    qexec("INSERT INTO pvp_battles(player1_id, player2_id, winner_id, loser_id, xp_gained, gold_gained, created_at) VALUES(?,?,?,?,?,?,?)",
          (challenger_id, opponent_id, winner_id, loser_id, xp_reward, gold_reward, ts()))
    
    mark_player_dirty(winner_id)
    mark_player_dirty(loser_id)
    return True, f"Battle complete! Winner: {get_player(winner_id)['name']}"

# ============================================================================
# CRAFTING SYSTEM
# ============================================================================

def craft_item(user_id: int, recipe_name: str) -> Tuple[bool, str]:
    """Craft an item from materials."""
    if recipe_name not in CRAFTING_RECIPES:
        return False, "Recipe not found"
    
    recipe = CRAFTING_RECIPES[recipe_name]
    p = get_player(user_id)
    
    if p["level"] < recipe["level"]:
        return False, f"Need level {recipe['level']}"
    
    # Check materials
    for material, qty in recipe["materials"]:
        item = db.execute("SELECT * FROM inventory WHERE user_id = ? AND item_name = ?", 
                         (user_id, material)).fetchone()
        if not item or item["qty"] < qty:
            return False, f"Need {qty} {material}"
    
    # Remove materials
    for material, qty in recipe["materials"]:
        remove_item(user_id, material, qty)
    
    # Add crafted item
    add_item(user_id, recipe_name, "crafted", "rare", 1, 10, 500)
    
    # Grant XP
    qexec("UPDATE players SET xp = xp + ? WHERE user_id = ?", (recipe["xp"], user_id))
    
    # Track crafting
    qexec("INSERT INTO crafting(user_id, recipe_name, last_crafted) VALUES(?,?,?) ON CONFLICT(user_id, recipe_name) DO UPDATE SET completed_count = completed_count + 1, last_crafted = ?",
          (user_id, recipe_name, ts(), ts()))
    
    mark_player_dirty(user_id)
    return True, f"✨ Crafted **{recipe_name}**! (+{recipe['xp']} XP)"

# ============================================================================
# PET SYSTEM
# ============================================================================

def buy_pet(user_id: int, pet_type: str) -> Tuple[bool, str]:
    """Purchase and obtain a pet."""
    if pet_type not in PETS:
        return False, "Pet not found"
    
    p = get_player(user_id)
    pet = PETS[pet_type]
    cost = pet["cost"]
    
    if p["gold"] < cost:
        return False, f"Need {cost - p['gold']} more gold"
    
    # Check if already has this pet
    existing = db.execute("SELECT * FROM pets WHERE user_id = ? AND pet_type = ?", 
                         (user_id, pet_type)).fetchone()
    if existing:
        return False, "Already have this pet"
    
    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (cost, user_id))
    qexec("INSERT INTO pets(user_id, pet_type, obtained_at) VALUES(?,?,?)", 
          (user_id, pet_type, ts()))
    
    mark_player_dirty(user_id)
    return True, f"🐾 Obtained **{pet['name']}**! ATK+{pet['atk_bonus']} DEF+{pet['def_bonus']}"

def get_pets(user_id: int):
    """Get all pets owned by player."""
    return db.execute("SELECT * FROM pets WHERE user_id = ?", (user_id,)).fetchall()

def create_character_for_guild(user_id: int, guild_id: int) -> Tuple[bool, str]:
    """Create a new character when joining a guild."""
    p = get_player(user_id)
    if not p:
        return False, "Player not found"
    
    existing = db.execute("SELECT * FROM characters WHERE user_id = ? AND guild_id = ?",
                         (user_id, guild_id)).fetchone()
    if existing:
        return False, "Character already exists in this guild"
    
    char_name = f"{p['name']}-{guild_id}"
    try:
        qexec("INSERT INTO characters(user_id, guild_id, char_name, level, created_at) VALUES(?,?,?,?,?)",
              (user_id, guild_id, char_name, 1, ts()))
        qexec("INSERT INTO guild_permissions(guild_id, user_id, permission_type, access_level, created_at) VALUES(?,?,?,?,?)",
              (guild_id, user_id, 'base_access', 'member', ts()))
        return True, f"✨ Character created: **{char_name}**"
    except Exception as e:
        return False, str(e)

def check_channel_access(guild_id: int, user_id: int, channel_id: int) -> bool:
    """Check if user has access to private guild channel."""
    perm = db.execute("SELECT * FROM guild_permissions WHERE guild_id = ? AND user_id = ? AND channel_id = ? AND access_level != 'restricted'",
                     (guild_id, user_id, channel_id)).fetchone()
    return perm is not None

def grant_channel_access(guild_id: int, user_id: int, channel_id: int, level: str = 'member'):
    """Grant user access to private channel."""
    qexec("INSERT OR REPLACE INTO guild_permissions(guild_id, user_id, channel_id, permission_type, access_level, created_at) VALUES(?,?,?,?,?,?)",
          (guild_id, user_id, channel_id, 'channel_specific', level, ts()))
    qexec("INSERT INTO channel_access_log(guild_id, channel_id, user_id, access_type, timestamp) VALUES(?,?,?,?,?)",
          (guild_id, channel_id, user_id, 'granted', ts()))

def revoke_channel_access(guild_id: int, user_id: int, channel_id: int):
    """Revoke user access to private channel."""
    qexec("DELETE FROM guild_permissions WHERE guild_id = ? AND user_id = ? AND channel_id = ?",
          (guild_id, user_id, channel_id))
    qexec("INSERT INTO channel_access_log(guild_id, channel_id, user_id, access_type, timestamp) VALUES(?,?,?,?,?)",
          (guild_id, channel_id, user_id, 'revoked', ts()))

def update_leaderboard(guild_id: int, user_id: int, stat_type: str, value: int):
    """Update guild leaderboard for a stat."""
    qexec("INSERT OR REPLACE INTO leaderboards(guild_id, user_id, stat_type, value, updated_at) VALUES(?,?,?,?,?)",
          (guild_id, user_id, stat_type, value, ts()))

def get_guild_leaderboard(guild_id: int, stat_type: str, limit: int = 10):
    """Get top players in guild for a stat."""
    return db.execute(
        "SELECT user_id, value FROM leaderboards WHERE guild_id = ? AND stat_type = ? ORDER BY value DESC LIMIT ?",
        (guild_id, stat_type, limit)
    ).fetchall()

def add_rival(user_id: int, rival_id: int):
    """Add a rival to player's rivalry list."""
    try:
        qexec("INSERT OR IGNORE INTO rivals(user_id, rival_user_id, rivalry_score, created_at) VALUES(?,?,?,?)",
              (user_id, rival_id, 0, ts()))
        return True
    except sqlite3.Error as e:
        print(f"add_rival error: {e}")
        return False

def update_rivalry_score(user_id: int, rival_id: int, points: int):
    """Update rivalry score after PvP."""
    qexec("UPDATE rivals SET rivalry_score = rivalry_score + ?, head_to_head = head_to_head + 1 WHERE user_id = ? AND rival_user_id = ?",
          (points, user_id, rival_id))

def get_rivals(user_id: int, limit: int = 5):
    """Get player's top rivals."""
    return db.execute(
        "SELECT rival_user_id, rivalry_score, head_to_head FROM rivals WHERE user_id = ? ORDER BY rivalry_score DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()

def start_clan_war(attacker_guild_id: int, defender_guild_id: int):
    """Initiate a clan war between two guilds."""
    try:
        cursor = qexec(
            "INSERT INTO clan_wars(attacker_guild_id, defender_guild_id, war_status, started_at) VALUES(?,?,?,?)",
            (attacker_guild_id, defender_guild_id, 'active', ts())
        )
        return True, f"⚔️ Clan War Started! {attacker_guild_id} vs {defender_guild_id}"
    except sqlite3.Error as e:
        print(f"start_clan_war error: {e}")
        return False, "Cannot start war"

def add_war_participant(war_id: int, user_id: int, guild_id: int):
    """Add player to clan war."""
    qexec(
        "INSERT INTO clan_war_participants(war_id, user_id, guild_id, created_at) VALUES(?,?,?,?)",
        (war_id, user_id, guild_id, ts())
    )

def update_war_damage(war_id: int, user_id: int, damage: int):
    """Update damage dealt in clan war."""
    qexec(
        "UPDATE clan_war_participants SET damage_dealt = damage_dealt + ? WHERE war_id = ? AND user_id = ?",
        (damage, war_id, user_id)
    )

def get_active_clan_wars(guild_id: int):
    """Get active clan wars for a guild."""
    return db.execute(
        "SELECT * FROM clan_wars WHERE (attacker_guild_id = ? OR defender_guild_id = ?) AND war_status = 'active'",
        (guild_id, guild_id)
    ).fetchall()

def create_trade_offer(initiator_id: int, receiver_id: int, initiator_items: list, receiver_items: list, escrow_gold: int = 0):
    """Create a trade offer with verification."""
    items_init = json.dumps(initiator_items)
    items_recv = json.dumps(receiver_items)
    expires_at = ts() + 3600
    
    try:
        cursor = qexec(
            "INSERT INTO advanced_trading(initiator_id, receiver_id, initiator_items, receiver_items, escrow_gold, expires_at, created_at) VALUES(?,?,?,?,?,?,?)",
            (initiator_id, receiver_id, items_init, items_recv, escrow_gold, expires_at, ts())
        )
        return True, cursor.lastrowid
    except sqlite3.Error as e:
        print(f"initiate_trade error: {e}")
        return False, None

def accept_trade(trade_id: int):
    """Accept and finalize a trade."""
    trade = db.execute("SELECT * FROM advanced_trading WHERE trade_id = ?", (trade_id,)).fetchone()
    if not trade or trade['trade_status'] != 'pending':
        return False, "Invalid trade"
    
    try:
        init_items = json.loads(trade['initiator_items'])
        recv_items = json.loads(trade['receiver_items'])
        
        # Transfer items
        for item in init_items:
            remove_item(trade['initiator_id'], item)
            add_item(trade['receiver_id'], item, "trade", "common", 1)
        
        for item in recv_items:
            remove_item(trade['receiver_id'], item)
            add_item(trade['initiator_id'], item, "trade", "common", 1)
        
        # Handle escrow gold
        if trade['escrow_gold'] > 0:
            qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (trade['escrow_gold'], trade['initiator_id']))
            qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (trade['escrow_gold'], trade['receiver_id']))
        
        qexec("UPDATE advanced_trading SET trade_status = 'completed' WHERE trade_id = ?", (trade_id,))
        mark_player_dirty(trade['initiator_id'])
        mark_player_dirty(trade['receiver_id'])
        return True, "Trade completed!"
    except Exception as e:
        return False, str(e)

def rate_trader(rater_id: int, rated_id: int, rating: int, comment: str = ""):
    """Rate a player after trading."""
    try:
        qexec(
            "INSERT OR REPLACE INTO trade_ratings(rater_id, rated_id, rating, comment, created_at) VALUES(?,?,?,?,?)",
            (rater_id, rated_id, max(1, min(5, rating)), comment, ts())
        )
        return True
    except sqlite3.Error as e:
        print(f"rate_trade error: {e}")
        return False

# ============================================================================
# BOSS BATTLES
# ============================================================================

def start_boss_fight(user_id: int, boss_key: str) -> Tuple[bool, str]:
    """Start a boss battle."""
    if boss_key not in BOSSES:
        return False, "Boss not found"
    
    p = get_player(user_id)
    boss = BOSSES[boss_key]
    
    if p["level"] < boss["min_level"]:
        return False, f"Need level {boss['min_level']}"
    
    if get_fight(user_id):
        return False, "Already in combat"
    
    # Check if already defeated
    defeated = db.execute("SELECT * FROM boss_defeats WHERE user_id = ? AND boss_key = ?", 
                         (user_id, boss_key)).fetchone()
    if defeated:
        return False, "Already defeated this boss"
    
    # Save boss as fight
    boss_for_fight = {
        "name": boss["name"],
        "level": boss["level"],
        "hp": boss["hp"],
        "max_hp": boss["hp"],
        "atk": boss["atk"],
        "def": boss["def"],
        "xp": boss["xp"],
        "gold": boss["gold"],
    }
    save_fight(user_id, boss_for_fight)
    qexec("INSERT INTO boss_defeats(user_id, boss_key, defeated_at, xp_gained) VALUES(?,?,?,?)",
          (user_id, boss_key, ts(), boss["xp"]))
    
    return True, f"⚔️ **{boss['name']}** appears!\nHP: {boss['hp']}\nATK: {boss['atk']} DEF: {boss['def']}\nUse !attack"

# ============================================================================
# DUNGEON SYSTEM
# ============================================================================

def start_dungeon(user_id: int, dungeon_name: str = "Abyss") -> Tuple[bool, str]:
    """Start a dungeon crawl (multiple floors)."""
    existing = db.execute("SELECT * FROM dungeons WHERE user_id = ? AND dungeon_name = ?", 
                         (user_id, dungeon_name)).fetchone()
    
    if existing:
        # Continue dungeon
        floor = existing["floor"]
    else:
        # New dungeon
        qexec("INSERT INTO dungeons(user_id, dungeon_name, started_at) VALUES(?,?,?)", 
              (user_id, dungeon_name, ts()))
        floor = 1
    
    p = get_player(user_id)
    enemy = make_enemy(p["level"] + floor, p["zone"])
    save_fight(user_id, enemy)
    
    return True, f"📍 **{dungeon_name}** Floor {floor}\n🐾 {enemy['name']} appears!"

# ============================================================================
# TOURNAMENT SYSTEM
# ============================================================================

def start_tournament(guild_id: int) -> Tuple[bool, str]:
    """Start a guild tournament."""
    members = db.execute("SELECT user_id FROM guild_members WHERE guild_id = ?", 
                        (guild_id,)).fetchall()
    
    if len(members) < 2:
        return False, "Need at least 2 members"
    
    # Bracket-style tournament (simplified)
    tournament_data = {
        "guild_id": guild_id,
        "started_at": ts(),
        "participants": [m[0] for m in members],
        "stage": "round1"
    }
    
    return True, f"🏆 Tournament started with {len(members)} players!"

# ============================================================================
# GUILDS
# ============================================================================

def create_guild(leader_id: int, guild_name: str) -> Tuple[bool, str]:
    if len(guild_name) < 3 or len(guild_name) > 32:
        return False, "Name must be 3-32 chars"
    try:
        cursor = qexec("INSERT INTO guilds(guild_name, leader_id, tier, created_at, updated_at) VALUES(?,?,?,?,?)",
                      (guild_name, leader_id, 1, ts(), ts()))
        guild_id = cursor.lastrowid
        qexec("INSERT INTO guild_members(guild_id, user_id, rank, joined_at) VALUES(?,?,?,?)", 
              (guild_id, leader_id, "leader", ts()))
        qexec("UPDATE players SET guild_id = ? WHERE user_id = ?", (guild_id, leader_id))
        mark_player_dirty(leader_id)
        return True, f"Guild **{guild_name}** created!"
    except sqlite3.IntegrityError:
        return False, "Guild name taken"

def join_guild(user_id: int, guild_id: int) -> Tuple[bool, str]:
    guild = db.execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)).fetchone()
    if not guild:
        return False, "Guild not found"
    if guild["member_count"] >= 30:
        return False, f"Guild is full! (Max 30 members)"
    existing = db.execute("SELECT * FROM guild_members WHERE guild_id = ? AND user_id = ?", 
                         (guild_id, user_id)).fetchone()
    if existing:
        return False, "Already in guild"
    try:
        qexec("INSERT INTO guild_members(guild_id, user_id, rank, joined_at) VALUES(?,?,?,?)", 
              (guild_id, user_id, "member", ts()))
        qexec("UPDATE players SET guild_id = ? WHERE user_id = ?", (guild_id, user_id))
        qexec("UPDATE guilds SET member_count = member_count + 1 WHERE guild_id = ?", (guild_id,))
        mark_player_dirty(user_id)
        return True, f"Joined **{guild['guild_name']}**!"
    except Exception as e:
        return False, str(e)

def list_guilds() -> List[tuple]:
    return db.execute("SELECT guild_id, guild_name, tier, member_count, treasury FROM guilds ORDER BY tier DESC LIMIT 25").fetchall()

# ============================================================================
# INTERACTIVE UI (dropdown menus) + PLAYER MARKETPLACE
# ============================================================================

EQUIPPABLE_TYPES = ("weapon", "armor", "accessory")


class EquipSelect(discord.ui.Select):
    def __init__(self, owner_id: int, items):
        self.owner_id = owner_id
        options = [
            discord.SelectOption(
                label=row["item_name"][:100],
                description=f"{row['item_type']} • +{row['power']} power"[:100],
                emoji=rarity_emoji(row["rarity"]),
                value=row["item_name"],
            )
            for row in items[:25]
        ]
        super().__init__(placeholder="🔧 Select an item to equip…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your inventory!", ephemeral=True)
            return
        ok, msg = equip_item(self.owner_id, self.values[0])
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class EquipView(discord.ui.View):
    def __init__(self, owner_id: int, items):
        super().__init__(timeout=120)
        if items:
            self.add_item(EquipSelect(owner_id, items))


class SellSelect(discord.ui.Select):
    def __init__(self, owner_id: int, items):
        self.owner_id = owner_id
        options = [
            discord.SelectOption(
                label=row["item_name"][:100],
                description=f"x{row['qty']} • {max(1, (row['value'] or 10) // 2)} gold each"[:100],
                emoji=rarity_emoji(row["rarity"]),
                value=row["item_name"],
            )
            for row in items[:25]
        ]
        super().__init__(placeholder="💰 Select an item to sell…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your inventory!", ephemeral=True)
            return
        item = db.execute("SELECT * FROM inventory WHERE user_id = ? AND item_name = ?",
                          (self.owner_id, self.values[0])).fetchone()
        if not item or item["qty"] < 1:
            await interaction.response.send_message("❌ You no longer have that item.", ephemeral=True)
            return
        price = max(1, (item["value"] or 10) // 2)
        remove_item(self.owner_id, self.values[0], 1)
        qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (price, self.owner_id))
        mark_player_dirty(self.owner_id)
        await interaction.response.send_message(f"💰 Sold **{self.values[0]}** for {price} gold!", ephemeral=True)


class SellView(discord.ui.View):
    def __init__(self, owner_id: int, items):
        super().__init__(timeout=120)
        if items:
            self.add_item(SellSelect(owner_id, items))


def list_market(limit: int = 25):
    return db.execute("SELECT * FROM market_listings ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()


def market_list_item(seller_id: int, item_name: str, price: int, qty: int = 1) -> Tuple[bool, str]:
    item_name = item_name.lower().strip()
    if price < 1:
        return False, "Price must be at least 1 gold."
    item = db.execute("SELECT * FROM inventory WHERE user_id = ? AND item_name = ?",
                      (seller_id, item_name)).fetchone()
    if not item or item["qty"] < qty:
        return False, f"You don't have {qty}x {item_name}."
    remove_item(seller_id, item_name, qty)
    qexec("INSERT INTO market_listings(seller_id, item_name, item_type, rarity, power, qty, price, created_at) VALUES(?,?,?,?,?,?,?,?)",
          (seller_id, item_name, item["item_type"], item["rarity"], item["power"], qty, price, ts()))
    return True, f"Listed **{item_name}** x{qty} for 💰{price}!"


def market_buy(buyer_id: int, listing_id: int) -> Tuple[bool, str]:
    listing = db.execute("SELECT * FROM market_listings WHERE listing_id = ?", (listing_id,)).fetchone()
    if not listing:
        return False, "Listing not found (it may have been bought already)."
    if listing["seller_id"] == buyer_id:
        return False, "You can't buy your own listing."
    buyer = get_player(buyer_id)
    if not buyer:
        return False, "Create a character first."
    if buyer["gold"] < listing["price"]:
        return False, f"Need {listing['price'] - buyer['gold']} more gold."
    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (listing["price"], buyer_id))

    # Dynamic tax rate + owner from config (set via s!settax and s!setowner)
    tax_rate = float(CONFIG.get("trade_tax", 0.0227))
    tax = int(listing["price"] * tax_rate)
    seller_payout = listing["price"] - tax
    OWNER_USER_ID = int(CONFIG.get("tax_owner_id", 0))

    qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (seller_payout, listing["seller_id"]))
    if OWNER_USER_ID and OWNER_USER_ID != listing["seller_id"]:
        qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (tax, OWNER_USER_ID))
        mark_player_dirty(OWNER_USER_ID)
    # If no owner set, tax is simply removed from circulation (gold sink)

    add_item(buyer_id, listing["item_name"], listing["item_type"], listing["rarity"],
             listing["qty"], listing["power"], listing["price"])
    qexec("DELETE FROM market_listings WHERE listing_id = ?", (listing_id,))
    mark_player_dirty(buyer_id)
    mark_player_dirty(listing["seller_id"])
    tax_pct = round(tax_rate * 100, 2)
    return True, f"Bought **{listing['item_name']}**! ({tax_pct}% tax: 💰{tax} {'→ owner' if OWNER_USER_ID else 'removed from economy'})"


class MarketBuySelect(discord.ui.Select):
    def __init__(self, listings):
        options = [
            discord.SelectOption(
                label=f"{l['item_name']} — {l['price']}g"[:100],
                description=f"x{l['qty']} • {l['rarity']} • listing #{l['listing_id']}"[:100],
                emoji=rarity_emoji(l["rarity"]),
                value=str(l["listing_id"]),
            )
            for l in listings[:25]
        ]
        super().__init__(placeholder="🛒 Select a listing to buy…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not get_player(interaction.user.id):
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        ok, msg = market_buy(interaction.user.id, int(self.values[0]))
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class MarketCategoryView(discord.ui.View):
    def __init__(self, listings):
        super().__init__(timeout=180)
        self.listings = listings
        categories = [
            ("⚔️ Weapons", "weapon"), ("🧪 Potions", "consumable"),
            ("🛡️ Armor", "armor"), ("💍 Acc", "accessory"),
            ("🪨 Materials", "material"), ("❔ Other", "other")
        ]
        for i, (label, cat) in enumerate(categories):
            button = CategoryButton(label, cat, listings)
            # Add buttons to rows (0,1,2 = row 0; 3,4,5 = row 1)
            button.row = i // 3
            self.add_item(button)

class CategoryButton(discord.ui.Button):
    def __init__(self, label, cat, listings):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.cat = cat
        self.listings = listings
    
    async def callback(self, interaction: discord.Interaction):
        filtered = [l for l in self.listings if l['item_type'] == self.cat or (self.cat == 'other' and l['item_type'] not in ['weapon', 'consumable', 'armor', 'accessory', 'material'])]
        if not filtered:
            await interaction.response.send_message(f"No listings found in {self.label}.", ephemeral=True)
            return
            
        desc = "\n".join(
            f"`#{l['listing_id']}` {rarity_emoji(l['rarity'])} **{l['item_name']}** x{l['qty']} — 💰{l['price']} (<@{l['seller_id']}>)"
            for l in filtered
        )
        embed = discord.Embed(title=f"🏪 {self.label} ✨", description=desc, color=discord.Colour(0xFF4081))
        await interaction.response.edit_message(embed=embed, view=self.view)


# ----- PLAYER SHOP VIEWS -----

class PlayerShopCategoryButton(discord.ui.Button):
    def __init__(self, label, cat, user_id):
        super().__init__(label=label, style=discord.ButtonStyle.blurple)
        self.cat = cat
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        shops = db.execute(
            "SELECT ps.shop_id, ps.user_id, ps.shop_name, si.item_name, si.qty, si.price, si.item_id, si.rarity "
            "FROM player_shops ps LEFT JOIN shop_inventory si ON ps.shop_id = si.shop_id "
            "WHERE ps.active = 1 AND si.item_type = ? ORDER BY si.price ASC",
            (self.cat,)
        ).fetchall()
        
        if not shops or not any(s['item_name'] for s in shops):
            await interaction.response.send_message(f"❌ No {self.label.lower()} in any player shops!", ephemeral=True)
            return
        
        listings = [s for s in shops if s['item_name']]
        
        # Generate preview image
        try:
            cheapest = min([l['price'] for l in listings]) if listings else 0
            preview = generate_category_preview(self.cat, len(listings), cheapest)
            file = discord.File(preview, filename="category_preview.png")
        except Exception as e:
            print(f"Image generation error: {e}")
            file = None
        
        desc = "\n".join(
            f"`#{s['item_id']}` {rarity_emoji(s['rarity'])} **{s['item_name']}** x{s['qty']} — 💰{s['price']} | <@{s['user_id']}>'s **{s['shop_name']}**"
            for s in listings[:15]
        )
        embed = discord.Embed(title=f"🏪 {self.label}", description=desc or "No items", color=discord.Colour.gold())
        embed.set_footer(text=f"Total: {len(listings)} items | Showing first 15")
        if file:
            embed.set_image(url="attachment://category_preview.png")
        
        await interaction.response.edit_message(embed=embed, view=PlayerShopItemSelectView(listings), file=file)


class PlayerShopItemSelectView(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=180)
        if items:
            self.add_item(PlayerShopItemSelect(items))


class PlayerShopItemSelect(discord.ui.Select):
    def __init__(self, items):
        self.items_map = {str(i['item_id']): i for i in items}
        options = [
            discord.SelectOption(
                label=f"{i['item_name']} x{i['qty']}",
                value=str(i['item_id']),
                description=f"💰 {i['price']} gold | {i['shop_name']}"[:100],
                emoji="💳"
            )
            for i in items[:25]
        ]
        super().__init__(placeholder="🛍️ Select item to buy…", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        item_id = int(self.values[0])
        item = self.items_map.get(str(item_id))
        if not item:
            await interaction.response.send_message("❌ Item not found!", ephemeral=True)
            return
        
        p = get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("❌ Create character first!", ephemeral=True)
            return
        
        if p["gold"] < item['price']:
            await interaction.response.send_message(f"❌ Need {item['price'] - p['gold']} more gold!", ephemeral=True)
            return
        
        # Generate item card
        file = None
        try:
            seller_name = db.execute("SELECT name FROM players WHERE user_id = ?", (item['user_id'],)).fetchone()
            seller_display = seller_name['name'] if seller_name else f"User#{item['user_id']}"
            item_power = db.execute("SELECT power FROM inventory WHERE user_id = ? AND item_name = ?", 
                                   (item['user_id'], item['item_name'])).fetchone()
            power_val = item_power['power'] if item_power else 0
            item_card = generate_item_card(item['item_name'], item['rarity'], item['item_type'], item['price'], seller_display, power_val)
            file = discord.File(item_card, filename="item_card.png")
        except Exception as e:
            print(f"Item card generation error: {e}")
        
        # Process purchase
        qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (item['price'], interaction.user.id))
        seller = get_player(item['user_id'])
        if seller:
            qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (item['price'], item['user_id']))
            mark_player_dirty(item['user_id'])
        
        add_item(interaction.user.id, item['item_name'], item['item_type'], item['rarity'], item['qty'])
        qexec("DELETE FROM shop_inventory WHERE item_id = ?", (item_id,))
        mark_player_dirty(interaction.user.id)
        
        embed = discord.Embed(
            title="✅ PURCHASE SUCCESSFUL!",
            description=f"You bought **{item['item_name']}** x{item['qty']} for {item['price']} gold from <@{item['user_id']}>!",
            color=discord.Colour.green()
        )
        embed.add_field(name="📦 Added to inventory", value="Check your items with `status`!", inline=False)
        if file:
            embed.set_image(url="attachment://item_card.png")
        
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)


class PlayerShopMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        categories = [
            ("⚔️ Weapons", "weapon"), ("🧪 Potions", "consumable"),
            ("🛡️ Armor", "armor"), ("💍 Accessories", "accessory"),
            ("🪨 Materials", "material"), ("❔ Other", "other")
        ]
        for i, (label, cat) in enumerate(categories):
            button = PlayerShopCategoryButton(label, cat, 0)
            button.row = i // 3
            self.add_item(button)


# ----- Shop / Pet / LootBox / Guild / Menu helpers + dropdowns -----

LOOT_BOXES = {"wood": 150, "iron": 450, "gold": 1200, "mythic": 5000, "legendary": 12000, "ascended": 50000}
LOOT_TABLE = {
    "common": ["herbs", "cloth", "iron ore", "copper ore"],
    "uncommon": ["silver bar", "leather", "ancient coin", "wolf fang"],
    "rare": ["void shard", "crystal", "dragon scale", "mana stone"],
    "epic": ["mythic core", "godly essence", "elder rune", "celestial fragment"],
    "mythic": ["void crystal", "legendary essence", "ancient tome"],
}


def buy_shop_item(user_id: int, item_name: str) -> Tuple[bool, str]:
    data = SHOP_ITEMS.get(item_name)
    if not data:
        return False, "Item not found in shop."
    p = get_player(user_id)
    if not p:
        return False, "Create a character first."
    if p["gold"] < data["price"]:
        return False, f"Need {data['price'] - p['gold']} more gold."
    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (data["price"], user_id))
    add_item(user_id, item_name, data["type"], data["rarity"], 1, data.get("power", 0), data["price"])
    mark_player_dirty(user_id)
    return True, f"Bought **{item_name}** for {data['price']} gold!"


def buy_merchant_item(user_id: int, item_name: str) -> Tuple[bool, str]:
    if item_name not in daily_merchant_stock():
        return False, "That item isn't in today's merchant stock. Try `market` for player listings."
    data = SHOP_ITEMS.get(item_name)
    if not data:
        return False, "Item not found."
    p = get_player(user_id)
    if not p:
        return False, "Create a character first."
    price = dynamic_price(item_name)
    if p["gold"] < price:
        return False, f"Need {price:,} gold (you have {p['gold']:,})."
    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (price, user_id))
    add_item(user_id, item_name, data["type"], data["rarity"], 1, data.get("power", 0), price)
    mark_player_dirty(user_id)
    return True, f"Bought **{item_name}** for {price:,} gold!"


def pvp_bonus(user_id: int) -> int:
    eq = db.execute("SELECT weapon, armor, accessory FROM equipment WHERE user_id = ?", (user_id,)).fetchone()
    if not eq:
        return 0
    total = 0
    for slot in ("weapon", "armor", "accessory"):
        nm = eq[slot]
        if nm:
            total += SHOP_ITEMS.get(nm, {}).get("pvp_power", 0)
    return total


class MerchantSelect(discord.ui.Select):
    def __init__(self, stock):
        options = []
        for nm in stock[:25]:
            d = SHOP_ITEMS.get(nm, {})
            options.append(discord.SelectOption(
                label=f"{nm} — {dynamic_price(nm):,}g"[:100],
                description=f"{d.get('type', 'item')} • +{d.get('power', 0)} pow • {d.get('rarity', 'common')}"[:100],
                emoji=rarity_emoji(d.get("rarity", "common")),
                value=nm,
            ))
        super().__init__(placeholder="🛒 Buy from today's merchant…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not get_player(interaction.user.id):
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        ok, msg = buy_merchant_item(interaction.user.id, self.values[0])
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class MerchantView(discord.ui.View):
    def __init__(self, stock):
        super().__init__(timeout=120)
        if stock:
            self.add_item(MerchantSelect(stock))


def adopt_pet(user_id: int, pet_key: str) -> Tuple[bool, str]:
    info = PETS.get(pet_key)
    if not info:
        return False, "Pet not found."
    p = get_player(user_id)
    if not p:
        return False, "Create a character first."
    if p["gold"] < info["cost"]:
        return False, f"Need {info['cost'] - p['gold']} more gold."
    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (info["cost"], user_id))
    qexec("INSERT INTO pets(user_id, pet_type, obtained_at) VALUES(?,?,?)", (user_id, pet_key, ts()))
    mark_player_dirty(user_id)
    return True, f"Adopted **{info['name']}**! ATK+{info['atk_bonus']} DEF+{info['def_bonus']}"


def open_lootbox(user_id: int, box_type: str) -> Tuple[bool, str]:
    price = LOOT_BOXES.get(box_type)
    if price is None:
        return False, "Unknown loot box."
    p = get_player(user_id)
    if not p:
        return False, "Create a character first."
    if p["gold"] < price:
        return False, f"Need {price - p['gold']} more gold."
    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (price, user_id))
    
    # Celestial Crystal Chance: 0.02% base, 0.5% for Ascended
    crystal_chance = 0.005 if box_type == "ascended" else 0.0002
    if random.random() < crystal_chance:
        add_item(user_id, "celestial crystal", "material", "chromatic", 1, 0, 0, 0, 100000)
        return True, "✨ 💠 **JACKPOT! You found a CELESTIAL CRYSTAL!** 💠 ✨"

    rarities = ["common", "uncommon", "rare", "epic", "mythic"]
    weights = [50, 30, 15, 4, 1] if box_type not in ["legendary", "ascended"] else [5, 10, 25, 40, 20]
    rarity = random.choices(rarities, weights=weights)[0]
    
    gear_chance = 0.80 if box_type == "ascended" else (0.45 if box_type in ("gold", "mythic", "legendary") else 0.30)
    if random.random() < gear_chance:
        _floor = {"wood": "common", "iron": "uncommon", "gold": "rare",
                  "mythic": "epic", "legendary": "legendary", "ascended": "mythic"}.get(box_type)
        _drop = grant_rich_drop(user_id, p["level"], p["zone"], floor=_floor)
        if _drop:
            mark_player_dirty(user_id)
            return True, f"Opened **{box_type}** box →\n{V.drop_banner(_drop)}"
    
    item = random.choice(LOOT_TABLE[rarity])
    add_item(user_id, item, "material", rarity, random.randint(1, 3))
    mark_player_dirty(user_id)
    return True, f"Opened **{box_type}** box → {rarity_emoji(rarity)} **{item}**!"


class ShopBuySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=f"{name} — {data['price']}g"[:100],
                description=f"{data.get('type', 'item')} • +{data.get('power', 0)} power • {data.get('rarity', 'common')}"[:100],
                emoji=rarity_emoji(data.get("rarity", "common")),
                value=name,
            )
            for name, data in list(SHOP_ITEMS.items())[:25]
        ]
        super().__init__(placeholder="🛒 Select an item to buy…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not get_player(interaction.user.id):
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        ok, msg = buy_shop_item(interaction.user.id, self.values[0])
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        if SHOP_ITEMS:
            self.add_item(ShopBuySelect())


class PetBuySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=f"{info['name']} — {info['cost']}g"[:100],
                description=f"ATK+{info['atk_bonus']} • DEF+{info['def_bonus']}"[:100],
                emoji="🐾",
                value=key,
            )
            for key, info in list(PETS.items())[:25]
        ]
        super().__init__(placeholder="🐾 Select a pet to adopt…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not get_player(interaction.user.id):
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        ok, msg = adopt_pet(interaction.user.id, self.values[0])
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class PetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        if PETS:
            self.add_item(PetBuySelect())


class LootBoxSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"{name.title()} box — {price}g"[:100], emoji="🎁", value=name)
            for name, price in LOOT_BOXES.items()
        ]
        super().__init__(placeholder="🎁 Select a loot box to open…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not get_player(interaction.user.id):
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        ok, msg = open_lootbox(interaction.user.id, self.values[0])
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class LootBoxView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(LootBoxSelect())


class GuildJoinSelect(discord.ui.Select):
    def __init__(self, guilds):
        options = [
            discord.SelectOption(
                label=g[1][:100],
                description=f"Tier {g[2]} • {g[3]} members"[:100],
                emoji="🏰",
                value=str(g[0]),
            )
            for g in guilds[:25]
        ]
        super().__init__(placeholder="🏰 Select a guild to join…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        p = get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        if p["guild_id"]:
            await interaction.response.send_message("❌ You're already in a guild! Use `guild leave` first.", ephemeral=True)
            return
        ok, msg = join_guild(interaction.user.id, int(self.values[0]))
        if ok and isinstance(interaction.user, discord.Member):
            g = db.execute("SELECT channel_id FROM guilds WHERE guild_id=?", (int(self.values[0]),)).fetchone()
            if g and g["channel_id"]:
                await grant_guild_channel_access(interaction.guild, g["channel_id"], interaction.user, True)
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class GuildJoinView(discord.ui.View):
    def __init__(self, guilds):
        super().__init__(timeout=120)
        if guilds:
            self.add_item(GuildJoinSelect(guilds))


MENU_CATEGORIES = {
    "⚔️ Combat": "`attack`, `boss`, `dungeon`, `duel [bet]`, `pvp`, `bounty`",
    "💰 Economy": "`shop`, `sell`, `market`, `astralshop` 💠, `daily`, `gamble [amount]`, `lootbox`",
    "🧍 Character": "`status`, `inventory`, `equip`, `class [name]`, `merge/apply [ench]`, `rebirth`, `prestige`",
    "⛏️ Gathering": "`fish`, `mine`, `craft`, `alchemy`, `quest`",
    "👥 Social": "`guild`, `team`, `lobby`, `trade @user`, `config`, `g.m`, `leaderboard daily/weekly/...`",
}


class MenuSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=k, description=v[:100], value=k) for k, v in MENU_CATEGORIES.items()]
        super().__init__(placeholder="📜 Pick a category to see commands…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        await interaction.response.send_message(f"**{cat} commands:**\n{MENU_CATEGORIES[cat]}", ephemeral=True)


class MenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(MenuSelect())


# ----- Enchanting dropdown + aesthetics helpers -----

RARITY_COLORS = {
    "common": 0x9E9E9E, "uncommon": 0x4CAF50, "rare": 0x2196F3,
    "epic": 0x9C27B0, "mythic": 0xFFD700, "secret": 0x37474F, "chromatic": 0xFF4081,
}


def rarity_color(rarity: str) -> "discord.Colour":
    return discord.Colour(RARITY_COLORS.get(rarity, 0x9E9E9E))


def level_color(level: int) -> "discord.Colour":
    if level >= 300:
        return discord.Colour(0xFF4081)
    if level >= 150:
        return discord.Colour(0xFFD700)
    if level >= 75:
        return discord.Colour(0x9C27B0)
    if level >= 25:
        return discord.Colour(0x2196F3)
    return discord.Colour(0x4CAF50)


def xp_bar(current: int, total: int, slots: int = 12) -> str:
    if total <= 0:
        total = 1
    return V.xp_bar(current, total, slots)


def enchant_item(user_id: int, item_name: str) -> Tuple[bool, str]:
    item = db.execute("SELECT * FROM inventory WHERE user_id = ? AND item_name = ?", (user_id, item_name)).fetchone()
    if not item:
        return False, "Item not found."
    if item["item_type"] not in EQUIPPABLE_TYPES:
        return False, "Only weapons, armor & accessories can be enchanted."
    lvl = get_enchant_level(item)
    if lvl >= ENCHANT_MAX:
        return False, f"**{item_name}** is already MAX ✦{ENCHANT_MAX}!"
    p = get_player(user_id)
    if not p:
        return False, "Create a character first."
    cost = enchant_cost(lvl)
    if p["gold"] < cost:
        return False, f"Need {cost:,} gold (✦{lvl}→✦{lvl + 1}). You have {p['gold']:,}."
    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (cost, user_id))
    mark_player_dirty(user_id)
    if random.random() < enchant_success_chance(lvl):
        bonus = (lvl + 1) * 2
        new_power = (item["power"] or 0) + bonus
        qexec("UPDATE inventory SET power = ?, enchantments = ? WHERE user_id = ? AND item_name = ?",
              (new_power, str(lvl + 1), user_id, item_name))
        return True, f"✨ **{item_name}** enchanted to ✦{lvl + 1}! (+{bonus} power → {new_power})"
    return False, f"💥 Enchant failed! **{item_name}** stays ✦{lvl}. Lost {cost:,} gold."


class EnchantSelect(discord.ui.Select):
    def __init__(self, owner_id: int, items):
        self.owner_id = owner_id
        options = []
        for i in items[:25]:
            lvl = get_enchant_level(i)
            if lvl >= ENCHANT_MAX:
                desc = f"✦{lvl} • MAXED"
            else:
                desc = f"✦{lvl}→✦{lvl + 1} • {enchant_cost(lvl):,}g • {int(enchant_success_chance(lvl) * 100)}%"
            options.append(discord.SelectOption(
                label=i["item_name"][:100],
                description=desc[:100],
                emoji=rarity_emoji(i["rarity"]),
                value=i["item_name"],
            ))
        super().__init__(placeholder="✨ Select gear to enchant…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your gear!", ephemeral=True)
            return
        ok, msg = enchant_item(self.owner_id, self.values[0])
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class EnchantView(discord.ui.View):
    def __init__(self, owner_id: int, items):
        super().__init__(timeout=120)
        if items:
            self.add_item(EnchantSelect(owner_id, items))


# ----- Staff (ADMIN/OWNER), moderation, server events -----

def is_staff(member) -> bool:
    try:
        names = {r.name for r in member.roles}
    except AttributeError:
        return False
    return ADMIN_ROLE_NAME in names or OWNER_ROLE_NAME in names


def fmt_secs(s: int) -> str:
    s = max(0, int(s))
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


async def _announce(guild, msg: str, ping: bool = False):
    if guild is None:
        return
    am = discord.AllowedMentions(everyone=True, roles=True) if ping else discord.AllowedMentions.none()
    for name in ("🎮-general", EVENTS_CHANNEL_NAME, "⚔️-combat"):
        ch = discord.utils.get(guild.text_channels, name=name)
        if ch:
            try:
                await ch.send(msg, allowed_mentions=am)
                return
            except discord.HTTPException:
                pass
    for ch in guild.text_channels:
        try:
            await ch.send(msg, allowed_mentions=am)
            return
        except discord.HTTPException:
            pass


async def announce_event_start(guild, info, duration):
    await _announce(
        guild,
        f"{updates_mention(guild)}\n{info['emoji']} **SERVER EVENT LIVE:** {info['name']}! {info['emoji']}\n⏳ Active for {fmt_secs(duration)} — go go go!",
        ping=True,
    )


def create_event(guild_id, key, start_at, end_at, created_by, status):
    info = EVENT_TYPES[key]
    qexec(
        "INSERT INTO server_events(guild_id,event_key,name,field,multiplier,status,start_at,end_at,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (guild_id, key, info["name"], info["field"], info["mult"], status, start_at, end_at, created_by, ts()),
    )


def get_active_multipliers(guild_id: int) -> dict:
    mult = {"xp": 1.0, "gold": 1.0, "luck": 1.0, "drops": 1.0}
    now = ts()
    rows = db.execute(
        "SELECT field, multiplier FROM server_events WHERE guild_id=? AND status='active' AND start_at<=? AND end_at>?",
        (guild_id, now, now),
    ).fetchall()
    for r in rows:
        f, m = r["field"], r["multiplier"]
        if f == "all":
            for k in mult:
                mult[k] = max(mult[k], m)
        elif f == "xpgold":
            mult["xp"] = max(mult["xp"], m)
            mult["gold"] = max(mult["gold"], m)
        elif f in mult:
            mult[f] = max(mult[f], m)
    return mult


def active_event_summary(guild_id: int) -> str:
    now = ts()
    rows = db.execute(
        "SELECT name, end_at FROM server_events WHERE guild_id=? AND status='active' AND start_at<=? AND end_at>? ORDER BY end_at",
        (guild_id, now, now),
    ).fetchall()
    return " • ".join(f"{r['name']} (ends in {fmt_secs(r['end_at'] - now)})" for r in rows)


async def add_warning(guild_id, user_id, mod_id, reason) -> int:
    qexec("INSERT INTO warnings(guild_id,user_id,mod_id,reason,created_at) VALUES(?,?,?,?,?)",
          (guild_id, user_id, mod_id, reason, ts()))
    row = db.execute("SELECT COUNT(*) AS c FROM warnings WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
    return row["c"]


class _EventTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=v["name"][:100], value=k, emoji=v["emoji"]) for k, v in list(EVENT_TYPES.items())[:25]]
        super().__init__(placeholder="🎲 Choose an event…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_key = self.values[0]
        await interaction.response.defer()


class _DurationSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=lbl, value=str(secs), emoji="⏳") for lbl, secs in EVENT_DURATIONS.items()]
        super().__init__(placeholder="⏳ Choose duration…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_duration = int(self.values[0])
        await interaction.response.defer()


class _DelaySelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=lbl, value=str(secs), emoji="🕒") for lbl, secs in PLAN_DELAYS.items()]
        super().__init__(placeholder="🕒 Start after…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_delay = int(self.values[0])
        await interaction.response.defer()


class EventBuilderView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.selected_key = None
        self.selected_duration = None
        self.add_item(_EventTypeSelect())
        self.add_item(_DurationSelect())

    @discord.ui.button(label="⏰ Set Update Countdown", style=discord.ButtonStyle.secondary)
    async def set_countdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        await interaction.response.send_modal(_CountdownModal(self.guild_id))

class _CountdownModal(discord.ui.Modal, title="⏰ Set Update Countdown"):
    time_str = discord.ui.TextInput(label="Time (e.g. 10m, 1h, 1h 30m)", placeholder="10m")
    
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        # Very simple parser for m/h/s
        import re
        parts = re.findall(r'(\d+)([mhs])', self.time_str.value)
        total_secs = sum(int(n) * {"s": 1, "m": 60, "h": 3600}[u] for n, u in parts)
        if total_secs <= 0:
            await interaction.response.send_message("❌ Invalid time format.", ephemeral=True)
            return
        
        # Create countdown channel
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="📢-ANNOUNCEMENTS")
        if not category:
            category = await guild.create_category("📢-ANNOUNCEMENTS")
        
        ch = await guild.create_text_channel("update-countdown", category=category)
        msg = await ch.send(f"⏳ **Update in:** {total_secs}s")
        
        # Start countdown loop
        async def countdown():
            for i in range(total_secs, 0, -1):
                await asyncio.sleep(1)
                try:
                    await msg.edit(content=f"⏳ **Update in:** {i}s")
                except discord.errors.NotFound:
                    break  # Message was deleted, stop countdown
            await msg.edit(content="🚀 **UPDATE LIVE!**")
            # Logic for update control button call would go here
        
        asyncio.create_task(countdown())
        await interaction.response.send_message(f"✅ Countdown started in {ch.mention}!", ephemeral=True)


class PlanningBuilderView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.selected_key = None
        self.selected_duration = None
        self.selected_delay = None
        self.add_item(_EventTypeSelect())
        self.add_item(_DurationSelect())
        self.add_item(_DelaySelect())

    @discord.ui.button(label="🗓️ Schedule Event", style=discord.ButtonStyle.primary)
    async def schedule(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        if not (self.selected_key and self.selected_duration and self.selected_delay):
            await interaction.response.send_message("❌ Pick event, duration AND start delay first.", ephemeral=True)
            return
        start_at = ts() + self.selected_delay
        create_event(self.guild_id, self.selected_key, start_at, start_at + self.selected_duration, interaction.user.id, "scheduled")
        info = EVENT_TYPES[self.selected_key]
        await interaction.response.send_message(
            f"✅ Scheduled **{info['name']}** to start in {fmt_secs(self.selected_delay)}, running {fmt_secs(self.selected_duration)}.",
            ephemeral=True,
        )


class UpdateBroadcastView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📢 Broadcast Update Warning", style=discord.ButtonStyle.danger, custom_id="broadcast_update_warning")
    async def broadcast(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        await interaction.response.send_message("📢 Broadcasting update warning to all channels…", ephemeral=True)
        warning = (
            "@everyone\n🔧 **UPDATE INCOMING** 🔧\n"
            "All channels will be **wiped and re-added** shortly.\n"
            "✅ Don't worry — your **loot, items, stats, gold, and guilds are saved in the local database**, so **nothing is lost**!\n"
            "We'll be back in a few minutes. 💜"
        )
        sent = 0
        for ch in interaction.guild.text_channels:
            try:
                await ch.send(warning, allowed_mentions=discord.AllowedMentions(everyone=True))
                sent += 1
            except discord.HTTPException:
                pass
        try:
            await interaction.followup.send(f"✅ Sent to {sent} channels.", ephemeral=True)
        except discord.HTTPException:
            pass


# ----- Astral Shards shop + trading UI -----

class CurrencyShopSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for nm, d in CURRENCY_GEAR.items():
            options.append(discord.SelectOption(
                label=f"{nm.title()} — 💠{d['shards']}"[:100],
                description=f"{d['rarity']} armor • +{d['power']} power"[:100],
                emoji="🛡️", value=f"gear:{nm}"))
        for fam in ENCHANT_FAMILIES:
            options.append(discord.SelectOption(
                label=f"{fam} T1 — 💠40"[:100],
                description="Custom enchant • merge 2→1 up to T7"[:100],
                emoji="🔮", value=f"ench:{fam}"))
        for ckey, ccost in CURRENCY_CLASS_UNLOCKS.items():
            options.append(discord.SelectOption(
                label=f"SECRET CLASS: {ckey.title()} — 💠{ccost}"[:100],
                description=CLASSES[ckey]["desc"][:100],
                emoji="🧬", value=f"class:{ckey}"))
        super().__init__(placeholder="💠 Buy gear / enchants / secret classes…", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if not get_player(uid):
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        kind, key = self.values[0].split(":", 1)
        if kind == "gear":
            d = CURRENCY_GEAR[key]
            if get_shards(uid) < d["shards"]:
                await interaction.response.send_message(f"❌ Need 💠{d['shards']} (you have 💠{get_shards(uid)}).", ephemeral=True)
                return
            spend_shards(uid, d["shards"])
            add_item(uid, key, d["type"], d["rarity"], 1, d["power"], 0)
            await interaction.response.send_message(f"✅ Bought **{key.title()}** for 💠{d['shards']}! Equip with `equip {key}`.", ephemeral=True)
        elif kind == "ench":
            if get_shards(uid) < 40:
                await interaction.response.send_message(f"❌ Need 💠40 (you have 💠{get_shards(uid)}).", ephemeral=True)
                return
            spend_shards(uid, 40)
            add_item(uid, enchant_item_name(key, 1), "enchant", "common", 1, 0, 80)
            await interaction.response.send_message(f"✅ Bought **{key} T1**! Get 2 and `merge {key} 1` → T2.", ephemeral=True)
        if kind == "class":
            cost = CURRENCY_CLASS_UNLOCKS.get(key, 999999)
            if inv_qty(uid, f"{key} tome") > 0:
                await interaction.response.send_message("❌ You already unlocked that class — use `class " + key + "`.", ephemeral=True)
                return
            if get_shards(uid) < cost:
                await interaction.response.send_message(f"❌ Need 💠{cost} (you have 💠{get_shards(uid)}).", ephemeral=True)
                return
            spend_shards(uid, cost)
            add_item(uid, f"{key} tome", "tome", "secret", 1, 0, 0)
            await interaction.response.send_message(f"✅ Unlocked the **{key.title()}** secret class! Switch with `class {key}`.", ephemeral=True)


class CurrencyRoleSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=f"{nm} — 💠{cost}"[:100], value=nm, description="Cosmetic Astral role")
                   for nm, (cost, col) in CURRENCY_ROLES.items()][:25]
        super().__init__(placeholder="💠 Buy a role with Astral Shards…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        uid = interaction.user.id
        nm = self.values[0]
        cost, col = CURRENCY_ROLES[nm]
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Use this in a server.", ephemeral=True)
            return
        member = interaction.user
        role = discord.utils.get(guild.roles, name=nm)
        if role and role in member.roles:
            await interaction.response.send_message("❌ You already own that role.", ephemeral=True)
            return
        if get_shards(uid) < cost:
            await interaction.response.send_message(f"❌ Need 💠{cost} (you have 💠{get_shards(uid)}).", ephemeral=True)
            return
        try:
            if role is None:
                role = await guild.create_role(name=nm, colour=discord.Colour(col), hoist=True, mentionable=False)
            await member.add_roles(role, reason="Astral Shards purchase")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I can't manage roles (need Manage Roles + a higher position).", ephemeral=True)
            return
        spend_shards(uid, cost)
        await interaction.response.send_message(f"✅ Unlocked **{nm}** for 💠{cost}!", ephemeral=True)


class CurrencyShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(CurrencyShopSelect())
        self.add_item(CurrencyRoleSelect())


async def post_trade_state(channel, sess):
    guild = channel.guild
    a, b = sess["a"], sess["b"]
    def _fmt(side):
        offs = sess["offers"].get(side, [])
        if not offs:
            return "_nothing yet_"
        return "\n".join(f"• {q}× **{n}** (worth {item_worth(n) * q:,})" for q, n in offs)
    ma, mb = guild.get_member(a), guild.get_member(b)
    na = ma.display_name if ma else str(a)
    nb = mb.display_name if mb else str(b)
    embed = discord.Embed(title="🤝 TRADE TABLE", color=discord.Colour(0x00BCD4))
    embed.add_field(name=f"{na} {'✅' if sess['accepted'].get(a) else '⌛'}",
                    value=_fmt(a) + f"\n**Total: {offer_worth(sess['offers'].get(a, [])):,}**", inline=True)
    embed.add_field(name=f"{nb} {'✅' if sess['accepted'].get(b) else '⌛'}",
                    value=_fmt(b) + f"\n**Total: {offer_worth(sess['offers'].get(b, [])):,}**", inline=True)
    embed.set_footer(text="`offer [items]` (commas or `xN name`) • `offer` for a menu • `accept` • `decline` • `cancel`")
    _tf = apply_theme(embed)
    await channel.send(embed=embed, file=_tf)


async def _delete_later(channel, delay):
    await asyncio.sleep(delay)
    try:
        await channel.delete(reason="Trade finished")
    except Exception:
        pass


class TradeOfferSelect(discord.ui.Select):
    def __init__(self, owner_id, items):
        self.owner_id = owner_id
        options = [discord.SelectOption(label=r["item_name"][:100], value=r["item_name"],
                   description=f"x{r['qty']} • worth {item_worth(r['item_name']):,}"[:100], emoji=rarity_emoji(r["rarity"]))
                   for r in items[:25]]
        super().__init__(placeholder="🎁 Select up to 6 items to offer…", min_values=1,
                         max_values=min(6, max(1, len(options))), options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your menu.", ephemeral=True)
            return
        sess = active_trades.get(interaction.channel.id)
        if not sess:
            await interaction.response.send_message("❌ Trade no longer active.", ephemeral=True)
            return
        sess["offers"][self.owner_id] = [[1, n.lower()] for n in self.values]
        sess["accepted"] = {sess["a"]: False, sess["b"]: False}
        await interaction.response.send_message("✅ Offer set! Both players must now `accept`.", ephemeral=True)
        await post_trade_state(interaction.channel, sess)


class TradeOfferView(discord.ui.View):
    def __init__(self, owner_id, items):
        super().__init__(timeout=180)
        if items:
            self.add_item(TradeOfferSelect(owner_id, items))


# ----- Profile config (ephemeral per-user panel) -----

class ProfileTitleSelect(discord.ui.Select):
    def __init__(self, member: discord.Member):
        is_staff = any(r.name in [ADMIN_ROLE_NAME, OWNER_ROLE_NAME] for r in member.roles)
        options = []
        for k, t in TITLES.items():
            role_name = f"✦ {t['name']}"
            has_role = discord.utils.get(member.roles, name=role_name)
            if is_staff or has_role:
                options.append(discord.SelectOption(label=f"[{t['tag']}] {t['name']}", value=k, description=f"{t['name']} name color"))
        
        options.append(discord.SelectOption(label="Clear title", value="none", emoji="🧼"))
        super().__init__(placeholder="🎨 Choose a name title…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not get_player(interaction.user.id):
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Use this in a server.", ephemeral=True)
            return
        ok, msg = await apply_title(interaction.user, self.values[0])
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class ProfileConfigView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=180)
        self.add_item(ProfileTitleSelect(member))

    @discord.ui.button(label="🤝 Toggle Tradeable", style=discord.ButtonStyle.secondary)
    async def toggle_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        new = 0 if p["tradeable"] else 1
        qexec("UPDATE players SET tradeable=? WHERE user_id=?", (new, interaction.user.id))
        mark_player_dirty(interaction.user.id)
        await interaction.response.send_message(
            f"🤝 Tradeable is now **{'ON' if new else 'OFF'}** — others {'can' if new else 'cannot'} open trades with you.",
            ephemeral=True)

    @discord.ui.button(label="🔔 Toggle Update Pings", style=discord.ButtonStyle.secondary)
    async def toggle_notify(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("❌ Create a character first!", ephemeral=True)
            return
        new = 0 if p["notify"] else 1
        qexec("UPDATE players SET notify=? WHERE user_id=?", (new, interaction.user.id))
        mark_player_dirty(interaction.user.id)
        if isinstance(interaction.user, discord.Member) and interaction.guild:
            try:
                role = discord.utils.get(interaction.guild.roles, name=UPDATES_ROLE_NAME)
                if role is None:
                    role = await interaction.guild.create_role(name=UPDATES_ROLE_NAME, colour=discord.Colour(0xFFCA28), mentionable=True)
                if new:
                    await interaction.user.add_roles(role, reason="opt-in updates")
                else:
                    await interaction.user.remove_roles(role, reason="opt-out updates")
            except discord.Forbidden:
                pass
        await interaction.response.send_message(
            f"🔔 Update pings are now **{'ON' if new else 'OFF'}** ({'you will' if new else 'you will NOT'} be pinged for events/updates).",
            ephemeral=True)


class GuildInviteView(discord.ui.View):
    def __init__(self, guild_id, guild_name, inviter_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.inviter_id = inviter_id

    @discord.ui.button(label="✅ Accept Invite", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        # Check if already in a guild
        p = get_player(user_id)
        if p and p["guild_id"]:
            await interaction.response.send_message("❌ You are already in a guild!", ephemeral=True)
            return
        
        # Join guild
        qexec("INSERT INTO guild_members(guild_id, user_id, rank, joined_at) VALUES(?,?,?,?)",
              (self.guild_id, user_id, "Member", ts()))
        qexec("UPDATE players SET guild_id = ? WHERE user_id = ?", (self.guild_id, user_id))
        qexec("UPDATE guilds SET member_count = member_count + 1 WHERE guild_id = ?", (self.guild_id,))
        mark_player_dirty(user_id)
        
        # Grant channel access
        grow = db.execute("SELECT channel_id FROM guilds WHERE guild_id=?", (self.guild_id,)).fetchone()
        if grow and grow["channel_id"] and isinstance(interaction.user, discord.Member):
            await grant_guild_channel_access(interaction.guild, grow["channel_id"], interaction.user, True)
            
        await interaction.response.edit_message(content=f"✅ You have joined **{self.guild_name}**!", view=None)

    @discord.ui.button(label="❌ Dismiss", style=discord.ButtonStyle.danger)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Invite dismissed.", view=None)

class TicketingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Open Guild Promotion Ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        owner_member = guild.get_member(1512122345165291731)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if owner_member:
            overwrites[owner_member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
        ch = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
        await ch.send(f"🎫 **New Promotion Ticket**\n\nUser: {interaction.user.mention}\nOwner: <@1512122345165291731>\n\nNegotiate the broadcast cost here!")
        await interaction.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)

async def ensure_ticketing_infrastructure(guild):
    cat = discord.utils.get(guild.categories, name="🎮 RPG REALM")
    if not cat: return
    
    ch_name = "🎫-ticketing"
    ch = discord.utils.get(guild.text_channels, name=ch_name)
    if not ch:
        ch = await guild.create_text_channel(ch_name, category=cat, topic="Open a ticket to promote your guild!")
        await ch.send("✨ **GUILD PROMOTION TICKET** ✨\n\nClick the button below to open a private ticket to negotiate a server-wide @everyone broadcast for your guild!", view=TicketingView())
    else:
        # Re-post button just in case
        await ch.purge(limit=5)
        await ch.send("✨ **GUILD PROMOTION TICKET** ✨\n\nClick the button below to open a private ticket to negotiate a server-wide @everyone broadcast for your guild!", view=TicketingView())

class ProfileConfigEntryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⚙️ Open My Profile Config", style=discord.ButtonStyle.primary, custom_id="open_profile_config")
    async def open_cfg(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("❌ Create a character first! Type `start warrior`.", ephemeral=True)
            return
        title = TITLES.get(p["title"], {}).get("name", "None") if p["title"] else "None"
        embed = discord.Embed(
            title="🪪 YOUR PROFILE CONFIG",
            color=discord.Colour(0x00BCD4),
            description="Only **you** can see this panel.\n• Pick a **name title** (color + `[TAG]`)\n• Toggle whether you're **tradeable**\n• Toggle **update pings**")
        embed.add_field(name="Current Title", value=title, inline=True)
        embed.add_field(name="Tradeable", value="ON" if p["tradeable"] else "OFF", inline=True)
        embed.add_field(name="Update Pings", value="ON" if p["notify"] else "OFF", inline=True)
        await interaction.response.send_message(embed=embed, view=ProfileConfigView(interaction.user), ephemeral=True)

async def ensure_guild_channel(guild, guild_id, guild_name):
    """Create/get private channel for a guild."""
    category = discord.utils.get(guild.categories, name="🏰 GUILDS")
    if category is None:
        category = await guild.create_category("🏰 GUILDS")
    
    # Clean name: "My Guild" -> "my-guild"
    ch_name = "".join(c if c.isalnum() else "-" for c in guild_name.lower()).strip("-")
    ch = discord.utils.get(guild.text_channels, name=ch_name)
    
    if ch is None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        ch = await guild.create_text_channel(ch_name, category=category, overwrites=overwrites, topic=f"Private chat for {guild_name}")
    
    qexec("UPDATE guilds SET channel_id = ? WHERE guild_id = ?", (ch.id, guild_id))
    return ch

def format_profile(p) -> discord.Embed:
    eq = get_equipment(p["user_id"])
    inv = get_inventory(p["user_id"])
    b = gear_bonuses(p["user_id"])
    es = effective_stats(p)
    power_score = int(es["atk"] * 2 + es["defense"] * 1.6 + es["max_hp"] * 0.25 + (p["crit"] or 0) * 1200)
    inv_str = ", ".join(
        f"{V.rarity_emoji(row['rarity'])} {row['item_name']} ×{row['qty']}" for row in inv[:6]
    ) or "Empty"

    embed = discord.Embed(
        title=f"{V.class_emoji(p['class_name'])} {p['name']} {V.class_emoji(p['class_name'])}",
        description=f"**{p['class_name'].upper()}** — Level {p['level']}  •  ⚡ Power **{V.fmt(power_score)}**",
        color=discord.Colour(V.rarity_color(V.RARITY_ORDER[min(len(V.RARITY_ORDER) - 1, p['level'] // 25)]))
    )

    embed.add_field(
        name="❤️ VITALS",
        value=f"{V.hp_color_bar(p['hp'], p['max_hp'])}\nHP: `{V.fmt(p['hp'])}/{V.fmt(p['max_hp'])}` | Mana: `{V.fmt(p['mana'])}/{V.fmt(p['max_mana'])}`",
        inline=False
    )

    def _bonus(tag):
        return f" `+{V.fmt(tag)}`🔥" if tag else ""
    embed.add_field(
        name="⚔️ COMBAT (base + gear)",
        value=(f"ATK: `{V.fmt(es['atk'])}`{_bonus(b['atk'])} | "
               f"DEF: `{V.fmt(es['defense'])}`{_bonus(b['def'])} | "
               f"CRIT: `{p['crit']*100:.1f}%`"),
        inline=False
    )
    
    embed.add_field(
        name="📊 PROGRESS",
        value=f"XP: `{p['xp']}` | Gold: `💰{p['gold']}` | Zone: `{p['zone'].upper()}`",
        inline=False
    )
    
    embed.add_field(
        name="⚰️ BATTLE RECORD",
        value=f"Kills: `{p['kills']}` | Deaths: `{p['deaths']}` | PvP: `{p['pvp_wins']}W-{p['pvp_losses']}L`",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ EQUIPMENT",
        value=f"⚔️ {eq['weapon'] or 'None'}\n🛡️ {eq['armor'] or 'None'}\n✨ {eq['accessory'] or 'None'}",
        inline=False
    )

    _set_labels = b.get("set_labels", [])
    if _set_labels:
        embed.add_field(name="🔗 SET BONUSES", value="\n".join(_set_labels), inline=False)

    embed.add_field(name="💼 INVENTORY", value=inv_str, inline=False)
    embed.add_field(name="📊 Rating", value=f"`{p['pvp_rating']}`", inline=True)
    embed.add_field(name="⏱️ Playtime", value=f"`{p['playtime_seconds']//60}m`", inline=True)
    
    return embed

def format_help() -> str:
    embed = discord.Embed(
        title="📜 RPG GUIDE 📜",
        description="═══════════════════════════════════",
        color=discord.Colour.gold()
    )
    embed.add_field(
        name="⚔️ COMBAT",
        value="**hunt** — Find an enemy\n**attack** — Deal damage\n**defend** — Reduce damage",
        inline=False
    )
    embed.add_field(
        name="💼 ITEMS",
        value="**inventory** — View items\n**shop** — Buy items\n**buy [item]** — Purchase",
        inline=False
    )
    embed.add_field(
        name="💰 ECONOMY",
        value="**daily** — Claim reward\n**gold** — Check balance\n**sell [item]** — Sell items",
        inline=False
    )
    embed.add_field(
        name="🎪 GACHA",
        value="**gacha** — See all tiers\n**gacha draw [tier]** — Pull items\nTiers: common, rare, epic, mythic, chromatic",
        inline=False
    )
    embed.add_field(
        name="⚔️ RIVALS & WAR",
        value="**rivals** — View rivals\n**rival add @user** — Add rival\n**clanwar** — Guild wars",
        inline=False
    )
    embed.add_field(
        name="🤝 TRADING",
        value="**trade @user** — Offer trade\n**trade accept** — Accept trade\n**trade rate @user [1-5]** — Rate player",
        inline=False
    )
    embed.add_field(
        name="📋 OTHER",
        value="**profile** — Character stats\n**season** — Battle pass\n**quest** — Daily quests\n**prestige** — Progression",
        inline=False
    )
    embed.add_field(
        name="✨ FORGE & FORTUNE",
        value="**reforge [item]** — Re-roll stats & affixes\n**salvage [item]** — Scrap for gold + stardust\n**codex** — Your live drop odds\n**gamble [amt]** — Slot machine\n**spin** — Free fortune wheel",
        inline=False
    )
    return embed

async def handle_message(message: discord.Message):
    """Handle all messages in RPG channel - pure chat-based."""
    if message.author.bot or not message.content:
        return
    
    content = message.content.lower().strip()
    
    # Auto-create player
    p = get_player(message.author.id)
    if not p:
        if "create" in content:
            parts = content.split()
            class_name = parts[1] if len(parts) > 1 else "warrior"
            if class_name not in CLASSES:
                class_name = "warrior"
            p = create_player(message.author, class_name)
            embed = discord.Embed(
                title="✨ CHARACTER CREATED ✨",
                description=f"Welcome, **{p['name']}**!",
                color=discord.Colour.gold()
            )
            embed.add_field(name="⚔️ Class", value=p['class_name'].upper(), inline=True)
            embed.add_field(name="❤️ HP", value=f"{p['hp']}/{p['max_hp']}", inline=True)
            embed.add_field(name="💎 Level", value="1", inline=True)
            await message.reply(embed=embed)
            return
        else:
            return
    
    # Profile/Status
    if any(word in content for word in ["profile", "status", "stats"]):
        await message.reply(format_profile(p))
        return
    
    # Help
    if "help" in content:
        await message.reply(format_help())
        return
    
    # Inventory
    if any(word in content for word in ["inventory", "inv", "bag", "items"]):
        inv = get_inventory(message.author.id)
        if not inv:
            embed = discord.Embed(title="💼 INVENTORY", description="Empty", color=discord.Colour.greyple())
            await message.reply(embed=embed)
            return
        inv_str = "\n".join(inventory_line(row) for row in inv)
        if len(inv_str) > 4000:
            inv_str = inv_str[:3990] + "\n…"
        _best = max(inv, key=lambda r: V.RARITY_RANK.get(r["rarity"], 0))
        _tot_pwr = sum((r["atk_bonus"] or 0) * 2 + (r["def_bonus"] or 0) * 2 + (r["hp_bonus"] or 0) // 4 for r in inv)
        embed = discord.Embed(title=f"💼 INVENTORY ({len(inv)} items)", description=inv_str,
                              color=discord.Colour(V.rarity_color(_best["rarity"])))
        embed.set_footer(text=f"⚡ Gear power {V.fmt(_tot_pwr)} • {V.power_rank_label(_tot_pwr)} • equip/reforge/salvage/inspect/compare <item>")
        await message.reply(embed=embed)
        return
    
    # Hunt
    if "hunt" in content:
        p = get_player(message.author.id)
        if not p:
            await message.reply("❌ Create character first")
            return
        if get_fight(message.author.id):
            await message.reply("🔥 Already in combat!")
            return
        
        enemy = make_enemy(p["level"], p["zone"])
        save_fight(message.author.id, enemy)
        embed = discord.Embed(
            title="⚔️ ENCOUNTER",
            description=f"🐾 **{enemy['name']}** appears!",
            color=discord.Colour.red()
        )
        embed.add_field(name="❤️ HP", value=f"{enemy['hp']}/{enemy['max_hp']}", inline=True)
        embed.add_field(name="⚔️ ATK", value=enemy['atk'], inline=True)
        embed.add_field(name="🛡️ DEF", value=enemy['def'], inline=True)
        await message.reply(embed=embed)
        return
    
    # Attack
    if "attack" in content:
        fight = get_fight(message.author.id)
        if not fight:
            await message.reply("❌ Not in combat! Say **hunt**")
            return

        p = get_player(message.author.id)
        es = effective_stats(p)
        eq = get_equipment(message.author.id)

        # element matchup (weapon element vs enemy element)
        player_elem = ""
        _wn = (eq.get("weapon") or "").lower()
        for _ek, _ev in V.ELEMENTS.items():
            if _ev["adj"].lower() in _wn:
                player_elem = _ek
                break
        enemy_elem = V.enemy_element(fight["enemy_name"])
        ematch = V.element_matchup(player_elem, enemy_elem) if player_elem else 1.0

        dmg = int(random.randint(int(es["atk"] * 0.8), int(es["atk"] * 1.2)) * ematch)
        if random.random() < es["crit"]:
            dmg = int(dmg * 1.5)
            crit_text = " 💥 **CRIT!**"
        else:
            crit_text = ""
        elem_tag = ""
        if player_elem and ematch > 1.0:
            elem_tag = f" {V.ELEMENTS[player_elem]['emoji']}💥super-effective"
        elif player_elem and ematch < 1.0:
            elem_tag = f" {V.ELEMENTS[player_elem]['emoji']}…resisted"

        # auto-cast class skill when mana fills
        skill_heal, skill_shield, skill_line = 0, 0.0, ""
        maxmana = p["max_mana"] or 1
        mana = min(maxmana, (p["mana"] or 0) + max(5, int(maxmana * 0.25)))
        if mana >= maxmana:
            sk = V.cast_skill(p["class_name"], es["atk"], fight["enemy_hp"], fight["enemy_max_hp"], player_elem, enemy_elem)
            dmg += sk["damage"]
            skill_heal, skill_shield = sk["heal"], sk["shield"]
            mana = 0
            skill_line = f"{sk['text']}"
        qexec("UPDATE players SET mana = ? WHERE user_id = ?", (mana, message.author.id))

        qexec("UPDATE fights SET enemy_hp = MAX(0, enemy_hp - ?), damage_dealt = damage_dealt + ? WHERE user_id = ?",
              (dmg, dmg, message.author.id))
        qexec("UPDATE players SET total_damage_dealt = total_damage_dealt + ? WHERE user_id = ?", (dmg, message.author.id))

        prev_hp = fight["enemy_hp"]
        fight = get_fight(message.author.id)

        if fight["enemy_hp"] <= 0:
            xp_gained = fight["enemy_xp"]
            gold_gained = fight["enemy_gold"]
            qexec("DELETE FROM fights WHERE user_id = ?", (message.author.id,))
            qexec("UPDATE players SET xp = xp + ?, gold = gold + ?, kills = kills + 1, total_gold_earned = total_gold_earned + ? WHERE user_id = ?",
                  (xp_gained, gold_gained, gold_gained, message.author.id))
            mark_player_dirty(message.author.id)
            embed = discord.Embed(
                title="🎉 VICTORY!",
                description=f"Defeated **{fight['enemy_name']}**! {skill_line}",
                color=discord.Colour.green()
            )
            embed.add_field(name="⭐ XP", value=f"+{V.fmt(xp_gained)}", inline=True)
            embed.add_field(name="💰 Gold", value=f"+{V.fmt(gold_gained)}", inline=True)
            embed.add_field(name="⚔️ Damage", value=f"{V.fmt(dmg)}{crit_text}", inline=True)
            if random.random() < 0.45:
                _drop = grant_rich_drop(message.author.id, p["level"], p["zone"])
                if _drop:
                    embed.add_field(name="🎁 Loot", value=V.drop_banner(_drop), inline=False)
            await message.reply(embed=embed)
        else:
            # boss multi-phase scaling + announce
            _oi, _, _ = V.boss_phase(prev_hp, fight["enemy_max_hp"])
            _ni, _plabel, _patk = V.boss_phase(fight["enemy_hp"], fight["enemy_max_hp"])
            raw = int(random.randint(int(fight["enemy_atk"] * 0.7), int(fight["enemy_atk"])) * _patk)
            if skill_shield:
                raw = int(raw * (1.0 - skill_shield))
            enemy_dmg = max(1, raw - int(es["defense"] * 0.5))
            cur_hp = min(es["max_hp"], (p["hp"] or 0) + skill_heal)
            new_hp = max(0, cur_hp - enemy_dmg)
            qexec("UPDATE players SET hp = ? WHERE user_id = ?", (new_hp, message.author.id))
            mark_player_dirty(message.author.id)

            _een = V.ELEMENTS.get(enemy_elem, {}).get("emoji", "")
            desc = f"You dealt **{V.fmt(dmg)}** damage{crit_text}{elem_tag}"
            if skill_line:
                desc += f"\n{skill_line}" + (f" (+{V.fmt(skill_heal)} HP)" if skill_heal else "") + (f" (🛡️ -{int(skill_shield*100)}%)" if skill_shield else "")
            if _ni > _oi and fight["enemy_max_hp"] >= 500:
                desc += "\n" + V.boss_phase_banner(fight["enemy_name"], _plabel, enemy_elem)
            embed = discord.Embed(title="⚔️ BATTLE", description=desc,
                                  color=discord.Colour(V.ELEMENTS.get(enemy_elem, {}).get("color", 0xE67E22)))
            embed.add_field(name=f"🐾 {fight['enemy_name']} {_een}",
                            value=f"{V.fmt(fight['enemy_hp'])}/{V.fmt(fight['enemy_max_hp'])} HP", inline=True)
            embed.add_field(name="💥 You took", value=f"**{V.fmt(enemy_dmg)}**", inline=True)
            embed.add_field(name="❤️ Your HP", value=f"{V.hp_color_bar(new_hp, es['max_hp'])}\n{V.fmt(new_hp)}/{V.fmt(es['max_hp'])}", inline=False)
            await message.reply(embed=embed)

        return
    
    # Shop
    if "shop" in content:
        def _shop_row(name):
            d = SHOP_ITEMS[name]
            icon = V.item_icon(name, d.get("type", ""), d.get("rarity", "common"))
            extra = []
            if d.get("power"):
                extra.append(f"⚡{V.fmt(d['power'])}")
            if d.get("heal"):
                extra.append(f"❤️+{V.fmt(d['heal'])}")
            tail = ("  " + " ".join(extra)) if extra else ""
            return f"{V.rarity_emoji(d['rarity'])} {icon} **{name}** — 💰{V.fmt(d['price'])}{tail}"
        shop_str = "\n".join(_shop_row(name) for name in list(SHOP_ITEMS.keys())[:12])
        embed = discord.Embed(title="🏪✨ WANDERING SHOP ✨🏪", description=shop_str, color=discord.Colour.gold())
        embed.set_footer(text="💎 Say 'buy [item]' to purchase • 'lootbox open <tier>' for a gamble 💎")
        emoji_anim = "🎪 ✨ 🎨 🎪 ✨ 🎨 🎪 ✨ 🎨" * 5
        await message.reply(f"{emoji_anim}", embed=embed)
        return
    
    # Buy
    if "buy" in content:
        p = get_player(message.author.id)
        item_name = content.replace("buy", "").strip().lower()
        if not item_name or item_name not in SHOP_ITEMS:
            await message.reply("❌ Item not found. Say **shop**")
            return
        item = SHOP_ITEMS[item_name]
        if p["gold"] < item["price"]:
            await message.reply(f"💸 Need {item['price'] - p['gold']} more gold")
            return
        qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (item["price"], message.author.id))
        add_item(message.author.id, item_name, item["type"], item["rarity"], 1, item.get("power", 0), item["price"])
        mark_player_dirty(message.author.id)
        emoji_anim = "🌟 💫 ⭐ 🌟 💫 ⭐ 🌟 💫 ⭐" * 5
        embed = discord.Embed(title="🛒✨ PURCHASED! ✨🛒", description=f"**{item_name.upper()}** for 💰💰{item['price']}💰💰", color=discord.Colour.green())
        embed.set_footer(text="🎉 Item added to inventory! 🎉")
        await message.reply(f"{emoji_anim}", embed=embed)
        return
    
    # Daily Reward
    if any(word in content for word in ["daily", "reward"]):
        p = get_player(message.author.id)
        if not p:
            await message.reply("❌ Create character first")
            return
        
        now = ts()
        if now - p["last_action"] < 3600:
            await message.reply("⏳ Try again in 1 hour")
            return
        
        daily_gold = 500 + (p["level"] * 50)
        daily_xp = 200 + (p["level"] * 20)
        
        qexec("UPDATE players SET gold = gold + ?, xp = xp + ?, last_action = ? WHERE user_id = ?", 
              (daily_gold, daily_xp, now, message.author.id))
        mark_player_dirty(message.author.id)
        
        embed = discord.Embed(title="🎁 DAILY REWARD!", color=discord.Colour.green())
        embed.add_field(name="💰 Gold", value=f"+{daily_gold}", inline=True)
        embed.add_field(name="⭐ XP", value=f"+{daily_xp}", inline=True)
        await message.reply(embed=embed)
        return
    
    # Equipment
    if cmd == "equipment":
        eq = get_equipment(message.author.id)
        await message.channel.send(f"**⚔️ EQUIPMENT**\nWeapon: {eq['weapon'] or 'None'}\nArmor: {eq['armor'] or 'None'}\nAccessory: {eq['accessory'] or 'None'}")
        return
    
    # Equip
    if cmd == "equip":
        item_name = " ".join(parts[1:]).lower().strip()
        if not item_name:
            await message.channel.send("Equip what?")
            return
        ok, msg = equip_item(message.author.id, item_name)
        await message.channel.send(("✅ " if ok else "❌ ") + msg)
        return
    
    # Shop
    if cmd == "shop":
        shop_str = "\n".join(f"  **{name}** - 💰{info['price']} | +{info.get('power', 0)}" 
                            for name, info in sorted(SHOP_ITEMS.items())[:15])
        await message.channel.send(f"**🏪 SHOP**\n{shop_str}\n\nUse: !buy [name]")
        return
    
    # Buy
    if cmd == "buy":
        item_name = " ".join(parts[1:]).lower().strip()
        if not item_name or item_name not in SHOP_ITEMS:
            await message.channel.send("Item not found. Use **!shop**")
            return
        item = SHOP_ITEMS[item_name]
        if p["gold"] < item["price"]:
            await message.channel.send(f"💰 Need {item['price'] - p['gold']} more gold")
            return
        qexec("UPDATE players SET gold = gold - ?, updated_at = ? WHERE user_id = ?", 
              (item["price"], ts(), message.author.id))
        add_item(message.author.id, item_name, item["type"], item["rarity"], 1, item.get("power", 0), item["price"])
        log_action(message.author.id, "BUY", item_name)
        mark_player_dirty(message.author.id)
        await message.channel.send(f"🛒 Bought **{item_name}** for 💰{item['price']}")
        return
    
    # Sell
    if cmd == "sell":
        if len(parts) < 2:
            await message.channel.send("Sell what?")
            return
        qty = 1
        try:
            qty = int(parts[-1])
            item_name = " ".join(parts[1:-1]).lower().strip()
        except ValueError:
            item_name = " ".join(parts[1:]).lower().strip()
        
        item = db.execute("SELECT * FROM inventory WHERE user_id = ? AND item_name = ?", 
                         (message.author.id, item_name)).fetchone()
        if not item or item["qty"] < qty:
            await message.channel.send("Don't have that item")
            return
        price = max(1, (item["value"] or 10) * qty // 2)
        remove_item(message.author.id, item_name, qty)
        qexec("UPDATE players SET gold = gold + ?, updated_at = ? WHERE user_id = ?", 
              (price, ts(), message.author.id))
        mark_player_dirty(message.author.id)
        await message.channel.send(f"💰 Sold **{item_name}** ×{qty} for 💰{price}")
        return
    
    # Hunt
    if cmd == "hunt":
        if get_fight(message.author.id):
            await message.channel.send("⚔️ Already in combat!")
            return
        zone = pick_zone(p["level"], p["zone"])
        enemy = make_enemy(p["level"], zone)
        save_fight(message.author.id, enemy)
        await message.channel.send(f"""🐾 **{enemy['name']}** appears in **{zone.upper()}**!
❤️ HP: {enemy['hp']}/{enemy['max_hp']}
⚔️ ATK: {enemy['atk']} | 🛡️ DEF: {enemy['def']}
Use: !attack | !skill | !defend | !run""")
        return
    
    # Attack
    if cmd == "attack":
        fight = get_fight(message.author.id)
        if not fight:
            await message.channel.send("Use **!hunt** first")
            return
        
        dmg = random.randint(p["atk"] - 3, p["atk"] + 5)
        is_crit = random.random() < p["crit"]
        if is_crit:
            dmg = int(dmg * 1.5)
            crit_msg = " 🎯 CRIT!"
        else:
            crit_msg = ""
        
        fight_hp = fight["enemy_hp"] - dmg
        
        if fight_hp <= 0:
            reward_xp = fight["enemy_xp"]
            reward_gold = fight["enemy_gold"]
            qexec("UPDATE players SET xp = xp + ?, gold = gold + ?, kills = kills + 1, updated_at = ? WHERE user_id = ?",
                  (reward_xp, reward_gold, ts(), message.author.id))
            
            # Level up check
            new_p = get_player(message.author.id)
            xp_needed = 100 * (new_p["level"] ** 1.5)
            if new_p["xp"] >= xp_needed:
                qexec("UPDATE players SET level = level + 1, xp = 0 WHERE user_id = ?", (message.author.id,))
                await message.channel.send(f"🎉 **LEVEL UP!** You are now level {new_p['level'] + 1}!")
            
            qexec("DELETE FROM fights WHERE user_id = ?", (message.author.id,))
            await message.channel.send(f"""⚔️ Dealt **{dmg}** damage{crit_msg}!
✨ **{fight['enemy_name']}** defeated!
Gained: **{reward_xp} XP** + **{reward_gold} gold**""")
            mark_player_dirty(message.author.id)
            mark_fight_dirty(message.author.id)
        else:
            enemy_dmg = random.randint(fight["enemy_atk"] - 2, fight["enemy_atk"] + 3)
            player_hp = p["hp"] - enemy_dmg
            
            if player_hp <= 0:
                qexec("DELETE FROM fights WHERE user_id = ?", (message.author.id,))
                qexec("UPDATE players SET deaths = deaths + 1, hp = ?, updated_at = ? WHERE user_id = ?", 
                      (p["max_hp"], ts(), message.author.id))
                await message.channel.send(f"💀 Took **{enemy_dmg}** damage and died! Respawning with full HP...")
                mark_player_dirty(message.author.id)
            else:
                qexec("UPDATE fights SET enemy_hp = ? WHERE user_id = ?", (fight_hp, message.author.id))
                qexec("UPDATE players SET hp = ? WHERE user_id = ?", (player_hp, message.author.id))
                await message.channel.send(f"""⚔️ Dealt **{dmg}** damage{crit_msg}!
💥 Enemy dealt **{enemy_dmg}** damage
HP: {player_hp}/{p['max_hp']}
Use: !attack | !defend | !run""")
                mark_player_dirty(message.author.id)
                mark_fight_dirty(message.author.id)
        return
    
    # Defend
    if cmd in {"defend", "block"}:
        fight = get_fight(message.author.id)
        if not fight:
            await message.channel.send("Use **!hunt** first")
            return
        qexec("UPDATE fights SET defending = 1 WHERE user_id = ?", (message.author.id,))
        await message.channel.send("🛡️ Defending! Damage reduced by 40%")
        mark_fight_dirty(message.author.id)
        return
    
    # Run
    if cmd in {"run", "flee", "escape"}:
        fight = get_fight(message.author.id)
        if not fight:
            await message.channel.send("Use **!hunt** first")
            return
        if random.random() < 0.5:
            qexec("DELETE FROM fights WHERE user_id = ?", (message.author.id,))
            await message.channel.send("🏃 Escaped successfully!")
            mark_fight_dirty(message.author.id)
        else:
            await message.channel.send("💨 Escape failed! Use !attack or !defend")
        return
    
    # Skill
    if cmd == "skill":
        fight = get_fight(message.author.id)
        if not fight:
            await message.channel.send("Use **!hunt** first")
            return
        if p["mana"] < 30:
            await message.channel.send("Not enough mana (need 30)")
            return
        
        dmg = int(p["atk"] * 1.8)
        qexec("UPDATE players SET mana = mana - 30 WHERE user_id = ?", (message.author.id,))
        qexec("UPDATE fights SET enemy_hp = MAX(0, enemy_hp - ?) WHERE user_id = ?", (dmg, message.author.id))
        
        fight = get_fight(message.author.id)
        if fight["enemy_hp"] <= 0:
            qexec("DELETE FROM fights WHERE user_id = ?", (message.author.id,))
            qexec("UPDATE players SET xp = xp + ?, gold = gold + ?, kills = kills + 1 WHERE user_id = ?",
                  (fight["enemy_xp"], fight["enemy_gold"], message.author.id))
            await message.channel.send(f"✨ Skill dealt **{dmg}** damage!\n✨ Enemy defeated!")
            mark_player_dirty(message.author.id)
        else:
            await message.channel.send(f"✨ Skill dealt **{dmg}** damage!\nEnemy HP: {fight['enemy_hp']}/{fight['enemy_max_hp']}")
            mark_player_dirty(message.author.id)
        return
    
    # Use
    if cmd == "use":
        item_name = parts[1].lower() if len(parts) > 1 else "potion"
        inv_item = db.execute("SELECT * FROM inventory WHERE user_id = ? AND item_name = ?", 
                             (message.author.id, item_name)).fetchone()
        if not inv_item or inv_item["qty"] < 1:
            await message.channel.send("Don't have that item")
            return
        
        if "potion" in item_name:
            heal = 60 if item_name == "potion" else 180 if item_name == "hi-potion" else 400
            hp = min(p["max_hp"], p["hp"] + heal)
            qexec("UPDATE players SET hp = ? WHERE user_id = ?", (hp, message.author.id))
            remove_item(message.author.id, item_name)
            await message.channel.send(f"🧪 Used **{item_name}**! HP: {hp}/{p['max_hp']}")
            mark_player_dirty(message.author.id)
        else:
            await message.channel.send("Can't use that here")
        return
    
    # Reforge — re-roll an item's stats & affixes
    if cmd == "reforge":
        _ok, _msg = reforge_item(message.author.id, " ".join(parts[1:]).lower().strip())
        await message.channel.send(_msg)
        return

    # Salvage — destroy gear for gold + stardust
    if cmd in ("salvage", "scrap", "dismantle"):
        _ok, _msg = salvage_item(message.author.id, " ".join(parts[1:]).lower().strip())
        await message.channel.send(_msg)
        return

    # Codex — live drop odds & rarity colors
    if cmd in ("codex", "odds", "rarities", "luck"):
        await message.reply(embed=build_codex_embed(message.author.id))
        return

    # Gamble — 3-reel slot machine
    if cmd in ("gamble", "slots", "bet"):
        await message.channel.send(gamble_gold(message.author.id, parts[1] if len(parts) > 1 else "0"))
        return

    # Spin — free fortune wheel
    if cmd in ("spin", "wheel", "fortune"):
        await message.channel.send(fortune_wheel(message.author.id))
        return

    # Inspect — full item card from your inventory
    if cmd in ("inspect", "examine", "view", "item"):
        _ok, _msg = inspect_item(message.author.id, " ".join(parts[1:]).lower().strip())
        await message.channel.send(_msg)
        return

    # Compare — candidate vs currently equipped in that slot
    if cmd in ("compare", "cmp", "vs"):
        _ok, _msg = compare_item(message.author.id, " ".join(parts[1:]).lower().strip())
        await message.channel.send(_msg)
        return

    # Gem exchange — buy gems with stardust
    if cmd in ("gem", "gems"):
        if len(parts) >= 3 and parts[1] in ("buy", "get"):
            _ok, _msg = buy_gem(message.author.id, parts[2])
            await message.channel.send(_msg)
        else:
            await message.channel.send(gem_shop_text())
        return

    # Socket — infuse a gem into a piece of gear: `socket <item> | <gem>`
    if cmd in ("socket", "infuse", "embed"):
        rest = " ".join(parts[1:])
        if "|" in rest:
            item_part, gem_part = rest.split("|", 1)
        else:
            bits = rest.rsplit(" ", 1)
            item_part, gem_part = (bits[0], bits[1]) if len(bits) == 2 else (rest, "")
        _ok, _msg = socket_gem(message.author.id, item_part.strip(), gem_part.strip())
        await message.channel.send(_msg)
        return


    # Explore
    if cmd == "explore":
        roll = random.random()
        if roll < 0.35:
            enemy = make_enemy(p["level"], p["zone"])
            save_fight(message.author.id, enemy)
            await message.channel.send(f"🌲 Found **{enemy['name']}**! Use !attack")
        elif roll < 0.60:
            gold = random.randint(25, 120) + p["level"] * 2
            qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (gold, message.author.id))
            mark_player_dirty(message.author.id)
            await message.channel.send(f"💰 Found **{gold} gold**!")
        elif roll < 0.82:
            if random.random() < 0.55:
                _drop = grant_rich_drop(message.author.id, p["level"], p["zone"])
                if _drop:
                    await message.channel.send(V.drop_banner(_drop))
                    return
            item_name, _, rarity, qty, _, _ = maybe_grant_loot(message.author.id, p["level"], p["zone"])
            await message.channel.send(f"{rarity_emoji(rarity)} Found **{item_name}** ×{qty}!")
        else:
            hp = min(p["max_hp"], p["hp"] + 8)
            mana = min(p["max_mana"], p["mana"] + 6)
            qexec("UPDATE players SET hp=?, mana=? WHERE user_id=?", (hp, mana, message.author.id))
            mark_player_dirty(message.author.id)
            await message.channel.send("🧭 Found a calm spot and recovered energy")
        return
    
    # Lootbox
    if cmd == "lootbox":
        if len(parts) < 3 or parts[1] != "open":
            await message.channel.send("Use: !lootbox open [wood|copper|iron|silver|gold|platinum|mythic|eternal|legendary|chromatic]")
            return
        
        box = parts[2].lower()
        if box not in LOOTBOXES:
            await message.channel.send("Invalid tier")
            return
        
        cost = LOOTBOXES[box]["price"]
        if p["gold"] < cost:
            await message.channel.send(f"Need {cost - p['gold']} more gold")
            return

        qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (cost, message.author.id))
        mark_player_dirty(message.author.id)

        # higher-tier boxes guarantee a higher minimum rarity
        tier = LOOTBOXES[box]["tier"]
        floor = ("common" if tier < 2 else "uncommon" if tier < 3 else "rare"
                 if tier < 4 else "epic" if tier < 5 else "legendary" if tier < 6 else "mythic")
        drop = grant_rich_drop(message.author.id, p["level"], p["zone"], floor=floor)
        if not drop:
            # fallback: a stack of materials if the catalog had nothing
            add_item(message.author.id, "void shard", "material", "rare", random.randint(2, 4), 0, 0, 0, 80)
            await message.channel.send("🎁 Got 🔵 **void shard**!")
            return

        # animated slot-machine reveal: post once, then edit through the frames
        frames = V.drop_reveal_frames(drop)
        header = f"🎁 Opening **{box.upper()}** box…"
        reveal = await message.channel.send(f"{header}\n{frames[0]}")
        for fr in frames[1:]:
            await asyncio.sleep(0.7)
            try:
                await reveal.edit(content=f"{header}\n{fr}")
            except Exception:
                pass
        return

    
    # Daily
    if cmd == "daily":
        now = ts()
        if now - p["last_action"] < 60:
            await message.channel.send("⏳ Try again soon")
            return
        reward = 300 + p["level"] * 20
        qexec("UPDATE players SET gold = gold + ?, last_action = ? WHERE user_id = ?", 
              (reward, now, message.author.id))
        mark_player_dirty(message.author.id)
        await message.channel.send(f"🎁 Daily reward: **{reward} gold**")
        return
    
    # Zone
    if cmd == "zone":
        zone = parts[1].lower() if len(parts) > 1 else None
        if not zone or zone not in ZONES:
            zones_str = ", ".join(ZONES.keys())
            await message.channel.send(f"Available zones: {zones_str}")
            return
        
        if ZONES[zone]["min_level"] > p["level"]:
            await message.channel.send(f"Need level {ZONES[zone]['min_level']} for {zone}")
            return
        
        qexec("UPDATE players SET zone = ? WHERE user_id = ?", (zone, message.author.id))
        mark_player_dirty(message.author.id)
        await message.channel.send(f"📍 Moved to **{zone.upper()}**")
        return
    
    # Guild
    if cmd == "guild":
        if len(parts) < 2:
            await message.channel.send("Use: !guild create [name] | !guild list | !guild join [id]")
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == "create":
            guild_name = " ".join(parts[2:]) if len(parts) > 2 else None
            if not guild_name:
                await message.channel.send("Provide guild name")
                return
            ok, msg = create_guild(message.author.id, guild_name)
            await message.channel.send(("✅ " if ok else "❌ ") + msg)
            return
        
        if subcmd == "list":
            guilds = list_guilds()
            if not guilds:
                await message.channel.send("No guilds yet")
                return
            guild_str = "\n".join(f"  **{g[1]}** (ID: {g[0]}) - Members: {g[3]}, Gold: {g[4]}" for g in guilds)
            await message.channel.send(f"**⚔️ GUILDS**\n{guild_str}")
            return
        
        if subcmd == "join":
            guild_id = int(parts[2]) if len(parts) > 2 else 0
            if guild_id <= 0:
                await message.channel.send("Invalid guild ID")
                return
            ok, msg = join_guild(message.author.id, guild_id)
            if ok:
                ok2, msg2 = create_character_for_guild(message.author.id, guild_id)
                await message.channel.send(("✅ " if ok else "❌ ") + msg + "\n" + ("✅ " if ok2 else "⚠️ ") + msg2)
            else:
                await message.channel.send("❌ " + msg)
            return
        
        if subcmd == "info":
            guild = db.execute("SELECT * FROM guilds WHERE guild_id = ?", 
                              (p["guild_id"],)).fetchone() if p["guild_id"] else None
            if not guild:
                await message.channel.send("You're not in a guild")
                return
            members = db.execute("SELECT COUNT(*) as count FROM guild_members WHERE guild_id = ?", 
                               (guild["guild_id"],)).fetchone()
            await message.channel.send(f"""**⚔️ {guild['guild_name']}**
Tier: {guild['tier']} | Level: {guild['level']}
Members: {members['count']} | Treasury: {guild['treasury']} gold""")
            return
    
    # Leaderboard
    if cmd == "leaderboard":
        stat = parts[1].lower() if len(parts) > 1 else "level"
        valid = ["level", "gold", "kills", "pvp_rating"]
        if stat not in valid:
            await message.channel.send(f"Stats: {', '.join(valid)}")
            return
        
        lb = db.execute(f"SELECT user_id, name, {stat} FROM players ORDER BY {stat} DESC LIMIT 10").fetchall()
        if not lb:
            await message.channel.send("No data")
            return
        
        lb_str = "\n".join(f"  {i+1}. **{row[1]}** - {row[2]}" for i, row in enumerate(lb))
        await message.channel.send(f"**🏆 {stat.upper()} LEADERBOARD**\n{lb_str}")
        return
    
    # Boss
    if cmd == "boss":
        if len(parts) < 2:
            await message.channel.send("Use: !boss list | !boss fight [name]")
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == "list":
            boss_list = "\n".join(f"  **{b['name']}** (Lvl {b['level']}, Min: {b['min_level']})" 
                                 for b in BOSSES.values())
            await message.channel.send(f"**⚔️ BOSSES**\n{boss_list}")
            return
        
        if subcmd == "fight":
            boss_key = parts[2] if len(parts) > 2 else ""
            if not boss_key or boss_key not in BOSSES:
                await message.channel.send("Boss not found. Use !boss list")
                return
            ok, msg = start_boss_fight(message.author.id, boss_key)
            await message.channel.send(("✅ " if ok else "❌ ") + msg)
            return
    
    # Crafting
    if cmd == "craft":
        if len(parts) < 2:
            await message.channel.send("Use: !craft list | !craft make [item]")
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == "list":
            craft_list = "\n".join(f"  **{name}** (Lvl {recipe['level']}) - {', '.join([f'{m[1]}x {m[0]}' for m in recipe['materials']])}"
                                  for name, recipe in CRAFTING_RECIPES.items())
            await message.channel.send(f"**🔨 RECIPES**\n{craft_list}")
            return
        
        if subcmd == "make":
            item = " ".join(parts[2:]) if len(parts) > 2 else ""
            if not item or item not in CRAFTING_RECIPES:
                await message.channel.send("Recipe not found. Use !craft list")
                return
            ok, msg = craft_item(message.author.id, item)
            await message.channel.send(("✅ " if ok else "❌ ") + msg)
            return
    
    # Pets
    if cmd == "pet":
        if len(parts) < 2:
            await message.channel.send("Use: !pet list | !pet buy [type] | !my pets")
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == "list":
            pet_list = "\n".join(f"  **{pet['name']}** - ATK+{pet['atk_bonus']} DEF+{pet['def_bonus']} (💰{pet['cost']})"
                                for pet in PETS.values())
            await message.channel.send(f"**🐾 PETS**\n{pet_list}")
            return
        
        if subcmd == "buy":
            pet_type = parts[2] if len(parts) > 2 else ""
            if not pet_type or pet_type not in PETS:
                await message.channel.send("Pet not found. Use !pet list")
                return
            ok, msg = buy_pet(message.author.id, pet_type)
            await message.channel.send(("✅ " if ok else "❌ ") + msg)
            return
        
        if subcmd == "my":
            pets = get_pets(message.author.id)
            if not pets:
                await message.channel.send("No pets yet")
                return
            pet_str = "\n".join(f"  **{PETS[p['pet_type']]['name']}** (Lvl {p['level']}, XP: {p['xp']})"
                               for p in pets)
            await message.channel.send(f"**🐾 MY PETS**\n{pet_str}")
            return
    
    # PvP
    if cmd == "pvp":
        if len(parts) < 2:
            await message.channel.send("Use: !pvp [player_name] | !pvp stats")
            return
        
        if parts[1] == "stats":
            await message.channel.send(f"""**⚔️ PVP STATS**
Wins: {p['pvp_wins']}
Losses: {p['pvp_losses']}
Rating: {p['pvp_rating']}""")
            return
        
        # Find opponent by name (simplified)
        opponent_name = " ".join(parts[1:])
        opponent = db.execute("SELECT * FROM players WHERE name LIKE ?", 
                             (f"%{opponent_name}%",)).fetchone()
        if not opponent:
            await message.channel.send("Player not found")
            return
        
        ok, msg = initiate_pvp(message.author.id, opponent["user_id"])
        await message.channel.send(("✅ " if ok else "❌ ") + msg)
        return
    
    # Dungeon
    if cmd == "dungeon":
        if len(parts) < 2:
            await message.channel.send("Use: !dungeon start [name] | !dungeon status")
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == "start":
            name = " ".join(parts[2:]) if len(parts) > 2 else "Abyss"
            ok, msg = start_dungeon(message.author.id, name)
            await message.channel.send(("✅ " if ok else "❌ ") + msg)
            return
        
        if subcmd == "status":
            dungeons = db.execute("SELECT * FROM dungeons WHERE user_id = ?", 
                                 (message.author.id,)).fetchall()
            if not dungeons:
                await message.channel.send("No active dungeons")
                return
            dung_str = "\n".join(f"  **{d['dungeon_name']}** - Floor {d['floor']}"
                                for d in dungeons)
            await message.channel.send(f"**📍 DUNGEONS**\n{dung_str}")
            return
    
    # Tournament
    if cmd == "tournament":
        if len(parts) < 2:
            await message.channel.send("Use: !tournament start")
            return
        
        if parts[1] == "start":
            if not p["guild_id"]:
                await message.channel.send("Join a guild first")
                return
            ok, msg = start_tournament(p["guild_id"])
            await message.channel.send(("✅ " if ok else "❌ ") + msg)
            return
    
    # Character management
    if cmd == "character":
        if len(parts) < 2:
            chars = db.execute("SELECT * FROM characters WHERE user_id = ?", (message.author.id,)).fetchall()
            if not chars:
                await message.channel.send("❌ No characters yet. Join a guild!")
                return
            char_list = "\n".join(f"  **{c['char_name']}** (Lvl {c['level']}, Guild ID: {c['guild_id']})" for c in chars)
            await message.channel.send(f"**📋 YOUR CHARACTERS**\n{char_list}")
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == "level":
            if not p["guild_id"]:
                await message.channel.send("❌ Join a guild first")
                return
            char = db.execute("SELECT * FROM characters WHERE user_id = ? AND guild_id = ?",
                            (message.author.id, p["guild_id"])).fetchone()
            if not char:
                await message.channel.send("❌ No character in current guild")
                return
            await message.channel.send(f"📊 **{char['char_name']}** - Level: **{char['level']}**")
            return
    
    # Leaderboards
    if cmd == "leaderboard":
        if not p["guild_id"]:
            await message.channel.send("❌ Join a guild first")
            return
        
        stat = parts[1].lower() if len(parts) > 1 else "level"
        lb = get_guild_leaderboard(p["guild_id"], stat, 10)
        
        if not lb:
            await message.channel.send(f"❌ No data for {stat}")
            return
        
        lb_str = "\n".join(f"  {i+1}. <@{user_id}> - {value}" for i, (user_id, value) in enumerate(lb))
        await message.channel.send(f"**🏆 GUILD LEADERBOARD - {stat.upper()}**\n{lb_str}")
        return
    
    # Channel access control
    if cmd == "access":
        if len(parts) < 2:
            await message.channel.send("Use: !access check | !access grant [user] [channel] | !access revoke [user] [channel]")
            return
        
        subcmd = parts[1].lower()
        guild = message.guild
        
        if subcmd == "check":
            perms = db.execute("SELECT * FROM guild_permissions WHERE guild_id = ? AND user_id = ?",
                             (guild.id, message.author.id)).fetchall()
            if not perms:
                await message.channel.send("❌ No special permissions")
                return
            perm_str = "\n".join(f"  • {p['permission_type']} - {p['access_level']}" for p in perms)
            await message.channel.send(f"**🔐 YOUR PERMISSIONS**\n{perm_str}")
            return
        
        if subcmd == "grant" and len(parts) >= 4:
            member_name = parts[2]
            channel_name = parts[3]
            member = discord.utils.get(guild.members, name=member_name)
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            
            if not member or not channel:
                await message.channel.send("❌ Member or channel not found")
                return
            
            grant_channel_access(guild.id, member.id, channel.id, 'member')
            await message.channel.send(f"✅ Granted {member.name} access to {channel.name}")
            return
        
        if subcmd == "revoke" and len(parts) >= 4:
            member_name = parts[2]
            channel_name = parts[3]
            member = discord.utils.get(guild.members, name=member_name)
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            
            if not member or not channel:
                await message.channel.send("❌ Member or channel not found")
                return
            
            revoke_channel_access(guild.id, member.id, channel.id)
            await message.channel.send(f"✅ Revoked {member.name}'s access to {channel.name}")
            return
    
    # Season/Battle Pass
    if cmd == "season":
        if len(parts) < 2:
            season = db.execute("SELECT * FROM seasons WHERE user_id = ? ORDER BY season_number DESC LIMIT 1",
                             (message.author.id,)).fetchone()
            if not season:
                await message.channel.send("❌ Not in any season. !season start")
                return
            await message.channel.send(f"""**⭐ CURRENT SEASON**
Season: {season['season_number']}
Tier: {season['tier']}
XP: {season['tier_xp']}/1000""")
            return
        
        if parts[1].lower() == "start":
            last = db.execute("SELECT season_number FROM seasons WHERE user_id = ? ORDER BY season_number DESC LIMIT 1",
                            (message.author.id,)).fetchone()
            new_season = (last['season_number'] + 1) if last else 1
            
            qexec("INSERT INTO seasons(user_id, season_number, tier, tier_xp, created_at) VALUES(?,?,?,?,?)",
                  (message.author.id, new_season, 0, 0, ts()))
            await message.channel.send(f"✅ Started Season {new_season}!")
            return
    
    # Quest system
    if cmd == "quest":
        if len(parts) < 2:
            quests = db.execute("SELECT * FROM quests WHERE user_id = ? AND completed = 0", (message.author.id,)).fetchall()
            if not quests:
                await message.channel.send("❌ No active quests. !quest new")
                return
            quest_str = "\n".join(f"  **{q['quest_name']}** ({q['progress']}/{q['target']})" for q in quests)
            await message.channel.send(f"**📜 ACTIVE QUESTS**\n{quest_str}")
            return
        
        if parts[1].lower() == "new":
            quest_types = ["hunt", "gather", "defeat"]
            qtype = random.choice(quest_types)
            target = random.randint(5, 20)
            
            qexec("INSERT INTO quests(user_id, quest_type, quest_name, target, reward_gold, reward_xp, created_at) VALUES(?,?,?,?,?,?,?)",
                  (message.author.id, qtype, f"Complete {target} {qtype}s", target, target*50, target*100, ts()))
            await message.channel.send(f"✅ New quest: Complete **{target}** {qtype}s\nReward: {target*50} gold, {target*100} xp")
            return
    
    # Gacha/Collections
    if cmd == "gacha":
        if len(parts) < 2:
            collections = db.execute("SELECT COUNT(*) as cnt FROM collections WHERE user_id = ?",
                                   (message.author.id,)).fetchone()
            await message.channel.send(f"📦 You have collected **{collections['cnt']}** unique items. !gacha pull to get more!")
            return
        
        if parts[1].lower() == "pull":
            cost = 100
            if p["gold"] < cost:
                await message.channel.send(f"❌ Need {cost} gold!")
                return
            
            rarities = ["common", "uncommon", "rare", "epic", "mythic", "secret", "chromatic"]
            weights = [35, 30, 15, 10, 5, 3, 2]
            rarity = random.choices(rarities, weights=weights)[0]
            
            loot_items = {
                "common": ["Copper Coin", "Wooden Badge", "Iron Dust"],
                "uncommon": ["Silver Coin", "Bronze Medal", "Steel Fragment"],
                "rare": ["Gold Coin", "Diamond", "Crystal Shard"],
                "epic": ["Cosmic Gem", "Void Essence", "Mythril Ingot"],
                "mythic": ["Eternal Flame", "Divine Artifact", "Ancient Relic"],
                "secret": ["Shadow Heart", "Hidden Scroll", "Obscure Tome"],
                "chromatic": ["Prism Essence", "Multicolor Core", "Rainbow Fragment"],
            }
            
            item = random.choice(loot_items[rarity])
            qexec("INSERT OR IGNORE INTO collections(user_id, item_name, rarity, times_pulled, created_at) VALUES(?,?,?,?,?)",
                  (message.author.id, item, rarity, 1, ts()))
            qexec("UPDATE collections SET times_pulled = times_pulled + 1 WHERE user_id = ? AND item_name = ?",
                  (message.author.id, item))
            qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (cost, message.author.id))
            mark_player_dirty(message.author.id)
            
            await message.channel.send(f"🎪 Pulled **{rarity_emoji(rarity)} {item}**!")
            return
    
    # Rivals
    if cmd == "rival":
        if len(parts) < 2:
            rivals = get_rivals(message.author.id)
            if not rivals:
                await message.channel.send("❌ No rivals yet! Defeat players in PvP!")
                return
            rival_str = "\n".join(f"  {i+1}. <@{rid}> - Score: {score} (H2H: {h2h})" 
                                 for i, (rid, score, h2h) in enumerate(rivals))
            await message.channel.send(f"**⚔️ YOUR RIVALS**\n{rival_str}")
            return
        
        if parts[1].lower() == "add":
            rival_name = " ".join(parts[2:]) if len(parts) > 2 else None
            if not rival_name:
                await message.channel.send("❌ Specify rival name")
                return
            rival = db.execute("SELECT * FROM players WHERE name LIKE ?", (f"%{rival_name}%",)).fetchone()
            if not rival or rival['user_id'] == message.author.id:
                await message.channel.send("❌ Player not found")
                return
            
            if add_rival(message.author.id, rival['user_id']):
                await message.channel.send(f"⚔️ **{rival['name']}** is now your rival!")
            else:
                await message.channel.send("❌ Already rivals")
            return
    
    # Clan Wars
    if cmd == "clanwar":
        if not p["guild_id"]:
            await message.channel.send("❌ Join a guild first")
            return
        
        if len(parts) < 2:
            wars = get_active_clan_wars(p["guild_id"])
            if not wars:
                await message.channel.send("❌ No active clan wars")
                return
            war_str = "\n".join(f"  War {w['war_id']}: Score {w['attacker_score']}-{w['defender_score']}" for w in wars)
            await message.channel.send(f"**⚔️ CLAN WARS**\n{war_str}")
            return
        
        if parts[1].lower() == "start":
            enemy_guild_id = int(parts[2]) if len(parts) > 2 else 0
            if enemy_guild_id <= 0:
                await message.channel.send("❌ Specify enemy guild ID")
                return
            
            ok, msg = start_clan_war(p["guild_id"], enemy_guild_id)
            await message.channel.send(("✅ " if ok else "❌ ") + msg)
            return
    
    # Advanced Trading
    if cmd == "trade":
        if len(parts) < 2:
            await message.channel.send("Use: !trade offer [player] [items...] | !trade accept [id] | !trade rate [player] [1-5]")
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == "offer":
            player_name = parts[2] if len(parts) > 2 else None
            if not player_name:
                await message.channel.send("❌ Specify player")
                return
            
            target = db.execute("SELECT * FROM players WHERE name LIKE ?", (f"%{player_name}%",)).fetchone()
            if not target or target['user_id'] == message.author.id:
                await message.channel.send("❌ Player not found")
                return
            
            trade_items = parts[3:] if len(parts) > 3 else ["gold"]
            ok, trade_id = create_trade_offer(message.author.id, target['user_id'], trade_items, [])
            if ok:
                await message.channel.send(f"📦 Trade offer sent to {target['name']} (ID: {trade_id})")
            else:
                await message.channel.send("❌ Cannot create trade")
            return
        
        if subcmd == "accept":
            trade_id = int(parts[2]) if len(parts) > 2 else 0
            if trade_id <= 0:
                await message.channel.send("❌ Invalid trade ID")
                return
            
            ok, msg = accept_trade(trade_id)
            await message.channel.send(("✅ " if ok else "❌ ") + msg)
            return
        
        if subcmd == "rate":
            player_name = parts[2] if len(parts) > 2 else None
            rating = int(parts[3]) if len(parts) > 3 else 5
            if not player_name:
                await message.channel.send("❌ Specify player")
                return
            
            target = db.execute("SELECT * FROM players WHERE name LIKE ?", (f"%{player_name}%",)).fetchone()
            if not target:
                await message.channel.send("❌ Player not found")
                return
            
            if rate_trader(message.author.id, target['user_id'], rating):
                await message.channel.send(f"⭐ Rated {target['name']} {rating}/5")
            return
    
    # Gacha Shop Tiers
    if "gacha" in content:
        p = get_player(message.author.id)
        if not p:
            await message.reply("❌ Create character first")
            return
        
        if "shop" in content or "tiers" in content or "draw" not in content:
            embed = discord.Embed(
                title="🎪 GACHA SHOP 🎪",
                description="═══════════════════════════════════",
                color=discord.Colour.magenta()
            )
            embed.add_field(
                name="⚪ COMMON DRAW — 100 💰",
                value="40% Common | 35% Uncommon | 15% Rare | 8% Epic | 2% Mythic",
                inline=False
            )
            embed.add_field(
                name="🟢 RARE DRAW — 500 💰",
                value="20% Uncommon | 40% Rare | 25% Epic | 12% Mythic | 3% Secret",
                inline=False
            )
            embed.add_field(
                name="🟣 EPIC DRAW — 2000 💰",
                value="15% Rare | 35% Epic | 30% Mythic | 15% Secret | 5% Chromatic",
                inline=False
            )
            embed.add_field(
                name="🌟 MYTHIC DRAW — 8000 💰",
                value="10% Epic | 25% Mythic | 35% Secret | 25% Chromatic | 5% CELESTIAL ✨",
                inline=False
            )
            embed.add_field(
                name="🌈 CHROMATIC DRAW — 25000 💰",
                value="100% Guaranteed Secret/Chromatic/Celestial 🔮",
                inline=False
            )
            embed.set_footer(text="Say 'gacha draw [tier]' to pull (common/rare/epic/mythic/chromatic)")
            await message.reply(embed=embed)
            return
        
        # Parse draw tier
        tier = "common"
        for t in ["chromatic", "mythic", "epic", "rare"]:
            if t in content:
                tier = t
                break
        
        tier_config = {
            "common": {"cost": 100, "weights": [40, 35, 15, 8, 2, 0, 0], "emoji": "⚪"},
            "rare": {"cost": 500, "weights": [0, 20, 40, 25, 12, 3, 0], "emoji": "🟢"},
            "epic": {"cost": 2000, "weights": [0, 0, 15, 35, 30, 15, 5], "emoji": "🟣"},
            "mythic": {"cost": 8000, "weights": [0, 0, 0, 10, 25, 35, 25], "emoji": "🌟"},
            "chromatic": {"cost": 25000, "weights": [0, 0, 0, 0, 5, 50, 45], "emoji": "🌈"},
        }
        
        if tier not in tier_config:
            tier = "common"
        
        cfg = tier_config[tier]
        if p["gold"] < cfg["cost"]:
            await message.reply(f"💸 Need {cfg['cost'] - p['gold']} more gold for {tier.upper()} draw")
            return
        
        rarities = ["common", "uncommon", "rare", "epic", "mythic", "secret", "chromatic"]
        rarity = random.choices(rarities, weights=cfg["weights"])[0]
        
        loot_items = {
            "common": ["Copper Coin", "Wooden Badge", "Iron Dust", "Tin Ore"],
            "uncommon": ["Silver Coin", "Bronze Medal", "Steel Fragment", "Quartz"],
            "rare": ["Gold Coin", "Diamond", "Crystal Shard", "Emerald"],
            "epic": ["Cosmic Gem", "Void Essence", "Mythril Ingot", "Opal"],
            "mythic": ["Eternal Flame", "Divine Artifact", "Ancient Relic", "Moonstone"],
            "secret": ["Shadow Heart", "Hidden Scroll", "Obscure Tome", "Void Whisper"],
            "chromatic": ["Prism Essence", "Multicolor Core", "Rainbow Fragment", "Celestial Shard"],
        }
        
        item = random.choice(loot_items[rarity])
        qexec("INSERT OR IGNORE INTO collections(user_id, item_name, rarity, times_pulled, created_at) VALUES(?,?,?,?,?)",
              (message.author.id, item, rarity, 1, ts()))
        qexec("UPDATE collections SET times_pulled = times_pulled + 1 WHERE user_id = ? AND item_name = ?",
              (message.author.id, item))
        qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (cfg["cost"], message.author.id))
        mark_player_dirty(message.author.id)
        
        embed = discord.Embed(
            title=f"{cfg['emoji']} {tier.upper()} DRAW {cfg['emoji']}",
            description=f"{rarity_emoji(rarity)} **{item}** {rarity_emoji(rarity)}",
            color=discord.Colour.magenta()
        )
        embed.add_field(name="Rarity", value=rarity.upper(), inline=True)
        embed.add_field(name="Cost", value=f"💰 {cfg['cost']}", inline=True)
        await message.reply(embed=embed)
        return
# SERVER SETUP - FIRST RUN ONLY
# ============================================================================

async def setup_server():
    """FULL aesthetic setup - DELETE ALL and create FRESH & BEAUTIFUL"""
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        print("\n⚠️  INVITE BOT TO YOUR SERVER FIRST!")
        return None
    
    print(f"\n🗑️  WIPING SERVER CLEAN...")
    SERVER_PATH.write_text(str(guild.id))
    
    try:
        # 1. DELETE
        protected_channel_ids = set()
        if getattr(guild, "rules_channel", None):
            protected_channel_ids.add(guild.rules_channel.id)
        if getattr(guild, "public_updates_channel", None):
            protected_channel_ids.add(guild.public_updates_channel.id)

        for channel in list(guild.channels):
            if channel.id in protected_channel_ids:
                print(f"Skipping protected community channel: {channel.name}")
                continue

            name_lower = channel.name.lower()
            if any(x in name_lower for x in ("announcement", "announcements", "changelog", "change-log", "updates")):
                print(f"Skipping announcement/changelog channel: {channel.name}")
                continue
                print(f"Skipping protected community channel: {channel.name}")
                continue

            try:
                await channel.delete()
                await asyncio.sleep(0.5)
            except discord.errors.NotFound:
                pass  # Already deleted
            except discord.HTTPException as e:
                if getattr(e, "code", None) == 50074:
                    print(f"Skipping protected community channel: {channel.name}")
                    continue
                raise
        for category in list(guild.categories):
            try:
                await category.delete()
                await asyncio.sleep(0.5)
            except discord.errors.NotFound:
                pass  # Already deleted
        for role in list(guild.roles):
            if getattr(role, "managed", False):
                continue
            if getattr(role, "is_default", lambda: False)():
                continue
            if hasattr(guild, "me") and role >= guild.me.top_role:
                continue

            if role.name not in ["@everyone"]:
                try:
                    try:
                    await role.delete()
                except discord.Forbidden:
                    print(f"Skipping role (missing permissions): {role.name}")
                    continue
                except discord.HTTPException:
                    continue
                    await asyncio.sleep(0.5)
                except discord.errors.NotFound:
                    pass  # Already deleted
        
        # 2. CREATE BASE
        roles_to_create = [
            ("Elite Player", discord.Colour.gold()), ("Adventurer", discord.Colour.purple()),
            ("Warrior", discord.Colour.red()), ("Mage", discord.Colour.blue()),
            ("Rogue", discord.Colour.dark_gray()), ("Paladin", discord.Colour.light_gray()),
            ("Ranger", discord.Colour.green()), ("Druid", discord.Colour.dark_green()),
        ]
        for name, color in roles_to_create:
            await guild.create_role(name=name, color=color, mentionable=True)
        
        category = await guild.create_category("🎮 RPG REALM")
        channels = [
            ("🎮-general", "Chat, quests, announcements"), ("⚔️-combat", "Battle reports"),
            ("🏪-shop", "Buy & sell"), ("🗺️-explore", "Zones"),
            ("💰-economy", "Market"), ("👥-guilds", "Guilds"),
            ("🏆-leaderboards", "Rankings"), ("💎-loot", "Drops"),
            ("📖-guide", "Guide"), ("🎪-events", "Events"),
        ]
        for ch_name, topic in channels:
            await guild.create_text_channel(ch_name, category=category, topic=topic)
            
        # 3. RESTORE INFRASTRUCTURE
        print("Restoring infrastructure...")
        await ensure_staff_infrastructure(guild)
        await ensure_profile_infrastructure(guild)
        await ensure_info_infrastructure(guild)
        await ensure_world_infrastructure(guild)
        await ensure_chat_channel(guild)
        print("Infrastructure restored.")
            
        print(f"\n✅ Server '{guild.name}' rebuilt.")
        
    except Exception as e:
        print(f"Setup error: {e}")
        import traceback
        traceback.print_exc()
    
    return guild

@tasks.loop(minutes=5)
async def guild_stats_loop():
    """Recalculate guild power and influence based on member stats."""
    guilds = db.execute("SELECT guild_id FROM guilds").fetchall()
    for g in guilds:
        gid = g["guild_id"]
        # Total Power = Sum of member levels + ATK + DEF
        stats = db.execute("SELECT SUM(level + atk + defense) as power FROM players WHERE guild_id = ?", (gid,)).fetchone()
        power = stats["power"] or 0
        qexec("UPDATE guilds SET total_power = ? WHERE guild_id = ?", (power, gid))

@tasks.loop(hours=1)
async def hourly_pact_processor():
    """Deduct pact costs from guild treasuries every hour."""
    pacts = db.execute("SELECT * FROM guild_pacts WHERE status = 'active'").fetchall()
    for pact in pacts:
        # Deduct cost from guild1 (initiator)
        grow = db.execute("SELECT treasury FROM guilds WHERE guild_id = ?", (pact["guild1_id"],)).fetchone()
        if grow and grow["treasury"] >= pact["cost_per_hour"]:
            qexec("UPDATE guilds SET treasury = treasury - ? WHERE guild_id = ?", (pact["cost_per_hour"], pact["guild1_id"]))
        else:
            # Pact broken due to insufficient funds
            qexec("UPDATE guild_pacts SET status = 'broken' WHERE id = ?", (pact["id"],))
            print(f"Pact {pact['id']} broken due to lack of funds.")
            # Notify guilds...

async def ensure_chat_channel(guild):
    category = discord.utils.get(guild.categories, name="🎮 RPG REALM")
    if not category: return
    
    ch_name = "💬-chat"
    if not discord.utils.get(guild.text_channels, name=ch_name):
        await guild.create_text_channel(ch_name, category=category, topic="Non-bot chat area")

# ============================================================================
# RNG & CRAFTING ENGINE
# ============================================================================

def roll_loot(p, zone):
    """RNG engine for drops."""
    drops = []
    # 0.02% chance for Celestial Crystal
    if random.random() < 0.0002:
        add_item(p["user_id"], "celestial crystal", "material", "chromatic", 1, 0, 0, 0, 100000)
        drops.append("✨ 💠 **CELESTIAL CRYSTAL** 💠 ✨")
    
    # Drop lootboxes (e.g., 5% chance for wood/iron/gold box)
    if random.random() < 0.05:
        box = random.choice(["wood", "iron", "gold"])
        add_item(p["user_id"], f"{box} box", "consumable", "common", 1, 0, 0, 0, LOOT_BOXES[box])
        drops.append(f"🎁 **{box.upper()} BOX**")

    return drops

def forge_chromatic(user_id, item_name):
    # Check if they have 300 crystals
    crystal = db.execute("SELECT qty FROM inventory WHERE user_id = ? AND item_name = 'celestial crystal'", (user_id,)).fetchone()
    if not crystal or crystal["qty"] < 300:
        return False, "❌ Need 300 Celestial Crystals to forge Chromatic gear!"
    
    # Consume crystals and add item
    remove_item(user_id, "celestial crystal", 300)
    # Give the chromatic item
    add_item(user_id, item_name, "weapon", "chromatic", 1, 5000000, 10000000)
    return True, f"✅ Forged **{item_name}**! Your grind has paid off!"

QUESTS = {
    "slayer": {"target": 5000, "desc": "Slay 5000 Mobs", "gold": 50000, "xp": 10000},
    "boss_killer": {"target": 5, "desc": "Defeat 5 Mega Bosses", "gold": 100000, "xp": 50000},
    "chromatic_grind": {"target": 100, "desc": "Complete 100 Daily Quests", "gold": 500000, "xp": 200000}
}

def start_quest(user_id, quest_key):
    if quest_key not in QUESTS: 
        return False, "Unknown quest."
    q = QUESTS[quest_key]
    now = ts()
    qexec("INSERT OR IGNORE INTO quests(user_id, quest_key, progress, started_at) VALUES(?,?,?,?)", 
          (user_id, quest_key, 0, now))
    return True, f"Started quest: {q['desc']}"

def progress_quest(user_id, quest_key, amount=1):
    """Update quest progress. Returns (completed, message)."""
    qexec("UPDATE quests SET progress = progress + ? WHERE user_id = ? AND quest_key = ? AND completed = 0", 
          (amount, user_id, quest_key))
    q = db.execute("SELECT * FROM quests WHERE user_id = ? AND quest_key = ? AND completed = 0", 
                   (user_id, quest_key)).fetchone()
    if q and q["progress"] >= QUESTS.get(quest_key, {}).get("target", 1):
        qexec("UPDATE quests SET completed = 1, completed_at = ? WHERE user_id = ? AND quest_key = ?", 
              (ts(), user_id, quest_key))
        return True, f"QUEST READY TO CLAIM: {QUESTS[quest_key]['desc']}"
    return False, None

def claim_quest_reward(user_id, quest_key):
    """Claim completed quest reward."""
    q = db.execute("SELECT * FROM quests WHERE user_id = ? AND quest_key = ? AND completed = 1", 
                   (user_id, quest_key)).fetchone()
    if not q: 
        return False, "Quest not completed."
    
    cfg = QUESTS[quest_key]
    qexec("UPDATE players SET gold = gold + ?, xp = xp + ? WHERE user_id = ?", 
          (cfg["gold"], cfg["xp"], user_id))
    qexec("DELETE FROM quests WHERE user_id = ? AND quest_key = ?", (user_id, quest_key))
    mark_player_dirty(user_id)
    return True, f"Claimed {cfg['gold']} Gold & {cfg['xp']} XP!"

async def ensure_info_infrastructure(guild):
    """Create announcements (staff-send), changelog & guide (read-only) — these are NEVER wiped."""
    try:
        admin_role = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)
        owner_role = discord.utils.get(guild.roles, name=OWNER_ROLE_NAME)
        # Announcements: everyone reads, only staff send
        ann = discord.utils.get(guild.text_channels, name=ANNOUNCE_CHANNEL_NAME)
        if ann is None:
            ow = {guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                  guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
            if admin_role:
                ow[admin_role] = discord.PermissionOverwrite(send_messages=True)
            if owner_role:
                ow[owner_role] = discord.PermissionOverwrite(send_messages=True)
            ann = await guild.create_text_channel(ANNOUNCE_CHANNEL_NAME, overwrites=ow, topic="Official announcements — staff only.")
            await ann.send("📢 **Announcements** — important news lands here. (RPG commands don't work in this channel.)")
        # Read-only display channels
        readonly = {guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        # Changelog — post missing versions
        clog = discord.utils.get(guild.text_channels, name=CHANGELOG_CHANNEL_NAME)
        if clog is None:
            clog = await guild.create_text_channel(CHANGELOG_CHANNEL_NAME, overwrites=readonly, topic="Update history — newest at the bottom.")
        
        # Get already posted versions
        posted_versions = set()
        async for msg in clog.history(limit=100):
            if msg.embeds:
                for embed in msg.embeds:
                    if embed.title and "📜" in embed.title:
                        # Extract version from title: "📜 v1.10 — Title" -> "v1.10"
                        v = embed.title.split("—")[0].replace("📜", "").strip()
                        posted_versions.add(v)
        
        # Post missing versions (oldest to newest)
        for entry in reversed(CHANGELOG):
            if entry['v'] not in posted_versions:
                e = discord.Embed(title=f"📜 {entry['v']} — {entry['title']}", color=discord.Colour(0x4DD0E1))

                def _add_section(emb, label, items):
                    # Discord caps each field value at 1024 chars — split into chunks.
                    chunk, part = [], 1
                    cur = 0
                    for x in items:
                        line = f"• {x}"
                        if cur + len(line) + 1 > 1024 and chunk:
                            nm = label if part == 1 else f"{label} ({part})"
                            emb.add_field(name=nm, value="\n".join(chunk), inline=False)
                            chunk, cur, part = [], 0, part + 1
                        chunk.append(line)
                        cur += len(line) + 1
                    if chunk:
                        nm = label if part == 1 else f"{label} ({part})"
                        emb.add_field(name=nm, value="\n".join(chunk), inline=False)

                if entry.get("added"):
                    _add_section(e, "✨ Added", entry["added"])
                if entry.get("upgraded"):
                    _add_section(e, "⬆️ Upgraded", entry["upgraded"])
                if entry.get("fixed"):
                    _add_section(e, "🐛 Fixed", entry["fixed"])
                if entry.get("removed"):
                    _add_section(e, "❌ Removed", entry["removed"])
                _tf = apply_theme(e)
                await clog.send(embed=e, file=_tf)
        # Guide — post once (don't nuke)
        guide = discord.utils.get(guild.text_channels, name=GUIDE_CHANNEL_NAME)
        if guide is None:
            guide = await guild.create_text_channel(GUIDE_CHANNEL_NAME, overwrites=readonly, topic="Every command & feature explained.")
        has_g = False
        async for _ in guide.history(limit=1):
            has_g = True
        if not has_g:
            intro = discord.Embed(title="📖✨ DXN1 RPG'S — FULL GUIDE ✨📖",
                                  description="Just **type** commands anywhere (no prefix). Here's everything you can do:",
                                  color=discord.Colour(0x1565C0))
            _tf = apply_theme(intro)
            await guide.send(embed=intro, file=_tf)
            for section, cmds in GUIDE_COMMANDS:
                # Build command lines and chunk if needed (Discord limit: 1024 chars per field)
                lines = [f"**`{c}`** — {d}" for c, d in cmds]
                full_text = "\n".join(lines)
                
                if len(full_text) <= 1024:
                    e = discord.Embed(title=section, color=discord.Colour(0x1565C0), description=full_text)
                    await guide.send(embed=e)
                else:
                    # Split into multiple embeds if too long
                    chunk, part = [], 1
                    for line in lines:
                        if len("\n".join(chunk + [line])) > 1024:
                            e = discord.Embed(title=f"{section} ({part})", color=discord.Colour(0x1565C0),
                                            description="\n".join(chunk))
                            await guide.send(embed=e)
                            chunk, part = [line], part + 1
                        else:
                            chunk.append(line)
                    if chunk:
                        e = discord.Embed(title=f"{section} ({part})" if part > 1 else section, 
                                        color=discord.Colour(0x1565C0),
                                        description="\n".join(chunk))
                        await guide.send(embed=e)
    except discord.Forbidden:
        print("⚠️  Missing permissions for info channels.")
    except Exception as e:
        print(f"Info infra error: {e}")


async def post_announcement(guild, title, body):
    ch = discord.utils.get(guild.text_channels, name=ANNOUNCE_CHANNEL_NAME) if guild else None
    if ch:
        e = discord.Embed(title=title, description=body, color=discord.Colour(0xFFCA28))
        try:
            await ch.send(content=updates_mention(guild), embed=e, allowed_mentions=discord.AllowedMentions(everyone=True, roles=True))
        except discord.HTTPException:
            pass


class EncounterView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=90)
        self.owner_id = owner_id

    async def _guard(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your encounter!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🏃 Run", style=discord.ButtonStyle.secondary)
    async def run(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        if random.random() < 0.5:
            qexec("DELETE FROM fights WHERE user_id = ?", (self.owner_id,))
            await interaction.response.send_message("🏃💨 You **escaped**! The squad lost your trail.")
        else:
            await interaction.response.send_message("😨 They were faster and **tackled you** — you must `attack`!")
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="🗡️ Fight", style=discord.ButtonStyle.danger)
    async def fight(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await interaction.response.send_message("⚔️ You stand your ground! Say `attack` to strike!")
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="🛡️ Ping Guild", style=discord.ButtonStyle.primary)
    async def ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        p = get_player(self.owner_id)
        if not p or not p["guild_id"]:
            await interaction.response.send_message("❌ You're not in a guild to ping!", ephemeral=True)
            return
        g = db.execute("SELECT channel_id FROM guilds WHERE guild_id=?", (p["guild_id"],)).fetchone()
        gch = interaction.guild.get_channel(g["channel_id"]) if g and g["channel_id"] else None
        if gch:
            try:
                await gch.send(f"🛡️ **{interaction.user.display_name}** is being ambushed in {interaction.channel.mention}! Say `help @{interaction.user.name}` to jump in!")
            except discord.HTTPException:
                pass
            await interaction.response.send_message("🛡️ Pinged your guild for backup! Hold on & `attack`!")
        else:
            await interaction.response.send_message("❌ No guild channel found.", ephemeral=True)


async def ensure_profile_infrastructure(guild):
    """Create the Updates opt-in role and a single shared profile-config channel at the top."""
    try:
        if discord.utils.get(guild.roles, name=UPDATES_ROLE_NAME) is None:
            await guild.create_role(name=UPDATES_ROLE_NAME, colour=discord.Colour(0xFFCA28), mentionable=True)
        ch = discord.utils.get(guild.text_channels, name=PROFILE_CHANNEL_NAME)
        if ch is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
            ch = await guild.create_text_channel(PROFILE_CHANNEL_NAME, overwrites=overwrites,
                                                 topic="Configure your profile — your settings are private to you.")
            try:
                await ch.edit(position=0)
            except discord.HTTPException:
                pass
            embed = discord.Embed(
                title="🪪✨ CONFIGURE YOUR PROFILE ✨🪪",
                description=("Press the button below to open **your private config** (only you can see it).\n\n"
                             "🎨 **Name title** — pick a color + a `[TAG]` (e.g. `[SHADOW] yourname`)\n"
                             "🤝 **Tradeable** — allow/deny others opening trades with you\n"
                             "🔔 **Update pings** — opt in/out of event & update pings"),
                color=discord.Colour(0x00BCD4))
            _tf = apply_theme(embed)
            await ch.send(embed=embed, view=ProfileConfigEntryView(), file=_tf)
    except discord.Forbidden:
        print("⚠️  Missing permissions for profile setup (need Manage Roles/Channels/Nicknames).")
    except Exception as e:
        print(f"Profile setup error: {e}")


async def ensure_staff_infrastructure(guild):
    """Create ADMIN (red) + OWNER (gold) roles — NEVER auto-assigned — and staff-only channels."""
    try:
        admin_role = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)
        if admin_role is None:
            admin_role = await guild.create_role(
                name=ADMIN_ROLE_NAME, colour=discord.Colour(ADMIN_ROLE_COLOR),
                hoist=True, mentionable=True, permissions=discord.Permissions(administrator=True))
        owner_role = discord.utils.get(guild.roles, name=OWNER_ROLE_NAME)
        if owner_role is None:
            owner_role = await guild.create_role(
                name=OWNER_ROLE_NAME, colour=discord.Colour(OWNER_ROLE_COLOR),
                hoist=True, mentionable=True, permissions=discord.Permissions(administrator=True))

        category = discord.utils.get(guild.categories, name="🛡️ STAFF")
        if category is None:
            category = await guild.create_category("🛡️ STAFF")

        staff_overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            admin_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            owner_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for ch_name, topic in [
            (ADMIN_CHANNEL_NAME, "🛡️ Admin & Owner only."),
            (EVENTS_CHANNEL_NAME, "Type `event` here to launch a server-wide event."),
            (PLANNING_CHANNEL_NAME, "Type `planning` here to schedule a future event."),
            (UPDATE_CHANNEL_NAME, "Press the button to broadcast an update warning."),
        ]:
            ch = discord.utils.get(guild.text_channels, name=ch_name)
            if ch is None:
                ch = await guild.create_text_channel(ch_name, category=category, overwrites=staff_overwrites, topic=topic)
                if ch_name == EVENTS_CHANNEL_NAME:
                    await ch.send("🎉 **EVENTS** — just type `event` (no prefix) to open the launcher.")
                elif ch_name == PLANNING_CHANNEL_NAME:
                    await ch.send("🗓️ **PLANNING** — just type `planning` (no prefix) to schedule a future event.")
                elif ch_name == UPDATE_CHANNEL_NAME:
                    await ch.send("🔄 **UPDATE CONTROL** — staff only.", view=UpdateBroadcastView())
                elif ch_name == ADMIN_CHANNEL_NAME:
                    await ch.send("🛡️ **ADMIN CHANNEL** — mod commands use the `s!` prefix (e.g. `s!warn @user spamming`).")
    except discord.Forbidden:
        print("⚠️  Missing permissions for staff setup (need Manage Roles + Manage Channels).")
    except Exception as e:
        print(f"Staff setup error: {e}")


async def ensure_world_infrastructure(guild):
    """Create the auto-roles and gated world channels (everyone sees, only role can enter)."""
    try:
        category = discord.utils.get(guild.categories, name="🌍 WORLDS")
        if category is None:
            category = await guild.create_category("🌍 WORLDS")
        for idx, w in enumerate(WORLDS):
            role = discord.utils.get(guild.roles, name=w["role"])
            if role is None:
                colour = discord.Colour(WORLD_COLORS[idx % len(WORLD_COLORS)])
                role = await guild.create_role(name=w["role"], hoist=True, mentionable=False, colour=colour)
            ch_name = f"{w['key']}-world"
            ch = discord.utils.get(guild.text_channels, name=ch_name)
            if ch is None:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                    role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                }
                ch = await guild.create_text_channel(
                    ch_name, category=category, overwrites=overwrites,
                    topic=f"{w['name']} — Lvl {w['level']} | Prestige {w['prestige']} | Rebirth {w['rebirth']}")
                await ch.send(f"🔒 **{w['name']}** is locked. Reach the requirements to earn **{w['role']}** and enter!")
    except discord.Forbidden:
        print("⚠️  Missing permissions for world setup (bot needs Manage Roles + Manage Channels, and its role above the world roles).")
    except Exception as e:
        print(f"World setup error: {e}")


async def sync_player_roles(member, player) -> list:
    """Grant any world roles the player now qualifies for. Returns the newly granted worlds."""
    if member is None or player is None:
        return []
    guild = member.guild
    newly = []
    try:
        for w in WORLDS:
            ok, _ = world_reqs_met(player, w)
            if not ok:
                continue
            role = discord.utils.get(guild.roles, name=w["role"])
            if role and role not in member.roles:
                await member.add_roles(role, reason=f"Unlocked world {w['name']}")
                newly.append(w)
                # Louder feedback: announce in the world channel + DM the player
                ch = discord.utils.get(guild.text_channels, name=f"{w['key']}-world")
                if ch:
                    try:
                        await ch.send(f"🎉 {member.mention} earned **{w['role']}** and entered **{w['name']}**! 🌍✨")
                    except discord.HTTPException:
                        pass
                try:
                    await member.send(f"🌍✨ You unlocked **{w['name']}**! You now hold the **{w['role']}** role and can enter <#{ch.id if ch else 0}>.")
                except (discord.HTTPException, discord.Forbidden):
                    pass
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"Role sync error: {e}")
    return newly


@bot.event
async def on_ready():
    print(f"\n✅ Bot online as {bot.user}")
    print(f"💾 Database: {DB_PATH}")
    print(f"📝 Config: {CONFIG_PATH}")
    print("="*60 + "\n")
    
    # Persistent buttons (update broadcast + profile config)
    bot.add_view(UpdateBroadcastView())
    bot.add_view(ProfileConfigEntryView())
    bot.add_view(TicketingView())
    
    # Ensure world + staff + profile channels and auto-roles exist in every guild
    for g in bot.guilds:
        await ensure_staff_infrastructure(g)
        await ensure_profile_infrastructure(g)
        await ensure_info_infrastructure(g)
        await ensure_world_infrastructure(g)
    
    # Start background loops (needs a running event loop; guard against reconnects)
    for _loop in (autosave_loop, events_loop, guild_stats_loop):
        if not _loop.is_running():
            _loop.start()

@bot.event
async def on_reaction_add(reaction, user):
    """Handle inventory reactions"""
    if user.bot:
        return
    
    try:
        emoji = str(reaction.emoji)
        
        # Inventory navigation
        if emoji in ["⬅️", "➡️"]:
            message = reaction.message
            if "INVENTORY" in message.embeds[0].title if message.embeds else "":
                # Handle page navigation
                p = get_player(user.id)
                if not p:
                    return
                
                inv = db.execute("SELECT * FROM inventory WHERE user_id = ? ORDER BY rarity DESC", (user.id,)).fetchall()
                if not inv:
                    return
                
                # Simple forward/back logic
                inv_str = "\n".join(f"{rarity_emoji(row['rarity'])} **{row['item_name']}** x{row['qty']} (Power: {row['power']})" for row in inv)
                
                embed = discord.Embed(title=f"📦✨ {p['name']}'s INVENTORY ✨📦", description=inv_str, color=discord.Colour.blue())
                embed.add_field(name="⬅️ React to navigate | 🔧 React to equip", value="Use ⬅️➡️ for pages | 📦 to equip items", inline=False)
                embed.set_footer(text=f"Items: {len(inv)} | Gold: {p['gold']} | Level: {p['level']}")
                
                await message.edit(embed=embed)
        
        # Equip button
        elif emoji == "🔧":
            message = reaction.message
            if "INVENTORY" in (message.embeds[0].title if message.embeds else ""):
                p = get_player(user.id)
                if not p:
                    return
                
                inv = db.execute("SELECT * FROM inventory WHERE user_id = ? LIMIT 10", (user.id,)).fetchall()
                if not inv:
                    return
                
                inv_str = "\n".join(f"🔧 **{row['item_name']}** (Power: {row['power']})" for row in inv)
                embed = discord.Embed(title="🔧 EQUIP MENU", description=inv_str, color=discord.Colour.gold())
                embed.add_field(name="Usage", value="Say: `equip [item name]`", inline=False)
                
                await message.channel.send(embed=embed)
    except:
        pass

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
        
    # Auto-purge logic
    if message.channel.name in ["events", "planning"]:
        # Don't delete if it's the control channel or has a view attached
        if not message.components:
            await asyncio.sleep(60)
            await message.delete()

    # ... existing auto-purge logic ...

    try:
        # Strict command parsing
        words = message.content.split()
        if not words: return
        cmd = words[0].lower()
        # Core context used throughout this handler
        content = (message.content or "").lower().strip()
        user_id = message.author.id
        p = get_player(user_id)
        
        # 1. SECRET ATTACK (Exact Match)
        if " ".join(words).lower() == "fidget spinner dickbender whirlpool superduper shitstain attack 9000":
             # ... existing secret attack logic ...
             return

        # QUESTS
        if cmd == "quest":
            subcmd = words[1].lower() if len(words) > 1 else "list"
            if subcmd == "list":
                qlist = "\n".join(f"• **{k}**: {v['desc']} (Target: {v['target']})" for k, v in QUESTS.items())
                await message.reply(f"📜 **AVAILABLE QUESTS**\n{qlist}\nUse `quest accept [key]` to start.")
                return
            if subcmd == "accept" and len(words) > 2:
                ok, msg = start_quest(user_id, words[2].lower())
                await message.reply(("✅ " if ok else "❌ ") + msg); return
            if subcmd == "claim" and len(words) > 2:
                ok, msg = claim_quest_reward(user_id, words[2].lower())
                await message.reply(("✅ " if ok else "❌ ") + msg); return

        # 2. GUILD COMMANDS (Explicit)
        if cmd == "guild":
            subcmd = words[1].lower() if len(words) > 1 else "list"
            
            if subcmd == "donate":
                if len(words) < 3:
                    await message.reply("Usage: `guild donate [amount]`")
                    return
                try:
                    amount = int(words[2])
                except ValueError:
                    await message.reply("❌ Invalid amount.")
                    return
                if amount <= 0 or p["gold"] < amount: await message.reply("❌ Invalid amount or not enough gold."); return
                qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (amount, user_id))
                qexec("UPDATE guilds SET treasury = treasury + ? WHERE guild_id = ?", (amount, p["guild_id"]))
                mark_player_dirty(user_id)
                await message.reply(f"✅ Donated {amount:,} gold to the treasury!")
                return
            
            if subcmd == "upgrade":
                # ... existing upgrade logic ...
                return
            
            if subcmd == "pact":
                # Usage: guild pact [enemy_guild_id] [type] [cost] [hours]
                if len(words) < 6: await message.reply("Usage: `guild pact [enemy_id] [type] [cost] [hours]`"); return
                enemy_id, p_type, cost, hours = int(words[2]), words[3], int(words[4]), int(words[5])
                qexec("INSERT INTO guild_pacts(guild1_id, guild2_id, pact_type, cost_per_hour, expires_at) VALUES(?,?,?,?,?)",
                      (p["guild_id"], enemy_id, p_type, cost, ts() + hours * 3600))
                await message.reply(f"🤝 Pact of {p_type} proposed/established with guild {enemy_id}!")
                return
        if content.startswith("s!"):
            if not isinstance(message.author, discord.Member) or not is_staff(message.author):
                await message.reply("❌ Only **ADMIN** or **OWNER** can use staff commands.")
                return
            parts = message.content[2:].split()
            if not parts:
                await message.reply(
                    "Staff cmds: `s!warn @u [reason]` • `s!unwarn @u` • `s!warnings @u` • "
                    "`s!kick @u` • `s!mute @u [mins]` • `s!unmute @u` • `s!ban @u [reason]` • "
                    "`s!unban <id>` • `s!cleanup` • `s!give <item> [amt] [@u]`\n"
                    "Owner-only: `s!settax <percent>` • `s!setowner <@user>`"
                )
                return
            cmd = parts[0].lower()
            guild = message.guild
            target = message.mentions[0] if message.mentions else None
            reason = " ".join(p for p in parts[1:] if not p.startswith("<@")) or "No reason given"

            if cmd == "warn":
                if not target:
                    await message.reply("Usage: `s!warn @user [reason]`"); return
                count = await add_warning(guild.id, target.id, user_id, reason)
                await message.reply(f"⚠️ Warned {target.mention} — now **{count}** warning(s). Reason: {reason}")
                try:
                    await target.send(f"⚠️ You were warned in **{guild.name}**: {reason} (total {count})")
                except (discord.HTTPException, discord.Forbidden):
                    pass
                return
            # ── s!settax <percent> ── (OWNER only)
            if cmd == "settax":
                if not any(r.name == OWNER_ROLE_NAME for r in message.author.roles):
                    await message.reply(f"❌ Only **{OWNER_ROLE_NAME}** can use `s!settax`.")
                    return
                if len(parts) < 2:
                    current = round(float(CONFIG.get("trade_tax", 0.0227)) * 100, 2)
                    await message.reply(f"💰 Current marketplace tax: **{current}%**\nUsage: `s!settax <percent>` (e.g. `s!settax 2.5`)")
                    return
                try:
                    new_rate = float(parts[1].replace("%", ""))
                    if not 0 <= new_rate <= 25:
                        raise ValueError
                except ValueError:
                    await message.reply("❌ Rate must be a number between 0 and 25 (percent).")
                    return
                CONFIG["trade_tax"] = round(new_rate / 100, 6)
                CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2))
                await message.reply(f"✅ Marketplace tax set to **{new_rate}%**. Changes apply instantly.")
                return

            # ── s!setowner <@user> ── (OWNER only)
            if cmd == "setowner":
                if not any(r.name == OWNER_ROLE_NAME for r in message.author.roles):
                    await message.reply(f"❌ Only **{OWNER_ROLE_NAME}** can use `s!setowner`.")
                    return
                if not message.mentions:
                    current_id = int(CONFIG.get("tax_owner_id", 0))
                    mention = f"<@{current_id}>" if current_id else "*(not set — tax is a gold sink)*"
                    await message.reply(f"💰 Current tax recipient: {mention}\nUsage: `s!setowner @user`")
                    return
                new_owner = message.mentions[0]
                CONFIG["tax_owner_id"] = new_owner.id
                CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2))
                await message.reply(f"✅ Marketplace tax recipient set to {new_owner.mention}. They'll collect all future market taxes.")
                return

            if cmd == "give":
                # Check for owner role
                if not any(r.name == OWNER_ROLE_NAME for r in message.author.roles):
                    await message.reply(f"❌ Only **{OWNER_ROLE_NAME}** can use `s!give`.")
                    return
                
                if len(parts) < 2:
                    await message.reply("Usage: `s!give <item_name> [amount] [@user]`")
                    return
                
                target = message.mentions[0] if message.mentions else message.author
                
                # Exclude mentions from parts for item parsing
                filtered_parts = [p for p in parts[1:] if not p.startswith("<@")]
                
                # Parse item and amount
                if filtered_parts and filtered_parts[-1].isdigit():
                    amount = int(filtered_parts[-1])
                    item_name = " ".join(filtered_parts[:-1])
                else:
                    amount = 1
                    item_name = " ".join(filtered_parts)
                
                if not item_name:
                    await message.reply("Usage: `s!give <item_name> [amount] [@user]`")
                    return

                # Check if it's a stat update
                name_low = item_name.lower()
                if name_low in ["level", "lvl"]:
                    qexec("UPDATE players SET level = level + ? WHERE user_id = ?", (amount, target.id))
                    await message.reply(f"✅ Added **{amount}** levels to {target.mention}.")
                    mark_player_dirty(target.id)
                    return
                elif name_low in ["gold", "money"]:
                    qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (amount, target.id))
                    await message.reply(f"✅ Added **{amount}** gold to {target.mention}.")
                    mark_player_dirty(target.id)
                    return

                # Check if item exists in SHOP_ITEMS for type/rarity info
                item_data = SHOP_ITEMS.get(name_low)
                
                if not item_data:
                    item_type = "material"
                    rarity = "common"
                    power = 0
                    value = 10
                else:
                    item_type = item_data.get("type", "material")
                    rarity = item_data.get("rarity", "common")
                    power = item_data.get("power", 0)
                    value = item_data.get("price", 10)
                
                add_item(target.id, item_name, item_type, rarity, amount, power, value)
                await message.reply(f"✅ Given **{amount}× {item_name}** to {target.mention}.")
                return
            if cmd == "cleanup":
                # Check for owner role
                if not any(r.name == OWNER_ROLE_NAME for r in message.author.roles):
                    await message.reply(f"❌ Only **{OWNER_ROLE_NAME}** can use `s!cleanup`.")
                    return
                
                subcmd = parts[1] if len(parts) > 1 else None
                if subcmd == "full":
                    await message.reply("⚠️ Performing full server cleanup and recreation...")
                    await setup_server()
                elif subcmd == "worlds":
                    await message.reply("🔄 Recreating world infrastructure...")
                    await ensure_world_infrastructure(guild)
                elif subcmd == "general":
                    await message.reply("🔄 Recreating general infrastructure...")
                    await ensure_info_infrastructure(guild)
                else:
                    await message.reply("Usage: `s!cleanup [full|worlds|general]`")
                return
            if cmd == "unwarn":
                if not target:
                    await message.reply("Usage: `s!unwarn @user`"); return
                row = db.execute("SELECT warn_id FROM warnings WHERE guild_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1", (guild.id, target.id)).fetchone()
                if not row:
                    await message.reply(f"{target.mention} has no warnings."); return
                qexec("DELETE FROM warnings WHERE warn_id=?", (row["warn_id"],))
                await message.reply(f"✅ Removed latest warning from {target.mention}.")
                return
            if cmd == "warnings":
                if not target:
                    await message.reply("Usage: `s!warnings @user`"); return
                rows = db.execute("SELECT reason FROM warnings WHERE guild_id=? AND user_id=? ORDER BY created_at DESC LIMIT 15", (guild.id, target.id)).fetchall()
                if not rows:
                    await message.reply(f"{target.mention} has no warnings."); return
                await message.reply(f"⚠️ **{target.display_name}** has {len(rows)} warning(s):\n" + "\n".join(f"• {r['reason']}" for r in rows))
                return
            if cmd == "kick":
                if not target:
                    await message.reply("Usage: `s!kick @user`"); return
                try:
                    await target.kick(reason=reason)
                    await message.reply(f"👢 Kicked {target.mention}. Reason: {reason}")
                except discord.Forbidden:
                    await message.reply("❌ I lack permission to kick (need Kick Members + a higher role).")
                return
            if cmd == "mute":
                if not target:
                    await message.reply("Usage: `s!mute @user [minutes]`"); return
                mins = next((int(p) for p in parts[1:] if p.isdigit()), 10)
                try:
                    import datetime
                    await target.timeout(datetime.timedelta(minutes=mins), reason=reason)
                    await message.reply(f"🔇 Muted {target.mention} for {mins} min.")
                except discord.Forbidden:
                    await message.reply("❌ I lack permission to timeout (need Moderate Members).")
                except Exception as e:
                    await message.reply(f"❌ Couldn't mute: {type(e).__name__}")
                return
            if cmd == "unmute":
                if not target:
                    await message.reply("Usage: `s!unmute @user`"); return
                try:
                    await target.timeout(None, reason="unmute")
                    await message.reply(f"🔊 Unmuted {target.mention}.")
                except discord.Forbidden:
                    await message.reply("❌ I lack permission to do that.")
                return
            if cmd == "ban":
                if not target:
                    await message.reply("Usage: `s!ban @user [reason]`"); return
                try:
                    await guild.ban(target, reason=reason)
                    await message.reply(f"🔨 Banned {target.mention}. Reason: {reason}")
                except discord.Forbidden:
                    await message.reply("❌ I lack permission to ban (need Ban Members + a higher role).")
                return
            if cmd == "unban":
                ids = [int(p) for p in parts[1:] if p.isdigit()]
                if not ids:
                    await message.reply("Usage: `s!unban <user_id>` (mentions don't work for banned users)"); return
                try:
                    await guild.unban(discord.Object(id=ids[0]))
                    await message.reply(f"✅ Unbanned `{ids[0]}`.")
                except discord.NotFound:
                    await message.reply("❌ That user isn't banned.")
                except discord.Forbidden:
                    await message.reply("❌ I lack permission to unban.")
                return
            await message.reply(f"❓ Unknown staff command `{cmd}`. Try `s!` for the list.")
            return

        # ---------- EVENTS / PLANNING channels (no prefix, staff only) ----------
        norm_ch = _norm_channel(getattr(message.channel, "name", "")) if message.guild else ""
        if norm_ch in ("events", "planning"):
            if not is_staff(message.author):
                return
            if norm_ch == "events" and content.strip() == "event":
                active = active_event_summary(message.guild.id)
                embed = discord.Embed(
                    title="🎉✨ EVENT LAUNCHER ✨🎉",
                    description="Pick an **event** and a **duration**, then hit **🚀 Launch Event**.\nIt goes live server-wide instantly and pings everyone.",
                    color=discord.Colour(0xFF4081))
                if active:
                    embed.add_field(name="🟢 Currently Active", value=active, inline=False)
                embed.set_footer(text="Only ADMIN/OWNER can see & use this channel.")
                _tf = apply_theme(embed)
                await message.reply(embed=embed, view=EventBuilderView(message.guild.id), file=_tf)
                return
            if norm_ch == "planning" and content.strip() == "planning":
                embed = discord.Embed(
                    title="🗓️✨ EVENT PLANNER ✨🗓️",
                    description="Pick an **event**, a **duration**, and **when it starts**, then hit **🗓️ Schedule Event**.",
                    color=discord.Colour(0x29B6F6))
                scheduled = db.execute("SELECT name, start_at FROM server_events WHERE guild_id=? AND status='scheduled' ORDER BY start_at LIMIT 10", (message.guild.id,)).fetchall()
                if scheduled:
                    now = ts()
                    embed.add_field(name="🕒 Upcoming", value="\n".join(f"{r['name']} — in {fmt_secs(r['start_at']-now)}" for r in scheduled), inline=False)
                embed.set_footer(text="Only ADMIN/OWNER can see & use this channel.")
                _tf = apply_theme(embed)
                await message.reply(embed=embed, view=PlanningBuilderView(message.guild.id), file=_tf)
                return
            return  # keep staff event channels clean — ignore other chatter
        
        # ---------- READ-ONLY / CHAT-ONLY CHANNELS: RPG engine stays silent ----------
        if norm_ch in NONRPG_CHANNELS:
            return
        if message.guild and db.execute("SELECT 1 FROM guilds WHERE channel_id=?", (message.channel.id,)).fetchone():
            return  # guild chat channel — for chatting, not RPG commands
        
        # ---------- ACTIVE TRADE CHANNEL ----------
        if message.guild and message.channel.id in active_trades:
            sess = active_trades[message.channel.id]
            if user_id not in (sess["a"], sess["b"]):
                return
            other = sess["b"] if user_id == sess["a"] else sess["a"]
            low = content.strip()
            if low.startswith("offer"):
                arg = message.content[len("offer"):].strip()
                if not arg:
                    inv = db.execute("SELECT * FROM inventory WHERE user_id=? ORDER BY rarity DESC LIMIT 25", (user_id,)).fetchall()
                    if not inv:
                        await message.reply("📦 You have nothing to offer!"); return
                    await message.reply("🎁 Pick items to offer (or type `offer x2 magma boots, void helmet`):", view=TradeOfferView(user_id, inv))
                    return
                offers, err = parse_offer(user_id, arg)
                if err:
                    await message.reply(f"❌ {err}"); return
                sess["offers"][user_id] = offers
                sess["accepted"] = {sess["a"]: False, sess["b"]: False}
                await message.reply(f"<@{other}> — new offer on the table!", allowed_mentions=discord.AllowedMentions(users=True))
                await post_trade_state(message.channel, sess)
                return
            if low in ("accept", "accepted", "yes"):
                if not sess["offers"].get(user_id) and not sess["offers"].get(other):
                    await message.reply("❌ Put something on the table first with `offer [item]`."); return
                sess["accepted"][user_id] = True
                if sess["accepted"].get(sess["a"]) and sess["accepted"].get(sess["b"]):
                    valid = all(inv_qty(side, n) >= q for side in (sess["a"], sess["b"]) for q, n in sess["offers"].get(side, []))
                    if not valid:
                        sess["accepted"] = {sess["a"]: False, sess["b"]: False}
                        await message.reply("❌ Someone no longer has their offered items — offers reset.")
                        return
                    transfer_offer(sess["a"], sess["b"], sess["offers"].get(sess["a"], []))
                    transfer_offer(sess["b"], sess["a"], sess["offers"].get(sess["b"], []))
                    active_trades.pop(message.channel.id, None)
                    await message.channel.send("✅🤝 **TRADE COMPLETE!** Items swapped & added to your inventories. This room self-destructs in 60s — say gg! 💜")
                    asyncio.create_task(_delete_later(message.channel, 60))
                    return
                await message.reply(f"✅ You accepted. Waiting on <@{other}>…", allowed_mentions=discord.AllowedMentions(users=True))
                return
            if low in ("decline", "no", "reject"):
                sess["accepted"][user_id] = False
                await message.reply("🚫 You declined. Adjust offers or `cancel`.")
                return
            if low in ("cancel", "close", "end"):
                active_trades.pop(message.channel.id, None)
                await message.channel.send("🚫 Trade cancelled. Channel closing in 10s.")
                asyncio.create_task(_delete_later(message.channel, 10))
                return
            return  # ignore other chatter in trade channels
        
        # ---------- OPEN A TRADE (trade @user) ----------
        if message.guild and content.startswith("trade") and message.mentions:
            if not get_player(user_id):
                await message.reply("❌ Create character first!"); return
            partner = next((m for m in message.mentions if m.id != user_id and not m.bot), None)
            if not partner:
                await message.reply("❌ Mention a valid player: `trade @user`"); return
            partner_p = get_player(partner.id)
            if not partner_p:
                await message.reply("❌ That player hasn't started the game yet."); return
            if not partner_p["tradeable"]:
                await message.reply(f"❌ **{partner.display_name}** has trading turned **off** in their profile config."); return
            for s in active_trades.values():
                if user_id in (s["a"], s["b"]) or partner.id in (s["a"], s["b"]):
                    await message.reply("❌ You or that player are already in a trade."); return
            guild = message.guild
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                    message.author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                    partner: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                }
                ch = await guild.create_text_channel(f"trade-{message.author.name}-{partner.name}"[:32], overwrites=overwrites, topic="Private trade — auto-deletes after completion")
            except discord.Forbidden:
                await message.reply("❌ I need **Manage Channels** to open a trade room."); return
            active_trades[ch.id] = {"a": user_id, "b": partner.id, "offers": {}, "accepted": {user_id: False, partner.id: False}, "done": False}
            await ch.send(
                f"🤝 {message.author.mention} ⇄ {partner.mention}\n"
                "Use `offer [item]` (or `offer` for a menu), then both `accept`.\n"
                "Examples: `offer x11 inferno protection t3` • `offer void helmet, magma boots` • up to 6 via the menu.",
                allowed_mentions=discord.AllowedMentions(users=True))
            await message.reply(f"✅ Private trade room opened: {ch.mention}")
            return
        
        # Fuzzy typo correction for the natural-language router (inventury -> inventory)
        content = fuzzy_correct(content)
        
        # GUILD HELP MODE — `help @user` joins their fight
        if content.startswith("help") and message.mentions:
            if not get_player(user_id):
                await message.reply("❌ Create character first!"); return
            tgt = next((m for m in message.mentions if not m.bot), None)
            if not tgt or tgt.id == user_id:
                await message.reply("❌ Mention the player you want to help: `help @user`"); return
            tfight = get_fight(tgt.id)
            if not tfight:
                await message.reply(f"❌ {tgt.display_name} isn't in a fight right now."); return
            helping[user_id] = tgt.id
            fight_helpers.setdefault(tgt.id, set()).add(user_id)
            await message.reply(f"🛡️ You jumped in to help **{tgt.display_name}** fight the **{tfight['enemy_name']}**! Keep saying `attack` until it dies — then you'll exit help mode.")
            return
        
        # PROFILE CONFIG opener (also available in the 🪪-profile-config channel button)
        if content.strip() in ("config", "profile config", "profileconfig", "settings", "myprofile"):
            if not get_player(user_id):
                await message.reply("❌ Create character first!"); return
            embed = discord.Embed(title="🪪 Profile Config", description="Click below to open your **private** config panel (only you see it).", color=discord.Colour(0x00BCD4))
            await message.reply(embed=embed, view=ProfileConfigEntryView())
            return
        
        # G.M — message activity stats & message leaderboard
        if content.startswith("g.m"):
            sp = content.split(maxsplit=1)
            rest = sp[1].strip() if len(sp) > 1 else ""
            if "leaderboard" in rest or rest.startswith("lb") or "top" in rest:
                days, label = -1, "All-Time"
                for kw, d, lb in [("daily", 0, "Today"), ("weekly", 7, "This Week"), ("monthly", 30, "This Month"), ("yearly", 365, "This Year")]:
                    if kw in rest:
                        days, label = d, lb; break
                rows = msg_leaderboard(days)
                if not rows:
                    await message.reply("No message activity logged yet!"); return
                desc = "\n".join(f"**#{i+1}** <@{r['user_id']}> — {r['c']:,} msgs" for i, r in enumerate(rows))
                embed = discord.Embed(title=f"💬 MESSAGE LEADERBOARD — {label}", description=desc, color=discord.Colour(0x4DD0E1))
                _tf = apply_theme(embed)
                await message.reply(embed=embed, file=_tf)
                return
            target = message.mentions[0] if message.mentions else message.author
            tid = target.id
            embed = discord.Embed(title=f"💬 {target.display_name}'s Message Stats", color=discord.Colour(0x4DD0E1))
            embed.add_field(name="📅 Today", value=f"{msg_count(tid, 0):,}", inline=True)
            embed.add_field(name="🗓️ This Week", value=f"{msg_count(tid, 7):,}", inline=True)
            embed.add_field(name="📆 This Month", value=f"{msg_count(tid, 30):,}", inline=True)
            embed.add_field(name="🗓️ This Year", value=f"{msg_count(tid, 365):,}", inline=True)
            embed.add_field(name="♾️ All-Time", value=f"{msg_count(tid, -1):,}", inline=True)
            try:
                embed.set_thumbnail(url=target.display_avatar.url)
            except Exception:
                pass
            _tf = apply_theme(embed)
            await message.reply(embed=embed, file=_tf)
            return
        
        # LEADERBOARD with period filters (level by default, message-based for periods)
        if content.startswith("leaderboard") or content.strip() == "lb" or content.startswith("lb "):
            period = None
            for kw, d, lb in [("daily", 0, "Today"), ("weekly", 7, "This Week"), ("monthly", 30, "This Month"), ("yearly", 365, "This Year"), ("alltime", -1, "All-Time"), ("all-time", -1, "All-Time"), ("all time", -1, "All-Time")]:
                if kw in content:
                    period = (d, lb); break
            if period:
                days, label = period
                rows = msg_leaderboard(days)
                if not rows:
                    await message.reply("No message activity logged yet!"); return
                desc = "\n".join(f"**#{i+1}** <@{r['user_id']}> — {r['c']:,} msgs" for i, r in enumerate(rows))
                embed = discord.Embed(title=f"🏆 LEADERBOARD — {label}", description=desc, color=discord.Colour.gold())
                _tf = apply_theme(embed)
                await message.reply(embed=embed, file=_tf)
                return
            top = db.execute("SELECT * FROM players ORDER BY level DESC, xp DESC LIMIT 10").fetchall()
            if not top:
                await message.reply("No players yet!"); return
            desc = "\n".join(f"**#{i+1}** 🏅 **{r['name']}** — Lvl {r['level']} ({r['xp']:,} XP)" for i, r in enumerate(top))
            embed = discord.Embed(title="🏆 LEVEL LEADERBOARD", description=desc, color=discord.Colour.gold())
            embed.set_footer(text="Try `leaderboard daily/weekly/monthly/yearly/alltime` for chat leaders • `g.m` for your stats")
            _tf = apply_theme(embed)
            await message.reply(embed=embed, file=_tf)
            return
        
        # CLASS — view & switch classes
        if content.startswith("class"):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!"); return
            toks = content.split()
            rest = " ".join(toks[1:]).strip()
            if not rest or rest == "list":
                norm = [k for k in CLASSES if k not in SECRET_CLASSES]
                lines = [f"⚔️ **{k.title()}** — {CLASSES[k]['desc']} (HP {CLASSES[k]['hp']}/ATK {CLASSES[k]['atk']}/DEF {CLASSES[k]['def']})" for k in norm]
                sec_lines = []
                for k in sorted(SECRET_CLASSES):
                    owned = inv_qty(user_id, f"{k} tome") > 0
                    sec_lines.append(f"{'🧬' if owned else '🔒'} **{k.title()}** — {CLASSES[k]['desc']} {'(UNLOCKED)' if owned else '(buy in `astralshop`)'}")
                embed = discord.Embed(title="🧬 CLASSES", color=level_color(p["level"]),
                                      description="\n".join(lines) + "\n\n**🔒 SECRET CLASSES:**\n" + "\n".join(sec_lines))
                embed.add_field(name="Your class", value=f"**{p['class_name'].title()}**", inline=False)
                embed.set_footer(text="Switch with `class [name]` — switching adjusts your base stats")
                _tf = apply_theme(embed)
                await message.reply(embed=embed, file=_tf)
                return
            key = rest.replace(" ", "")
            if key not in CLASSES:
                await message.reply(f"❌ Unknown class **{rest}**. Say `class list`."); return
            if key in SECRET_CLASSES and inv_qty(user_id, f"{key} tome") <= 0:
                await message.reply(f"🔒 **{key.title()}** is a secret class — unlock it in `astralshop` with 💠 {CURRENCY_NAME}."); return
            if key == p["class_name"]:
                await message.reply(f"You're already a **{key.title()}**."); return
            old = CLASSES[p["class_name"]]
            new = CLASSES[key]
            qexec("UPDATE players SET class_name=?, atk=atk+?, defense=defense+?, max_hp=max_hp+?, max_mana=max_mana+?, crit=? WHERE user_id=?",
                  (key, new["atk"] - old["atk"], new["def"] - old["def"], new["hp"] - old["hp"], new["mana"] - old["mana"], new["crit"], user_id))
            mark_player_dirty(user_id)
            await message.reply(f"🧬 You are now a **{key.title()}**! Base stats adjusted.\n_{CLASSES[key]['desc']}_")
            return
        
        # PRIVATE ROOM (your own quiet channel — no chat spam / fights)
        if "private" in content:
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            guild = message.guild
            if not guild:
                await message.reply("❌ Use this inside a server.")
                return
            channel_name = f"🔒-{message.author.name.lower().replace(' ', '-')}"[:32]
            existing = discord.utils.get(guild.text_channels, name=channel_name)
            if existing:
                await message.reply(f"🔒 Your private room already exists: {existing.mention}")
                return
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    message.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                }
                ch = await guild.create_text_channel(
                    channel_name, overwrites=overwrites,
                    topic=f"Private RPG room for {message.author.name}")
                await ch.send(f"🔒 Welcome to your private room, <@{user_id}>!\nNo spam here — check `inventory`, `shop`, `market`, `status` in peace.")
                await message.reply(f"✅ Private room created: {ch.mention}")
            except Exception as e:
                await message.reply(f"❌ Couldn't create private room: {type(e).__name__}")
            return
        
        # MAIN MENU (clickable category dropdown)
        if content in ("menu", "help", "commands", "?") or content.startswith("menu"):
            embed = discord.Embed(
                title="📜✨ GAME MENU ✨📜",
                description="Use the dropdown below to browse commands by category.",
                color=discord.Colour.blurple(),
            )
            for cat, cmds in MENU_CATEGORIES.items():
                embed.add_field(name=cat, value=cmds, inline=False)
            await message.reply(embed=embed, view=MenuView())
            return
        
        # WORLDS (gated channels + auto-roles)
        if "world" in content:
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            guild = message.guild
            
            if "setup" in content:
                if guild and message.author.guild_permissions.manage_channels:
                    await ensure_world_infrastructure(guild)
                    await message.reply("✅ World channels & auto-roles are set up!")
                else:
                    await message.reply("❌ You need **Manage Channels** permission to set up worlds.")
                return
            
            member = message.author if isinstance(message.author, discord.Member) else None
            newly = await sync_player_roles(member, p)
            
            lines = []
            for w in WORLDS:
                ok, unmet = world_reqs_met(p, w)
                icon = "✅" if ok else "🔒"
                req = f"Lvl {w['level']}"
                if w["prestige"]:
                    req += f" • P{w['prestige']}"
                if w["rebirth"]:
                    req += f" • RB{w['rebirth']}"
                line = f"{icon} **{w['name']}** — {req}"
                if not ok:
                    line += f"  _(need: {', '.join(unmet)})_"
                lines.append(line)
            
            unlocked_count = sum(1 for w in WORLDS if world_reqs_met(p, w)[0])
            embed = discord.Embed(
                title="🌍✨ WORLDS ✨🌍",
                description="\n".join(lines),
                color=level_color(p["level"]),
            )
            embed.add_field(name="🗺️ Progress", value=f"**{unlocked_count}/{len(WORLDS)}** worlds unlocked", inline=False)
            if newly:
                embed.add_field(name="🆕 Newly Unlocked!", value="\n".join(f"{w['name']} → {w['role']}" for w in newly), inline=False)
            if guild and not guild.me.guild_permissions.manage_roles:
                embed.add_field(name="⚠️ Setup issue", value="I can't assign roles — give me **Manage Roles** and move my role **above** the world roles.", inline=False)
            try:
                if guild and guild.icon:
                    embed.set_thumbnail(url=guild.icon.url)
                else:
                    embed.set_thumbnail(url=message.author.display_avatar.url)
            except Exception:
                pass
            embed.set_footer(text="Meet the requirements to auto-earn the role & enter the world channel! • Admins: `world setup`")
            _tf = apply_theme(embed)
            await message.reply(embed=embed, file=_tf)
            return
        
        # ATTACK / FIGHT / HUNT
        if cmd in ["attack", "fight", "hunt", "hit", "damage", "strike"]:
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first! Say: `start warrior` or `start mage`")
                return
            
            # CO-OP: if you're helping someone, your attack hits THEIR enemy
            if user_id in helping:
                owner = helping[user_id]
                ofight = get_fight(owner)
                if not ofight:
                    helping.pop(user_id, None)
                    fight_helpers.get(owner, set()).discard(user_id)
                    await message.reply("🛡️ Their fight is over — you left help mode. Your next `attack` starts your **own** fight.")
                    return
                cdmg = random.randint(int(p["atk"] * 0.7), int(p["atk"] * 1.3))
                if random.random() < p["crit"]:
                    cdmg = int(cdmg * 1.5)
                cnew = max(0, ofight["enemy_hp"] - cdmg)
                if cnew <= 0:
                    _m = get_active_multipliers(message.guild.id if message.guild else 0)
                    base_xp, base_gold = ofight["enemy_xp"], ofight["enemy_gold"]
                    recipients = set(fight_helpers.get(owner, set())) | {owner}
                    qexec("DELETE FROM fights WHERE user_id=?", (owner,))
                    for rid in recipients:
                        gm = guild_income_mult(rid)
                        qexec("UPDATE players SET gold=gold+?, xp=xp+?, kills=kills+1 WHERE user_id=?",
                              (int(base_gold * _m["gold"] * gm), int(base_xp * _m["xp"] * gm), rid))
                        resolve_levels(rid)
                        mark_player_dirty(rid)
                    for h in list(fight_helpers.get(owner, set())):
                        helping.pop(h, None)
                    fight_helpers.pop(owner, None)
                    await message.reply(f"🛡️⚔️ **CO-OP KILL!** The **{ofight['enemy_name']}** falls! Everyone earned 💰{int(base_gold):,}+ & ⭐{int(base_xp):,}+. Help mode ended.")
                    return
                qexec("UPDATE fights SET enemy_hp=?, updated_at=? WHERE user_id=?", (cnew, ts(), owner))
                mark_fight_dirty(owner)
                await message.reply(f"🛡️ You strike for **{cdmg}**! <@{owner}>'s **{ofight['enemy_name']}** HP: {cnew}. Keep attacking!")
                return
            
            fight = get_fight(user_id)
            if not fight:
                enemy = make_enemy(p["level"], p["zone"])
                save_fight(user_id, enemy)
                # ~40% chance the encounter is an ambush squad with choices
                if random.random() < 0.4:
                    embed = discord.Embed(
                        title="🚨 AMBUSH!",
                        description=f"A squad of **{enemy['name']}s** [Lvl {enemy['level']}] ambushed you!\nHP: {enemy['hp']} 💓\n\n🏃 Run • 🗡️ Fight • 🛡️ Ping Guild for help",
                        color=discord.Colour(0xE53935))
                    _tf = apply_theme(embed)
                    await message.reply(embed=embed, view=EncounterView(user_id), file=_tf)
                    return
                emoji_anim = "⚡ 🔥 💥 ⚡ 🔥 💥 ⚡ 🔥 💥" * 6
                await message.reply(f"{emoji_anim}\n⚔️ A WILD **{enemy['name']}** (Lvl {enemy['level']}) APPEARS! ⚔️\nHP: {enemy['hp']} 💓\nSay `attack` to STRIKE!\n{emoji_anim}")
                return
            
            # Continue fight
            eq = get_equipment(user_id)
            is_ak47 = eq.get("weapon") == "ak-47"
            _es = effective_stats(p)
            # elemental matchup: equipped-weapon element vs enemy element
            player_elem = ""
            _wn = (eq.get("weapon") or "").lower()
            for _ek, _ev in V.ELEMENTS.items():
                if _ev["adj"].lower() in _wn:
                    player_elem = _ek
                    break
            enemy_elem = V.enemy_element(fight["enemy_name"])
            _ematch = V.element_matchup(player_elem, enemy_elem) if player_elem else 1.0

            dmg = random.randint(int(_es["atk"] * 0.7), int(_es["atk"] * 1.3))
            if is_ak47:
                dmg *= 100 # Huge AK-47 multiplier
            dmg = int(dmg * _ematch)

            is_crit = random.random() < _es["crit"]
            if is_crit:
                dmg = int(dmg * 1.5)
                dmg_text = f"💥 CRIT! {V.fmt(dmg)} damage!"
                if is_ak47: dmg_text = f"🔫💀 **BRRRRRRRT!** AK-47 sprays {V.fmt(dmg)} damage in a hail of lead! 💀🔫"
            else:
                dmg_text = f"⚡ {V.fmt(dmg)} damage!"
                if is_ak47: dmg_text = f"💥 **BANG BANG!** AK-47 rips through the enemy for {V.fmt(dmg)} damage!"
            if player_elem:
                _pe = V.ELEMENTS[player_elem]["emoji"]
                if _ematch > 1.0:
                    dmg_text += f"  {_pe}💥 super-effective!"
                elif _ematch < 1.0:
                    dmg_text += f"  {_pe}…resisted"

            # auto-cast class skill when mana fills, then reset mana
            skill_heal, skill_shield, skill_txt = 0, 0.0, ""
            _maxmana = p["max_mana"] or 1
            _mana = min(_maxmana, (p["mana"] or 0) + max(5, int(_maxmana * 0.25)))
            if _mana >= _maxmana:
                _sk = V.cast_skill(p["class_name"], _es["atk"], fight["enemy_hp"],
                                   fight["enemy_max_hp"], player_elem, enemy_elem)
                dmg += _sk["damage"]
                skill_heal, skill_shield = _sk["heal"], _sk["shield"]
                _mana = 0
                _extra = ""
                if _sk["damage"]:
                    _extra += f" +{V.fmt(_sk['damage'])} dmg"
                if skill_heal:
                    _extra += f" +{V.fmt(skill_heal)} HP"
                if skill_shield:
                    _extra += f" 🛡️-{int(skill_shield * 100)}% next hit"
                skill_txt = f"\n{_sk['text']}{_extra}"
            qexec("UPDATE players SET mana = ? WHERE user_id = ?", (_mana, user_id))
            dmg_text += skill_txt

            new_enemy_hp = max(0, fight["enemy_hp"] - dmg)
            
            if new_enemy_hp <= 0:
                _mult = get_active_multipliers(message.guild.id if message.guild else 0)
                _gmult = guild_income_mult(user_id)
                xp_gain = int(fight["enemy_xp"] * _mult["xp"] * _gmult)
                gold_gain = int(fight["enemy_gold"] * _mult["gold"] * _gmult)
                _bonus_txt = ""
                if _mult["xp"] > 1 or _mult["gold"] > 1:
                    _bonus_txt = f"\n🎉 Event bonus active! (XP ×{_mult['xp']:g}, Gold ×{_mult['gold']:g})"
                if _gmult > 1:
                    _bonus_txt += f"\n🏰 Guild boost: ×{_gmult:.1f} money & XP"
                qexec("DELETE FROM fights WHERE user_id = ?", (user_id,))
                qexec("UPDATE players SET gold = gold + ?, xp = xp + ?, kills = kills + 1, total_damage_dealt = total_damage_dealt + ? WHERE user_id = ?",
                      (gold_gain, xp_gain, dmg, user_id))
                # Quest progression
                ok, qmsg = progress_quest(user_id, "slayer")
                if ok: _bonus_txt += f"\n{qmsg}"
                
                if (p["zone"] or "").lower() == LAST_ZONE:
                    _shards = max(1, int(random.randint(1, 4) * _mult["luck"]))
                    add_shards(user_id, _shards)
                    _bonus_txt += f"\n{CURRENCY_EMOJI} +{_shards} {CURRENCY_NAME}!"
                gained = resolve_levels(user_id)
                mark_player_dirty(user_id)
                level_txt = ""
                if gained:
                    p2 = get_player(user_id)
                    level_txt = f"\n🆙 **LEVEL UP!** You are now **Level {gained[-1]}**!"
                    member = message.author if isinstance(message.author, discord.Member) else None
                    newly = await sync_player_roles(member, p2)
                    for w in newly:
                        level_txt += f"\n🌍 Unlocked **{w['name']}** — earned role **{w['role']}**!"
                emoji_anim = "🎊 🎉 🎁 🎊 🎉 🎁 🎊 🎉 🎁" * 6
                drop_txt = ""
                if random.random() < 0.45:
                    _drop = grant_rich_drop(user_id, p["level"], p["zone"], _mult.get("luck", 1.0))
                    if _drop:
                        drop_txt = "\n" + V.drop_banner(_drop)
                await message.reply(f"{emoji_anim}\n{dmg_text}\n🏆 **{fight['enemy_name']} DEFEATED!** 🏆\n💰💰 +{gold_gain} GOLD! 💰💰\n⭐⭐ +{xp_gain} XP! ⭐⭐{level_txt}{_bonus_txt}{drop_txt}\n{emoji_anim}")
                return
            
            # boss multi-phase: announce on phase change + scale enemy hits
            _old_idx, _, _ = V.boss_phase(fight["enemy_hp"], fight["enemy_max_hp"])
            _new_idx, _plabel, _patk = V.boss_phase(new_enemy_hp, fight["enemy_max_hp"])
            phase_txt = ""
            if _new_idx > _old_idx and fight["enemy_max_hp"] >= 500:
                phase_txt = "\n" + V.boss_phase_banner(fight["enemy_name"], _plabel, enemy_elem)

            _raw_edmg = int(random.randint(fight["enemy_atk"] - 3, fight["enemy_atk"] + 2) * _patk)
            if skill_shield:
                _raw_edmg = int(_raw_edmg * (1.0 - skill_shield))
            enemy_dmg = max(1, _raw_edmg - _es["defense"])
            _cur_hp = min(_es["max_hp"], (p["hp"] or 0) + skill_heal)
            new_player_hp = max(0, _cur_hp - enemy_dmg)

            qexec("UPDATE fights SET enemy_hp = ?, updated_at = ? WHERE user_id = ?",
                  (new_enemy_hp, ts(), user_id))
            qexec("UPDATE players SET hp = ? WHERE user_id = ?", (new_player_hp, user_id))
            mark_fight_dirty(user_id)
            mark_player_dirty(user_id)
            
            if new_player_hp <= 0:
                qexec("DELETE FROM fights WHERE user_id = ?", (user_id,))
                qexec("UPDATE players SET deaths = deaths + 1, hp = max_hp WHERE user_id = ?", (user_id,))
                mark_player_dirty(user_id)
                emoji_anim = "💎 ✨ 🌟 💎 ✨ 🌟 💎 ✨ 🌟" * 5
                await message.reply(f"{emoji_anim}\n{dmg_text}\n☠️ YOU WERE DEFEATED BY **{fight['enemy_name']}**! ☠️\n{emoji_anim}")
                return
            
            _een = V.ELEMENTS.get(enemy_elem, {}).get("emoji", "")
            await message.reply(
                f"{dmg_text}{phase_txt}\n"
                f"⚔️ **{fight['enemy_name']}** {_een} HP: {V.fmt(new_enemy_hp)}/{V.fmt(fight['enemy_max_hp'])}\n"
                f"{V.hp_color_bar(new_player_hp, _es['max_hp'])}\n"
                f"❤️ YOUR HP: {V.fmt(new_player_hp)}/{V.fmt(_es['max_hp'])}\n\nSay `attack` again! ⚡💥")
            return
        
        # ASTRAL SHARD SHOP (endgame currency)
        if any(k in content for k in ["astralshop", "currency shop", "shard shop", "astral shop", "void shop", "currency store"]):
            if not get_player(user_id):
                await message.reply("❌ Create character first!"); return
            embed = discord.Embed(
                title=f"{CURRENCY_EMOJI} ASTRAL EXCHANGE {CURRENCY_EMOJI}",
                description=f"Spend **{CURRENCY_NAME}** ({CURRENCY_EMOJI}) — earned only in **{LAST_ZONE.title()}** (and future endgame zones).\nBuy **magma/void armor**, **custom enchants**, and **exclusive roles**.",
                color=discord.Colour(0x7E57C2))
            embed.add_field(name=f"{CURRENCY_EMOJI} Your Balance", value=f"**{get_shards(user_id):,}** {CURRENCY_EMOJI}", inline=False)
            embed.set_footer(text="Use the dropdowns • merge enchants with `merge [name] [tier]` • apply with `apply [name] [tier]`")
            _tf = apply_theme(embed)
            await message.reply(embed=embed, view=CurrencyShopView(), file=_tf)
            return
        
        # MERGE custom enchants (2× tier N -> 1× tier N+1)
        if content.startswith("merge"):
            if not get_player(user_id):
                await message.reply("❌ Create character first!"); return
            arg = message.content[len("merge"):].strip()
            if not arg or arg.lower() in ("list", "help"):
                fams = "\n".join(f"🔮 {f}" for f in ENCHANT_FAMILIES)
                await message.reply(f"**Custom Enchants** (T1→T{ENCHANT_TIER_MAX}, merge 2→1):\n{fams}\n\nUse: `merge [name] [tier]` — e.g. `merge inferno protection 1`")
                return
            toks = arg.split()
            tier = None
            if toks and toks[-1].lower().lstrip("t").isdigit():
                tier = int(toks[-1].lower().lstrip("t")); toks = toks[:-1]
            fam_name = " ".join(toks).strip()
            if tier is None or not fam_name:
                await message.reply("Use: `merge [name] [tier]` — e.g. `merge frost ward 2`"); return
            ok, msg = merge_enchant(user_id, fam_name, tier)
            await message.reply(("✅ " if ok else "❌ ") + msg)
            return
        
        # APPLY a custom enchant to equipped armor
        if content.startswith("apply"):
            if not get_player(user_id):
                await message.reply("❌ Create character first!"); return
            arg = message.content[len("apply"):].strip()
            toks = arg.split()
            tier = None
            if toks and toks[-1].lower().lstrip("t").isdigit():
                tier = int(toks[-1].lower().lstrip("t")); toks = toks[:-1]
            fam_name = " ".join(toks).strip()
            if tier is None or not fam_name:
                await message.reply("Use: `apply [enchant name] [tier]` to enchant your equipped armor."); return
            ok, msg = apply_enchant(user_id, fam_name, tier)
            await message.reply(("✅ " if ok else "❌ ") + msg)
            return
        
        # HEAL / POTION
        if cmd in ["heal", "potion", "drink", "rest", "recover"]:
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            potion = db.execute("SELECT * FROM inventory WHERE user_id = ? AND item_name LIKE '%potion%' LIMIT 1", (user_id,)).fetchone()
            if not potion:
                await message.reply("❌ No potions! Use `shop` to buy.")
                return
            
            heal_amount = 100
            new_hp = min(p["max_hp"], p["hp"] + heal_amount)
            qexec("UPDATE players SET hp = ? WHERE user_id = ?", (new_hp, user_id))
            qexec("UPDATE inventory SET qty = qty - 1 WHERE user_id = ? AND item_name = ?", (user_id, potion["item_name"]))
            mark_player_dirty(user_id)
            emoji_anim = "🎪 ✨ 🎨 🎪 ✨ 🎨 🎪 ✨ 🎨" * 5
            await message.reply(f"{emoji_anim}\n🧪✨ USED **{potion['item_name'].upper()}**! ✨🧪\n❤️ HP: {p['hp']} → {new_hp} ❤️\n{emoji_anim}")
            return
        
        # STATUS / PROFILE
        if any(word in content for word in ["status", "stats", "profile", "me", "level", "character"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character! Say: `start warrior` (or mage, rogue, ranger, paladin, druid)")
                return
            
            # Real leveling: resolve any pending level-ups, then show progress on the curve
            resolve_levels(user_id)
            p = get_player(user_id)
            xp_total = xp_to_next(p["level"])
            xp_progress = p["xp"]
            xp_needed = max(0, xp_total - xp_progress)
            
            embed = discord.Embed(
                title=starry_box(f"⚔️✨ {p['name']} - {get_label('level')} {p['level']} ✨⚔️"),
                description=f"🎭 Class: **{p['class_name'].upper()}** 🎭",
                color=level_color(p["level"])
            )
            try:
                embed.set_thumbnail(url=message.author.display_avatar.url)
            except Exception:
                pass
            embed.add_field(name=get_label("hp"), value=f"💓 {p['hp']}/{p['max_hp']} 💓", inline=True)
            embed.add_field(name=get_label("mana"), value=f"✨ {p['mana']}/{p['max_mana']} ✨", inline=True)
            embed.add_field(name=get_label("atk"), value=f"💥 {p['atk']} 💥", inline=True)
            embed.add_field(name=get_label("defense"), value=f"🔒 {p['defense']} 🔒", inline=True)
            embed.add_field(name=get_label("crit"), value=f"⭐ {p['crit']*100:.0f}% ⭐", inline=True)
            embed.add_field(name=get_label("prestige"), value=f"🌟 {p['prestige']} | ♻️ {p['rebirths']}", inline=True)
            embed.add_field(name=get_label("shards"), value=f"{p['astral_shards']:,}", inline=True)
            embed.add_field(name=get_label("gold"), value=f"💵 {p['gold']:,} 💵", inline=True)
            embed.add_field(name=get_label("kills"), value=f"💀 {p['kills']} 💀", inline=True)
            embed.add_field(name=get_label("zone"), value=f"📍 {p['zone'].title()} 📍", inline=True)
            embed.add_field(
                name=f"{get_label('xp')} — {xp_progress:,}/{xp_total:,} (need {xp_needed:,})",
                value=f"{xp_bar(xp_progress, xp_total)}",
                inline=False,
            )
            embed.set_footer(text=starry_box("🎮 Type `menu` for all commands • `worlds` to see unlocks"))
            emoji_bar = "⚔️✨🎭💪🏆🌟💫⚡🔥💎"
            _tf = apply_theme(embed)
            await message.reply(f"{emoji_bar}", embed=embed, file=_tf)
            return
        
        # GEAR PREVIEW - Visual character with equipped items
        if any(word in content for word in ["gear", "preview", "look", "appearance", "outfit"]) and "inventory" not in content.lower():
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            eq = get_equipment(user_id)
            power = 0
            
            # Calculate total equipped power
            for slot in ["weapon", "armor", "accessory"]:
                item_name = eq.get(slot)
                if item_name:
                    item = db.execute("SELECT power FROM inventory WHERE user_id = ? AND item_name = ?", 
                                    (user_id, item_name)).fetchone()
                    if item:
                        power += (item["power"] if item["power"] else 0)
            
            try:
                gear_preview = generate_character_gear_preview(eq, p['name'], p['level'], power)
                file = discord.File(gear_preview, filename="gear_preview.png")
            except Exception as e:
                print(f"Gear preview generation error: {e}")
                file = None
            
            embed = discord.Embed(
                title=f"🎭 {p['name']}'s Gear Loadout",
                description="Your current equipped items and appearance",
                color=discord.Colour.gold()
            )
            if file:
                embed.set_image(url="attachment://gear_preview.png")
            embed.add_field(name="⚔️ Weapon", value=eq.get('weapon') or "None", inline=True)
            embed.add_field(name="🛡️ Armor", value=eq.get('armor') or "None", inline=True)
            embed.add_field(name="💍 Accessory", value=eq.get('accessory') or "None", inline=True)
            embed.add_field(name="⚡ Total Power", value=f"{power:,}", inline=False)
            
            await message.reply(embed=embed, file=file)
            return
        
        # INVENTORY - Interactive with reactions
        if any(word in content for word in ["inventory", "items", "bag", "backpack", "gear"]) and "equip" not in content.lower():
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            inv = db.execute("SELECT * FROM inventory WHERE user_id = ? ORDER BY rarity DESC LIMIT 20", (user_id,)).fetchall()
            if not inv:
                await message.reply("📦✨ YOUR INVENTORY IS EMPTY! ✨📦")
                return
            
            inv_str = "\n".join(f"{item_display(row['item_name'], row['rarity'])} **{row['item_name']}**{enchant_label(get_enchant_level(row))} ×{row['qty']} ⚔️{row['power']}" for row in inv)
            
            embed = discord.Embed(title=f"📦✨ {p['name']}'s INVENTORY ✨📦", description=inv_str, color=rarity_color(inv[0]["rarity"]))
            try:
                embed.set_thumbnail(url=message.author.display_avatar.url)
            except Exception:
                pass
            eq = get_equipment(user_id)
            eq_lines = []
            for slot, emoji in (("weapon", "🗡️"), ("armor", "🛡️"), ("accessory", "💍")):
                it = eq.get(slot)
                eq_lines.append(f"{emoji} **{slot.title()}:** {item_display(it) + ' ' + it.title() if it else '_— empty —_'}")
            embed.add_field(name="🧍 EQUIPPED", value="\n".join(eq_lines), inline=False)
            equippable = [row for row in inv if row["item_type"] in EQUIPPABLE_TYPES]
            if equippable:
                embed.add_field(name="🔧 EQUIP", value="Pick an item from the dropdown below to equip it!", inline=False)
            embed.set_footer(text=f"Items: {len(inv)} | Gold: {p['gold']} | Level: {p['level']}")
            _tf = apply_theme(embed)
            await message.reply(embed=embed, view=EquipView(user_id, equippable) if equippable else None, file=_tf)
            return
        
        # EQUIP SYSTEM - Fixed to not conflict with inventory
        if "equip" in content and "inventory" not in content.lower():
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            # Parse item name from equip command
            equip_parts = content.split("equip")
            if len(equip_parts) < 2:
                inv = db.execute("SELECT * FROM inventory WHERE user_id = ?", (user_id,)).fetchall()
                if not inv:
                    await message.reply("❌ No items to equip!")
                    return
                
                inv_str = "\n".join(f"🔧 **{row['item_name']}** (Power: {row['power']})" for row in inv[:10])
                embed = discord.Embed(title="🔧 EQUIP MENU", description=inv_str, color=discord.Colour.gold())
                embed.add_field(name="Usage", value="Say: `equip [item name]`", inline=False)
                await message.reply(embed=embed)
                return
            
            item_name = equip_parts[1].strip().lower()
            
            # Find item in inventory
            item = db.execute("SELECT * FROM inventory WHERE user_id = ? AND LOWER(item_name) = ?", 
                            (user_id, item_name)).fetchone()
            
            if not item:
                await message.reply(f"❌ You don't have **{item_name}**!")
                return
            
            # Staff check for admin_only items
            item_cfg = SHOP_ITEMS.get(item_name)
            if item_cfg and item_cfg.get("admin_only") and not is_staff(message.author):
                await message.reply(f"❌ You do not have permission to equip **{item_name.upper()}**!")
                return
            
            # Equip based on type
            if item["item_type"] == "weapon":
                qexec("INSERT OR REPLACE INTO equipment (user_id, weapon) VALUES (?, ?)", (user_id, item["item_name"]))
            elif item["item_type"] == "armor":
                qexec("INSERT OR REPLACE INTO equipment (user_id, armor) VALUES (?, ?)", (user_id, item["item_name"]))
            elif item["item_type"] == "accessory":
                qexec("INSERT OR REPLACE INTO equipment (user_id, accessory) VALUES (?, ?)", (user_id, item["item_name"]))
            
            mark_player_dirty(user_id)
            
            emoji_anim = "✨ 🔧 ⚔️ ✨ 🔧 ⚔️ ✨ 🔧 ⚔️" * 5
            await message.reply(f"{emoji_anim}\n⚔️ **EQUIPPED: {item['item_name']}!** ⚔️\n💪 +{item['power']} Power!\n{emoji_anim}")
            return
        
        # START / CREATE CHARACTER (exclude team, guild, lobby, equip, alchemy, quest, bounty, playershop, fish, mine)
        if any(word in content for word in ["start", "create", "character", "begin", "play"]) and not any(word in content for word in ["team", "guild", "lobby", "equip", "alchemy", "quest", "bounty", "fish", "mine", "playershop", "shop"]):
            p = get_player(user_id)
            if p:
                await message.reply(f"✅ You already have **{p['name']}** the {p['class_name']}! Say `status` to view.")
                return
            
            class_choice = None
            for cls in CLASSES.keys():
                if cls in content:
                    class_choice = cls
                    break
            
            if not class_choice:
                class_list = " | ".join(CLASSES.keys())
                await message.reply(f"Choose a class:\n`{class_list}`\n\nExample: `start warrior`")
                return
            
            p = create_player(message.author, class_choice)
            
            output = f"✨ **{p['name']}** THE **{class_choice.upper()}** IS BORN! ✨\n\n"
            output += f"{get_label('hp')}: {p['hp']}\n"
            output += f"{get_label('mana')}: {p['mana']}\n"
            output += f"{get_label('atk')}: {p['atk']}"
            
            await message.reply(starry_box(output))
            return
        
        # HELP / COMMANDS
        if any(word in content for word in ["help", "commands", "how", "guide", "?"]):
            help_embed = discord.Embed(
                title="🎮 RPG Commands",
                description="Just say any of these anywhere!",
                color=discord.Colour.green()
            )
            help_embed.add_field(name="⚔️ Combat", value="`attack` `hunt` `fight` - Battle enemies\n`heal` `potion` - Recover HP", inline=False)
            help_embed.add_field(name="👤 Character", value="`start [class]` - Create character\n`status` - View stats\n`inventory` - Items", inline=False)
            help_embed.add_field(name="🏪 Shopping", value="`shop` - Buy items\n`equip [item]` - Equip gear", inline=False)
            help_embed.add_field(name="🌍 Explore", value="`zone` - Change zone\n`boss` - Fight bosses", inline=False)
            help_embed.add_field(name="🎭 Social", value="`guild` - Guild system (`donate` `invite` `upgrade`)\n`pvp [player]` - Fight players", inline=False)
            help_embed.add_field(name="🗺️ Classes", value="**warrior** | **mage** | **rogue**\n**paladin** | **ranger** | **druid**", inline=False)
            await message.reply(embed=help_embed)
            return
        
        # PLAYER MARKETPLACE (players set their own prices)
        cmd = content.split()[0]
        if cmd in ["market", "marketplace", "auction", "playershop"]:
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            words = content.split()

            # LIST AN ITEM:  market sell <item name> <price>
            if "sell" in words and words[-1].isdigit():
                price = int(words[-1])
                sidx = words.index("sell")
                item_name = " ".join(words[sidx + 1:-1]).strip().lower()
                if not item_name:
                    await message.reply("❌ Use: `market sell [item name] [price]`")
                    return
                ok, msg = market_list_item(user_id, item_name, price)
                mark_player_dirty(user_id)
                await message.reply(("✅ " if ok else "❌ ") + msg)
                return

            # BUY BY ID:  market buy <id>
            if "buy" in words:
                ids = [w for w in words if w.isdigit()]
                if ids:
                    ok, msg = market_buy(user_id, int(ids[0]))
                    await message.reply(("✅ " if ok else "❌ ") + msg)
                    return

            # BROWSE
            listings = list_market()
            if not listings:
                await message.reply("🏪 The marketplace is empty! List one with `market sell [item] [price]`.")
                return
            desc = "\n".join(
                f"`#{l['listing_id']}` {rarity_emoji(l['rarity'])} **{l['item_name']}** x{l['qty']} — 💰{l['price']} (<@{l['seller_id']}>)"
                for l in listings
            )
            embed = discord.Embed(
                title="🏪✨ PLAYER MARKETPLACE ✨🏪",
                description=desc,
                color=discord.Colour(0xFF4081),
            )
            try:
                if message.guild and message.guild.icon:
                    embed.set_thumbnail(url=message.guild.icon.url)
            except Exception:
                pass
            embed.set_footer(text="💎 Pick a category to browse • `market sell [item] [price]` to list yours")
            await message.reply(embed=embed, view=MarketCategoryView(listings))
            return
        
        # Shop — player-driven economy + rotating "Wandering Merchant" (prices fluctuate)
        if cmd in ["shop", "buy", "store", "merchant"]:
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            stock = daily_merchant_stock()

            # BUY: today's merchant stock first, then a player-market listing id
            if "buy" in content:
                for nm in stock:
                    if nm in content:
                        ok, msg = buy_merchant_item(user_id, nm)
                        await message.reply(("✅ " if ok else "❌ ") + msg)
                        return
                ids = [w for w in content.split() if w.isdigit()]
                if ids:
                    ok, msg = market_buy(user_id, int(ids[0]))
                    await message.reply(("✅ " if ok else "❌ ") + msg)
                    return
                await message.reply("🛒 That isn't in today's merchant stock. Browse player listings with `market`, or say `shop` to see the merchant.")
                return

            # Remove lootboxes from the shop display
            # (Users will now only be able to open lootboxes that drop from combat)
            
            # DISPLAY: merchant stock + a peek at the player market
            lines = [
                f"{item_display(nm, SHOP_ITEMS[nm]['rarity'])} **{nm}** — 💰{dynamic_price(nm):,}  _(base {SHOP_ITEMS[nm]['price']:,})_"
                for nm in stock if nm not in LOOT_BOXES
            ]
            embed = discord.Embed(
                title="🛒 THE WANDERING MERCHANT",
                description="Stock **rotates daily** & **prices fluctuate** — grab it while it's here!\n\n" + ("\n".join(lines) if lines else "_Sold out!_"),
                color=discord.Colour.gold(),
            )
            try:
                if message.guild and message.guild.icon:
                    embed.set_thumbnail(url=message.guild.icon.url)
            except Exception:
                pass
            mlistings = list_market()
            if mlistings:
                preview = "\n".join(
                    f"`#{l['listing_id']}` {rarity_emoji(l['rarity'])} **{l['item_name']}** — 💰{l['price']:,}"
                    for l in mlistings[:5]
                )
                embed.add_field(name="🏪 Player Market (the real economy)", value=preview + "\n…say `market` to see all & buy", inline=False)
            else:
                embed.add_field(name="🏪 Player Market", value="No player listings yet — sell yours with `market sell [item] [price]`!", inline=False)
            embed.set_footer(text="Most gear comes from players & drops — the merchant is just daily luck!")
            await message.reply(embed=embed, view=MerchantView(stock))
            return
        
        # SECRET ATTACK
        cleaned_content = " ".join(content.split())
        if cleaned_content == "fidget spinner dickbender whirlpool superduper shitstain attack 9000":
            p = get_player(user_id)
            if p:
                await message.reply("🌀🌀🌀 **TOTAL ANNIHILATION!** 🌀🌀🌀\n💀 INFINITE DAMAGE DEALT! THE ENEMY HAS CEASED TO EXIST!")
            else:
                await message.reply("🌀🌀🌀 **TOTAL ANNIHILATION!** (But you have no character to execute it!)")
            return

        # DUNGEON
        if any(word in content for word in ["dungeon", "raid", "explore"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            dungeon = db.execute("SELECT * FROM dungeons WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
            if not dungeon:
                floor = 1
                difficulty = random.randint(1, 3)
                qexec("INSERT INTO dungeons(user_id, dungeon_name, floor, started_at, last_floor_at) VALUES(?,?,?,?,?)",
                      (user_id, f"Abyss Lvl {difficulty}", floor, ts(), ts()))
                await message.reply(f"🏚️ Entered **Abyss Level {difficulty}**!\nFloor: {floor}\nSay `attack` to fight!")
            else:
                await message.reply(f"🏚️ **{dungeon['dungeon_name']}** - Floor {dungeon['floor']}\nSay `attack` to continue!")
            return
        
        # BOSS FIGHT
        if any(word in content for word in ["boss", "raid", "legendary", "titan"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            bosses = ["Dragon", "Void King", "Leviathan", "Dark Lord", "Celestial Titan"]
            boss_name = random.choice(bosses)
            boss_hp = 500 + (p["level"] * 30)
            
            enemy = {
                "name": f"**{boss_name}** (BOSS)",
                "level": p["level"] + 10,
                "hp": boss_hp,
                "max_hp": boss_hp,
                "atk": p["atk"] + 15,
                "def": p["defense"] + 10,
                "xp": int(500 * (p["level"] / 10)),
                "gold": int(1000 * (p["level"] / 10)),
            }
            save_fight(user_id, enemy)
            await message.reply(f"🔥 **{boss_name}** APPEARS!\nHP: {boss_hp}\n⚠️ EXTREME DANGER! Say `attack` to fight!")
            return
        
        # TEAM SYSTEM (Max 4 people, auto creates channel)
        if "team" in content and "create character" not in content.lower():
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "create" in content:
                team_name = content.split("create")[-1].strip()
                if not team_name or len(team_name) < 2:
                    await message.reply("❌ `team create [name] @user1 @user2 @user3`")
                    return
                
                # Count mentions
                mentions = message.mentions
                if len(mentions) > 3:  # Leader + 3 others = 4 max
                    await message.reply("❌ Max 4 team members!")
                    return
                
                # Check if leader already in team
                existing_team = db.execute("SELECT * FROM team_members WHERE user_id = ?", (user_id,)).fetchone()
                if existing_team:
                    await message.reply("❌ You're already in a team!")
                    return
                
                # Create unique team name with timestamp
                unique_team_name = f"{team_name[:20]}_{ts()}"
                
                # Create team
                qexec("INSERT INTO teams (team_name, leader_id, member_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                      (unique_team_name, user_id, len(mentions) + 1, ts(), ts()))
                
                team_id = db.execute("SELECT team_id FROM teams WHERE team_name = ?", (unique_team_name,)).fetchone()["team_id"]
                
                # Collect all members (leader + mentions, no duplicates)
                all_members = {user_id}  # Start with leader
                for member in mentions:
                    all_members.add(member.id)
                
                # Add all members to team (no duplicates)
                for member_id in all_members:
                    try:
                        qexec("INSERT OR IGNORE INTO team_members (team_id, user_id, joined_at) VALUES (?, ?, ?)", 
                              (team_id, member_id, ts()))
                    except:
                        pass
                
                # Try to create channel
                try:
                    guild = message.guild
                    channel_name = f"👥-{team_name.lower().replace(' ', '-')}"[:32]
                    
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    }
                    
                    for member_id in all_members:
                        try:
                            member_obj = guild.get_member(member_id)
                            if member_obj:
                                overwrites[member_obj] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                        except:
                            pass
                    
                    team_channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
                    qexec("UPDATE teams SET channel_id = ? WHERE team_id = ?", (team_channel.id, team_id))
                    await team_channel.send(f"👥 **{team_name}** team created!\nLeader: <@{user_id}>")
                except Exception as e:
                    print(f"Could not create team channel: {e}")
                
                mark_player_dirty(user_id)
                emoji_anim = "👥 🎉 ⚔️ 👥 🎉 ⚔️ 👥 🎉 ⚔️" * 5
                await message.reply(f"{emoji_anim}\n👥 **TEAM CREATED: {team_name}!** 👥\n👫 Members: {len(all_members)}/4\n{emoji_anim}")
                return
            
            if "list" in content:
                teams = db.execute("SELECT * FROM teams ORDER BY member_count DESC LIMIT 10").fetchall()
                if not teams:
                    await message.reply("No teams yet!")
                    return
                
                teams_str = "\n".join(f"👥 **{t['team_name']}** - {t['member_count']}/4 members | Leader: <@{t['leader_id']}>" for t in teams)
                embed = discord.Embed(title="👥✨ TEAMS ✨👥", description=teams_str, color=discord.Colour.purple())
                await message.reply(embed=embed)
                return
            
            return
        
        # LOBBY SYSTEM (Max 4 people, wait for game start)
        if "lobby" in content:
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "create" in content:
                lobby_name = content.split("create")[-1].strip() or f"{p['name']}'s Lobby"
                
                # Check max lobbies
                user_lobbies = db.execute("SELECT * FROM lobbies WHERE creator_id = ? AND status = ?", 
                                         (user_id, "waiting")).fetchone()
                if user_lobbies:
                    await message.reply("❌ You already have an open lobby!")
                    return
                
                qexec("INSERT INTO lobbies (lobby_name, creator_id, created_at) VALUES (?, ?, ?)",
                      (lobby_name[:30], user_id, ts()))
                
                lobby_id = db.execute("SELECT lobby_id FROM lobbies WHERE creator_id = ? ORDER BY created_at DESC LIMIT 1",
                                     (user_id,)).fetchone()["lobby_id"]
                
                qexec("INSERT INTO lobby_members (lobby_id, user_id, joined_at) VALUES (?, ?, ?)",
                      (lobby_id, user_id, ts()))
                
                mark_player_dirty(user_id)
                emoji_anim = "🎪 👥 🎮 🎪 👥 🎮 🎪 👥 🎮" * 5
                await message.reply(f"{emoji_anim}\n🎮 **LOBBY CREATED: {lobby_name}!** 🎮\n👥 1/4 players\n{emoji_anim}")
                return
            
            if "list" in content:
                lobbies = db.execute("SELECT * FROM lobbies WHERE status = ? ORDER BY created_at DESC LIMIT 10", 
                                    ("waiting",)).fetchall()
                if not lobbies:
                    await message.reply("No open lobbies!")
                    return
                
                lobbies_str = "\n".join(f"🎮 **{l['lobby_name']}** - {l['current_players']}/4 players | Creator: <@{l['creator_id']}>" 
                                       for l in lobbies)
                embed = discord.Embed(title="🎮 OPEN LOBBIES 🎮", description=lobbies_str, color=discord.Colour.blue())
                await message.reply(embed=embed)
                return
            
            if "join" in content:
                # Parse lobby name or ID
                lobby_id_str = content.split("join")[-1].strip()
                
                try:
                    lobby_id = int(lobby_id_str) if lobby_id_str.isdigit() else None
                except:
                    lobby_id = None
                
                if not lobby_id:
                    await message.reply("❌ `lobby join [lobby_id]` or `lobby list`")
                    return
                
                lobby = db.execute("SELECT * FROM lobbies WHERE lobby_id = ? AND status = ?", 
                                  (lobby_id, "waiting")).fetchone()
                
                if not lobby:
                    await message.reply("❌ Lobby not found or already started!")
                    return
                
                if lobby["current_players"] >= lobby["max_players"]:
                    await message.reply("❌ Lobby is full!")
                    return
                
                # Check if already in lobby
                already_in = db.execute("SELECT * FROM lobby_members WHERE lobby_id = ? AND user_id = ?",
                                       (lobby_id, user_id)).fetchone()
                if already_in:
                    await message.reply("❌ You're already in this lobby!")
                    return
                
                qexec("INSERT INTO lobby_members (lobby_id, user_id, joined_at) VALUES (?, ?, ?)",
                      (lobby_id, user_id, ts()))
                qexec("UPDATE lobbies SET current_players = current_players + 1 WHERE lobby_id = ?", (lobby_id,))
                
                mark_player_dirty(user_id)
                emoji_anim = "🎮 ✨ 👥 🎮 ✨ 👥 🎮 ✨ 👥" * 5
                await message.reply(f"{emoji_anim}\n✅ **JOINED LOBBY!** ✅\n{emoji_anim}")
                return
            
            return
        
        # GUILD
        if any(word in content for word in ["guild", "clan", "organization"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "create" in content:
                if p["guild_id"]:
                    await message.reply("❌ You're already in a guild — **max 1 per person**. Use `guild leave`/`guild disband` first.")
                    return
                if p["gold"] < GUILD_CREATE_COST:
                    await message.reply(f"❌ Founding a guild costs **{GUILD_CREATE_COST:,} gold** — you have {p['gold']:,}. Only the mighty can lead!")
                    return
                raw_words = message.content.split()
                guild_name = " ".join(
                    w for w in raw_words
                    if w.lower() not in ("guild", "clan", "organization", "create", "make", "new", "found")
                ).strip()[:30] or "My Guild"
                
                if db.execute("SELECT 1 FROM guilds WHERE LOWER(guild_name) = ?", (guild_name.lower(),)).fetchone():
                    await message.reply(f"❌ Guild **{guild_name}** already exists!")
                    return
                
                qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (GUILD_CREATE_COST, user_id))
                qexec("INSERT INTO guilds(guild_name, leader_id, member_count, level, treasury, created_at, updated_at) VALUES(?,?,?,?,?,?,?)", 
                      (guild_name, user_id, 1, 1, 0, ts(), ts()))
                guild_id = db.execute("SELECT guild_id FROM guilds WHERE guild_name = ?", (guild_name,)).fetchone()["guild_id"]
                qexec("INSERT INTO guild_members(guild_id, user_id, rank, joined_at) VALUES(?,?,?,?)",
                      (guild_id, user_id, "Leader", ts()))
                qexec("UPDATE players SET guild_id = ? WHERE user_id = ?", (guild_id, user_id))
                mark_player_dirty(user_id)
                
                # Create private channel using new function
                try:
                    gch = await ensure_guild_channel(message.guild, guild_id, guild_name)
                    await gch.send(f"🎉 **{guild_name}** founded by <@{user_id}>! Use `guild upgrade` to power up every member.")
                except Exception as e:
                    print(f"Could not create guild channel: {e}")
                
                embed = discord.Embed(title="✨🏰 GUILD FOUNDED! 🏰✨", description=f"**{guild_name.upper()}** is born! (-{GUILD_CREATE_COST:,} gold)", color=discord.Colour.gold())
                embed.add_field(name="👑 Leader", value=f"<@{user_id}>", inline=True)
                embed.add_field(name="⭐ Level", value="1", inline=True)
                embed.set_footer(text="`guild` to manage • `guild upgrade` to boost members")
                _tf = apply_theme(embed)
                await message.reply(embed=embed, file=_tf)
                return
            
            if "join" in content:
                if p["guild_id"]:
                    await message.reply("❌ You're already in a guild — **max 1 per person**. `guild leave` first.")
                    return
                target = " ".join(
                    w for w in message.content.split()
                    if w.lower() not in ("guild", "clan", "organization", "join")
                ).strip()
                if target:
                    g = db.execute("SELECT * FROM guilds WHERE LOWER(guild_name) = ?", (target.lower(),)).fetchone()
                    if not g:
                        await message.reply(f"❌ No guild named **{target}**. Try `guild list`.")
                        return
                    ok, msg = join_guild(user_id, g["guild_id"])
                    if ok and g["channel_id"] and isinstance(message.author, discord.Member):
                        await grant_guild_channel_access(message.guild, g["channel_id"], message.author, True)
                    await message.reply(("✅ " if ok else "❌ ") + msg)
                    return
                guilds = list_guilds()
                if not guilds:
                    await message.reply("❌ No guilds exist yet! Make one with `guild create [name]` (costs 💰10M).")
                    return
                await message.reply("🏰 **Pick a guild to join:**", view=GuildJoinView(guilds))
                return
            
            if "disband" in content:
                if not p["guild_id"]:
                    await message.reply("❌ You're not in a guild!"); return
                grow = db.execute("SELECT * FROM guilds WHERE guild_id=?", (p["guild_id"],)).fetchone()
                if not grow or grow["leader_id"] != user_id:
                    await message.reply("❌ Only the **Leader** can disband the guild."); return
                if grow["channel_id"] and message.guild:
                    ch = message.guild.get_channel(grow["channel_id"])
                    if ch:
                        try:
                            await ch.delete(reason="guild disbanded")
                        except Exception:
                            pass
                qexec("UPDATE players SET guild_id=NULL WHERE guild_id=?", (grow["guild_id"],))
                qexec("DELETE FROM guild_members WHERE guild_id=?", (grow["guild_id"],))
                qexec("DELETE FROM guilds WHERE guild_id=?", (grow["guild_id"],))
                mark_player_dirty(user_id)
                await message.reply("💥 Your guild has been **disbanded**.")
                return
            
            if "leave" in content:
                if not p["guild_id"]:
                    await message.reply("❌ You're not in a guild!")
                    return
                grow = db.execute("SELECT * FROM guilds WHERE guild_id=?", (p["guild_id"],)).fetchone()
                if grow and grow["leader_id"] == user_id:
                    await message.reply("👑 You're the Leader — `guild promote @user` and demote yourself, or `guild disband` to close it.")
                    return
                if grow and grow["channel_id"] and isinstance(message.author, discord.Member):
                    await grant_guild_channel_access(message.guild, grow["channel_id"], message.author, False)
                qexec("DELETE FROM guild_members WHERE guild_id = ? AND user_id = ?", (p["guild_id"], user_id))
                qexec("UPDATE guilds SET member_count = MAX(0, member_count - 1) WHERE guild_id = ?", (p["guild_id"],))
                qexec("UPDATE players SET guild_id = NULL WHERE user_id = ?", (user_id,))
                mark_player_dirty(user_id)
                await message.reply("👋 You left your guild.")
                return
            
            # --- INVITE ---
            if "invite" in content and message.mentions:
                if not p["guild_id"]:
                    await message.reply("❌ You're not in a guild!"); return
                target = message.mentions[0]
                if target.bot:
                    await message.reply("❌ Cannot invite bots."); return
                
                # Extract optional custom message
                msg_content = message.content.replace("guild", "").replace("invite", "").replace(target.mention, "").strip()
                
                gi = db.execute("SELECT * FROM guilds WHERE guild_id=?", (p["guild_id"],)).fetchone()
                
                invite_text = f"🏰 **{message.author.name}** invited you to join their guild **{gi['guild_name']}**!"
                if msg_content:
                    invite_text += f"\n\nMessage: *{msg_content}*"

                try:
                    await target.send(invite_text, 
                                      view=GuildInviteView(p["guild_id"], gi["guild_name"], user_id))
                    await message.reply(f"✅ Invitation sent to {target.mention}!")
                except discord.Forbidden:
                    await message.reply(f"❌ Could not DM {target.mention}. They might have DMs closed.")
                return

            if "upgrade" in content:
                if not p["guild_id"]:
                    await message.reply("❌ You're not in a guild!"); return
                grow = db.execute("SELECT * FROM guilds WHERE guild_id=?", (p["guild_id"],)).fetchone()
                if grow["leader_id"] != user_id:
                    await message.reply("❌ Only the **Leader** can upgrade the guild."); return
                if grow["level"] >= GUILD_MAX_LEVEL:
                    await message.reply(f"🌟 Guild is already **MAX level {GUILD_MAX_LEVEL}** — all members enjoy **2× money & XP**!"); return
                
                cost = guild_upgrade_cost(grow["level"])
                if grow["treasury"] < cost:
                    await message.reply(f"❌ Treasury only has {grow['treasury']:,} gold (need {cost:,} to upgrade)."); return
                
                qexec("UPDATE guilds SET level = level + 1, treasury = treasury - ? WHERE guild_id=?", (cost, p["guild_id"]))
                mark_player_dirty(user_id)
                newlvl = grow["level"] + 1
                await message.reply(f"⬆️✨ **Guild upgraded to Level {newlvl}!** All members now earn **{1 + 0.1 * newlvl:.1f}× money & XP**! (-{cost:,}g from treasury)")
                return
            
            if any(k in content for k in ("promote", "demote", "kick")) and message.mentions:
                if not p["guild_id"] or not is_guild_officer(p["guild_id"], user_id):
                    await message.reply("❌ Only the guild **Leader/Admin** can manage members."); return
                tgt = message.mentions[0]
                trow = db.execute("SELECT * FROM guild_members WHERE guild_id=? AND user_id=?", (p["guild_id"], tgt.id)).fetchone()
                if not trow:
                    await message.reply("❌ That player isn't in your guild."); return
                if trow["rank"] == "Leader":
                    await message.reply("❌ You can't manage the Leader."); return
                if "kick" in content:
                    grow = db.execute("SELECT * FROM guilds WHERE guild_id=?", (p["guild_id"],)).fetchone()
                    if grow["channel_id"] and message.guild:
                        m = message.guild.get_member(tgt.id)
                        if m:
                            await grant_guild_channel_access(message.guild, grow["channel_id"], m, False)
                    qexec("DELETE FROM guild_members WHERE guild_id=? AND user_id=?", (p["guild_id"], tgt.id))
                    qexec("UPDATE guilds SET member_count=MAX(0,member_count-1) WHERE guild_id=?", (p["guild_id"],))
                    qexec("UPDATE players SET guild_id=NULL WHERE user_id=?", (tgt.id,))
                    mark_player_dirty(tgt.id)
                    await message.reply(f"👢 Kicked {tgt.mention} from the guild."); return
                ladder = ["Member", "Senior", "Admin"]
                cur = trow["rank"] if trow["rank"] in ladder else "Member"
                idx = ladder.index(cur)
                idx = min(len(ladder) - 1, idx + 1) if "promote" in content else max(0, idx - 1)
                qexec("UPDATE guild_members SET rank=? WHERE guild_id=? AND user_id=?", (ladder[idx], p["guild_id"], tgt.id))
                await message.reply(f"🎖️ {tgt.mention} is now **{ladder[idx]}** in the guild.")
                return
            
            if "list" in content:
                guilds = db.execute("SELECT * FROM guilds ORDER BY level DESC, member_count DESC LIMIT 10").fetchall()
                if not guilds:
                    await message.reply("No guilds yet! `guild create [name]` (costs 💰10M).")
                    return
                guild_str = "\n".join(f"🏰 **{g['guild_name']}** — Lvl {g['level']} • 👥 {g['member_count']} • {1 + 0.1 * g['level']:.1f}× boost" for g in guilds)
                embed = discord.Embed(title="👥✨ GUILDS ✨👥", description=guild_str, color=discord.Colour.blue())
                embed.set_footer(text="🏰 `guild join [name]` to join")
                _tf = apply_theme(embed)
                await message.reply(embed=embed, file=_tf)
                return
            
            if p["guild_id"]:
                gi = db.execute("SELECT * FROM guilds WHERE guild_id = ?", (p["guild_id"],)).fetchone()
                members = db.execute(
                    "SELECT user_id, rank FROM guild_members WHERE guild_id=? ORDER BY CASE rank WHEN 'Leader' THEN 0 WHEN 'Admin' THEN 1 WHEN 'Senior' THEN 2 ELSE 3 END LIMIT 25",
                    (p["guild_id"],)).fetchall()
                rank_emoji = {"Leader": "👑", "Admin": "🛡️", "Senior": "⭐", "Member": "👤"}
                mem_lines = "\n".join(f"{rank_emoji.get(m['rank'], '👤')} <@{m['user_id']}> — {m['rank']}" for m in members)
                lvl = gi["level"]
                embed = discord.Embed(title=f"🏰✨ {gi['guild_name'].upper()} ✨🏰", color=discord.Colour.gold())
                embed.add_field(name="⭐ Level", value=f"{lvl}/{GUILD_MAX_LEVEL}", inline=True)
                embed.add_field(name="👥 Members", value=f"{gi['member_count']}", inline=True)
                embed.add_field(name="💰 Treasury", value=f"{gi['treasury']:,}", inline=True)
                embed.add_field(name="📈 Member Boost", value=f"**{1 + 0.1 * lvl:.1f}×** money & XP", inline=True)
                if lvl < GUILD_MAX_LEVEL:
                    embed.add_field(name="⬆️ Next Upgrade", value=f"{guild_upgrade_cost(lvl):,} gold\n(`guild upgrade`)", inline=True)
                embed.add_field(name="🧑‍🤝‍🧑 Roster", value=mem_lines or "—", inline=False)
                embed.set_footer(text="Leader/Admin: `guild promote/demote/kick @user` • `guild upgrade` • `guild disband`")
                _tf = apply_theme(embed)
                await message.reply(embed=embed, file=_tf)
            else:
                await message.reply("💬 `guild list` to browse • `guild join [name]` to join • `guild create [name]` to found one (costs 💰10,000,000)")
            return
        
        # PVP
        if any(word in content for word in ["pvp", "duel", "battle player", "fight player"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            players = db.execute("SELECT * FROM players WHERE user_id != ? ORDER BY RANDOM() LIMIT 1", (user_id,)).fetchone()
            if not players:
                await message.reply("No opponents available!")
                return
            
            # PvP calculation — equipped PvP items add bonus power
            p_power = p["atk"] + p["defense"] + p["level"] + pvp_bonus(user_id)
            opp_power = players["atk"] + players["defense"] + players["level"] + pvp_bonus(players["user_id"])
            
            if random.random() * p_power > random.random() * opp_power:
                gold_gain = int(players["gold"] * 0.1)
                qexec("UPDATE players SET gold = gold + ?, pvp_wins = pvp_wins + 1 WHERE user_id = ?", (gold_gain, user_id))
                qexec("UPDATE players SET gold = MAX(0, gold - ?), pvp_losses = pvp_losses + 1 WHERE user_id = ?", (gold_gain, players["user_id"]))
                emoji_anim = "⚡ 🔥 💥 ⚡ 🔥 💥 ⚡ 🔥 💥" * 6
                await message.reply(f"{emoji_anim}\n⚔️🏆 **PVP VICTORY** vs **{players['name']}**! 🏆⚔️\n💰💰 +{gold_gain} GOLD! 💰💰\n{emoji_anim}")
            else:
                emoji_anim = "🎊 🎉 🎁 🎊 🎉 🎁 🎊 🎉 🎁" * 5
                await message.reply(f"{emoji_anim}\n⚔️💔 **PVP LOSS** vs **{players['name']}**... 💔⚔️\nGET STRONGER & TRY AGAIN!\n{emoji_anim}")
            return
        
        # ZONE
        if any(word in content for word in ["zone", "explore", "travel", "location"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            zones_list = list(ZONES.keys())
            
            if "list" in content:
                zone_str = "\n".join(f"🗺️ **{z.title()}** (Level {ZONES[z]['min_level']}+)" for z in zones_list)
                embed = discord.Embed(title="🌍 ZONES", description=zone_str, color=discord.Colour.green())
                embed.add_field(name="Current", value=p['zone'].title(), inline=False)
                await message.reply(embed=embed)
                return
            
            for zone in zones_list:
                if zone in content:
                    if p["level"] < ZONES[zone]["min_level"]:
                        await message.reply(f"❌ Need Level {ZONES[zone]['min_level']} for {zone}!")
                        return
                    qexec("UPDATE players SET zone = ? WHERE user_id = ?", (zone, user_id))
                    mark_player_dirty(user_id)
                    await message.reply(f"🌍 Traveled to **{zone.title()}**!\nEnemies are stronger here...")
                    if zone == LAST_ZONE and not p["astral_unlocked"]:
                        qexec("UPDATE players SET astral_unlocked = 1 WHERE user_id = ?", (user_id,))
                        mark_player_dirty(user_id)
                        unlock = discord.Embed(
                            title=f"{CURRENCY_EMOJI}✨ NEW UNLOCK: THE ASTRAL EXCHANGE ✨{CURRENCY_EMOJI}",
                            description=(f"You've reached **{zone.title()}** — the endgame frontier!\n\n"
                                         f"Enemies here drop **{CURRENCY_NAME}** {CURRENCY_EMOJI}, a rare currency.\n"
                                         f"Spend it in the **`astralshop`** on 🌋 magma & 🌌 void armor, 🔮 custom enchants, "
                                         f"exclusive roles, and 🧬 **secret classes**!"),
                            color=discord.Colour(0x7E57C2))
                        _tf = apply_theme(unlock)
                        await message.reply(embed=unlock, file=_tf)
                    return
            
            await message.reply("Say `zone list` to see all zones!")
            return
        
        # EQUIP
        if any(word in content for word in ["equip", "wear", "use", "wield"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            inv = db.execute("SELECT * FROM inventory WHERE user_id = ?", (user_id,)).fetchall()
            if not inv:
                await message.reply("No items to equip!")
                return
            
            for item in inv:
                if item["item_name"] in content.lower():
                    if item["item_type"] not in ["weapon", "armor", "accessory"]:
                        await message.reply(f"❌ Can't equip {item['item_name']}!")
                        return
                    
                    qexec(f"UPDATE equipment SET {item['item_type']} = ? WHERE user_id = ?",
                          (item["item_name"], user_id))
                    
                    # Update stats
                    item_power = (item["power"] if item["power"] else 0)
                    new_atk = p["atk"] + item_power
                    new_def = p["defense"] + (item_power // 2)
                    qexec("UPDATE players SET atk = ?, defense = ? WHERE user_id = ?",
                          (new_atk, new_def, user_id))
                    mark_player_dirty(user_id)
                    
                    await message.reply(f"✨ Equipped **{item['item_name']}**!\nATK: {p['atk']} → {new_atk}")
                    return
            
            await message.reply("Item not found in inventory!")
            return
        
        # LEADERBOARD
        if any(word in content for word in ["leaderboard", "top", "rank", "ranking"]):
            top = db.execute("SELECT * FROM players ORDER BY level DESC, xp DESC LIMIT 10").fetchall()
            
            if not top:
                await message.reply("No players yet!")
                return
            
            medals = ["🥇", "🥈", "🥉"]
            lb_str = "\n".join(
                f"{medals[i] if i < 3 else f'**#{i+1}**'} **{p['name']}** — Lvl {p['level']} • {p['xp']:,} XP"
                for i, p in enumerate(top)
            )
            embed = discord.Embed(title="🏆✨ LEADERBOARD ✨🏆", description=lb_str, color=discord.Colour(0xFFD700))
            try:
                if message.guild and message.guild.icon:
                    embed.set_thumbnail(url=message.guild.icon.url)
            except Exception:
                pass
            await message.reply(embed=embed)
            return
        
        # QUEST/DAILY
        if any(word in content for word in ["quest", "mission", "daily", "task"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            quests = [
                ("Defeat 5 enemies", 100, 500),
                ("Earn 1000 gold", 200, 1000),
                ("Level up once", 300, 2000),
                ("Buy 3 items", 150, 750),
            ]
            
            quest_name, xp_reward, gold_reward = random.choice(quests)
            
            embed = discord.Embed(title="📜 QUEST", color=discord.Colour.purple())
            embed.add_field(name="Goal", value=quest_name, inline=False)
            embed.add_field(name="Rewards", value=f"⭐ {xp_reward} XP | 💰 {gold_reward} Gold", inline=False)
            await message.reply(embed=embed)
            return
        
        # PET
        if any(word in content for word in ["pet", "companion", "animal"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "list" in content:
                pets_str = "\n".join(f"🐾✨ **{name}** - {info['name']} (💰💰{info['cost']}💰💰)" for name, info in PETS.items())
                embed = discord.Embed(title="🐾✨ PETS ✨🐾", description=pets_str, color=discord.Colour.blue())
                embed.set_footer(text="💎 Pick a pet from the dropdown to ADOPT! 💎")
                emoji_anim = "💎 ✨ 🌟 💎 ✨ 🌟 💎 ✨ 🌟" * 4
                await message.reply(f"{emoji_anim}", embed=embed, view=PetView())
                return
            
            if "buy" in content:
                for pet_key, pet_info in PETS.items():
                    if pet_key in content:
                        if p["gold"] < pet_info["cost"]:
                            await message.reply(f"❌ Need {pet_info['cost']} gold!")
                            return
                        
                        qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (pet_info["cost"], user_id))
                        qexec("INSERT INTO pets(user_id, pet_type, obtained_at) VALUES(?,?,?)",
                              (user_id, pet_key, ts()))
                        mark_player_dirty(user_id)
                        emoji_anim = "🎪 ✨ 🎨 🎪 ✨ 🎨 🎪 ✨ 🎨" * 5
                        await message.reply(f"{emoji_anim}\n🐾✨ OBTAINED **{pet_info['name'].upper()}**! ✨🐾\n⚡⚡ ATK+{pet_info['atk_bonus']} DEF+{pet_info['def_bonus']} ⚡⚡\n{emoji_anim}")
                        return
            
            my_pets = db.execute("SELECT * FROM pets WHERE user_id = ?", (user_id,)).fetchall()
            if my_pets:
                pets_owned = "\n".join(f"🐾✨ {PETS[p['pet_type']]['name']} (Lvl {p['level']}) ✨🐾" for p in my_pets)
                embed = discord.Embed(title="🐾✨ MY PETS ✨🐾", description=pets_owned, color=discord.Colour.blue())
                emoji_anim = "🌟 💫 ⭐ 🌟 💫 ⭐ 🌟 💫 ⭐" * 4
                await message.reply(f"{emoji_anim}", embed=embed)
            else:
                await message.reply("No pets! Say `pet list` to see available pets!")
            return
        
        # REBIRTH/PRESTIGE
        if any(word in content for word in ["rebirth", "prestige", "reset", "reincarnate"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if p["rebirths"] >= 1000:
                await message.reply("❌ You have reached the maximum rebirth limit (1000).")
                return
            
            if p["level"] < 50:
                await message.reply(f"❌ Need Level 50 to rebirth (you're {p['level']})")
                return
            
            qexec("UPDATE players SET rebirths = rebirths + 1, level = 1, xp = 0, hp = ?, max_hp = ? WHERE user_id = ?",
                  (CLASSES[p['class_name']]["hp"], CLASSES[p['class_name']]["hp"], user_id))
            mark_player_dirty(user_id)
            emoji_anim = "⚡ 🔥 💥 ⚡ 🔥 💥 ⚡ 🔥 💥" * 6
            await message.reply(f"{emoji_anim}\n♻️✨ **REBORN!** REBIRTH #{p['rebirths'] + 1} ✨♻️\n✨ YOU HAVE RISEN ANEW! ✨\n{emoji_anim}")
            return
        
        # CRAFTING
        if any(word in content for word in ["craft", "create", "forge", "make"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "list" in content:
                craft_str = "\n".join(f"🔨✨ **{name}**" for name in CRAFTING_RECIPES.keys())
                embed = discord.Embed(title="🔨✨ RECIPES ✨🔨", description=craft_str, color=discord.Colour.orange())
                embed.set_footer(text="💎 Say 'craft [recipe]' to FORGE! 💎")
                emoji_anim = "🎊 🎉 🎁 🎊 🎉 🎁 🎊 🎉 🎁" * 4
                await message.reply(f"{emoji_anim}", embed=embed)
                return
            
            for recipe_name in CRAFTING_RECIPES.keys():
                if recipe_name in content:
                    recipe = CRAFTING_RECIPES[recipe_name]
                    if p["level"] < recipe["level"]:
                        await message.reply(f"❌ Need Level {recipe['level']} to craft {recipe_name}!")
                        return
                    
                    # Check materials
                    has_all = True
                    for mat_name, mat_qty in recipe["materials"]:
                        mat = db.execute("SELECT qty FROM inventory WHERE user_id = ? AND item_name = ?",
                                        (user_id, mat_name)).fetchone()
                        if not mat or mat["qty"] < mat_qty:
                            await message.reply(f"❌ Need {mat_qty}x {mat_name}")
                            has_all = False
                            break
                    
                    if not has_all:
                        return
                    
                    # Craft
                    for mat_name, mat_qty in recipe["materials"]:
                        qexec("UPDATE inventory SET qty = qty - ? WHERE user_id = ? AND item_name = ?",
                              (mat_qty, user_id, mat_name))
                    
                    add_item(user_id, recipe_name, "weapon", "rare", 1, 25)
                    qexec("UPDATE players SET xp = xp + ? WHERE user_id = ?", (recipe["xp"], user_id))
                    mark_player_dirty(user_id)
                    
                    emoji_anim = "💎 ✨ 🌟 💎 ✨ 🌟 💎 ✨ 🌟" * 5
                    await message.reply(f"{emoji_anim}\n🔨✨ CRAFTED **{recipe_name.upper()}**! ✨🔨\n⭐⭐ +{recipe['xp']} XP! ⭐⭐\n{emoji_anim}")
                    return
            
            await message.reply("Say `craft list` to see recipes!")
            return
        
        # TRADE/MARKETPLACE
        if any(word in content for word in ["trade", "sell", "auction", "marketplace", "market"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            inv = db.execute("SELECT * FROM inventory WHERE user_id = ?", (user_id,)).fetchall()
            
            if "sell" in content:
                if not inv:
                    await message.reply("❌ No items to sell!")
                    return
                
                for item in inv:
                    if item["item_name"].lower() in content.lower():
                        gold_get = item["value"] * item["qty"]
                        qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (gold_get, user_id))
                        qexec("DELETE FROM inventory WHERE user_id = ? AND item_name = ?", (user_id, item["item_name"]))
                        mark_player_dirty(user_id)
                        await message.reply(f"💰 Sold **{item['item_name']}** x{item['qty']} for {gold_get} gold!")
                        return
                
                view = SellView(user_id, inv)
                sell_embed = discord.Embed(
                    title="💰 SELL MENU",
                    description="Pick an item from the dropdown to sell it to the shop for gold.",
                    color=discord.Colour.gold(),
                )
                await message.reply(embed=sell_embed, view=view)
                return
            
            if "list" in content or "market" in content:
                listings = list_market()
                if not listings:
                    await message.reply("🏪 Marketplace empty! Use `market sell [item] [price]` to list one.")
                    return
                desc = "\n".join(
                    f"`#{l['listing_id']}` {rarity_emoji(l['rarity'])} **{l['item_name']}** x{l['qty']} — 💰{l['price']}"
                    for l in listings
                )
                embed = discord.Embed(title="🏪 PLAYER MARKETPLACE", description=desc, color=discord.Colour.gold())
                await message.reply(embed=embed, view=MarketView(listings))
                return
            
            return
        
        # PLAYER SHOP (Personal vendor stalls)
        if any(word in content for word in ["playershop", "player shop", "vendor", "stall"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            inv = db.execute("SELECT * FROM inventory WHERE user_id = ?", (user_id,)).fetchall()
            
            # Just "playershop" shows category menu
            if not any(cmd in content for cmd in ["setup", "create", "list", "browse", "stock", "add"]):
                embed = discord.Embed(
                    title="🏪 PLAYER SHOP BAZAAR 🏪",
                    description="Browse player-run shops by category and find the best deals! 💰\n\nSelect a category below:",
                    color=discord.Colour.gold()
                )
                embed.set_footer(text="Tap a category to see all items from that type")
                await message.reply(embed=embed, view=PlayerShopMainView())
                return
            
            if "setup" in content or "create" in content:
                if not inv:
                    await message.reply("❌ You need items to create a shop!")
                    return
                
                qexec("INSERT OR REPLACE INTO player_shops (user_id, shop_name, active, created_at) VALUES (?, ?, ?, ?)",
                      (user_id, f"{p['name']}'s Emporium", 1, ts()))
                mark_player_dirty(user_id)
                
                emoji_anim = "🏪 ✨ 🎪 🏪 ✨ 🎪 🏪 ✨ 🎪" * 5
                await message.reply(f"{emoji_anim}\n🏪 **SHOP CREATED!** 🏪\n✨ Your personal vendor stall is now open! ✨\n{emoji_anim}")
                return
            
            if "list" in content or "browse" in content:
                shops = db.execute(
                    "SELECT ps.user_id, ps.shop_name, COUNT(si.item_id) as item_count FROM player_shops ps "
                    "LEFT JOIN shop_inventory si ON ps.shop_id = si.shop_id WHERE ps.active = 1 "
                    "GROUP BY ps.shop_id LIMIT 20"
                ).fetchall()
                
                if not shops:
                    await message.reply("🏪 No active player shops! Start one with `playershop setup`")
                    return
                
                # Generate banner image
                file = None
                try:
                    total_items = sum(s['item_count'] for s in shops)
                    banner = generate_shop_banner("Player Shop Bazaar", total_items)
                    file = discord.File(banner, filename="shop_banner.png")
                except Exception as e:
                    print(f"Banner generation error: {e}")
                
                shop_list = "\n".join(f"🏪 <@{s['user_id']}>'s **{s['shop_name']}** ({s['item_count']} items)" for s in shops)
                embed = discord.Embed(title="🏪 PLAYER SHOPS", description=shop_list, color=discord.Colour.gold())
                if file:
                    embed.set_image(url="attachment://shop_banner.png")
                await message.reply(embed=embed, file=file)
                return
            
            if "stock" in content or "add" in content:
                shop = db.execute("SELECT * FROM player_shops WHERE user_id = ?", (user_id,)).fetchone()
                if not shop:
                    await message.reply("❌ Create a shop first with `playershop setup`!")
                    return
                
                if not inv:
                    await message.reply("❌ No items to stock!")
                    return
                
                for item in inv[:5]:
                    qexec("INSERT INTO shop_inventory (shop_id, item_name, item_type, rarity, qty, price, listed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (shop["shop_id"], item["item_name"], item["item_type"], item["rarity"], item["qty"], item["value"] * 2, ts()))
                
                mark_player_dirty(user_id)
                await message.reply(f"📦 Stocked your shop with {min(5, len(inv))} item types!")
                return
            
            return
        
        # ENCHANT/UPGRADE (deep system — max ✦20, escalating cost & failure risk)
        if any(word in content for word in ["enchant", "upgrade", "enhance", "level up item"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            inv = db.execute("SELECT * FROM inventory WHERE user_id = ?", (user_id,)).fetchall()
            if not inv:
                await message.reply("❌ No items to enchant!")
                return
            
            target = None
            for item in inv:
                if item["item_name"].lower() in content.lower() and item["item_type"] in EQUIPPABLE_TYPES:
                    target = item
                    break
            
            if not target:
                equippable = [i for i in inv if i["item_type"] in EQUIPPABLE_TYPES]
                if not equippable:
                    await message.reply("❌ No enchantable gear! Only weapons, armor & accessories can be enchanted.")
                    return
                lines = []
                for i in equippable[:15]:
                    lvl = get_enchant_level(i)
                    tname, tglow = enchant_tier(lvl)
                    disp = f"{item_display(i['item_name'], i['rarity'])} **{i['item_name']}**"
                    if lvl >= ENCHANT_MAX:
                        lines.append(f"{disp} {tglow}✦{lvl} {tname} (MAX)")
                    elif lvl > 0:
                        lines.append(f"{disp} {tglow}✦{lvl} {tname} → next {enchant_cost(lvl):,}g ({int(enchant_success_chance(lvl)*100)}%)")
                    else:
                        lines.append(f"{disp} ✦0 → next {enchant_cost(lvl):,}g ({int(enchant_success_chance(lvl)*100)}%)")
                embed = discord.Embed(title="✨ ENCHANTING TABLE ✨", description="\n".join(lines), color=discord.Colour(0x9C27B0))
                embed.set_footer(text="Pick gear from the dropdown to enchant! Each ✦ costs more & has lower odds. Max ✦20.")
                _tf = apply_theme(embed)
                await message.reply(embed=embed, view=EnchantView(user_id, equippable), file=_tf)
                return
            
            lvl = get_enchant_level(target)
            if lvl >= ENCHANT_MAX:
                await message.reply(f"🌟 **{target['item_name']}** is already MAX enchant ✦{ENCHANT_MAX}!")
                return
            
            cost = enchant_cost(lvl)
            if p["gold"] < cost:
                await message.reply(f"❌ Need {cost:,} gold to enchant **{target['item_name']}** (✦{lvl}→✦{lvl+1}). You have {p['gold']:,}.")
                return
            
            qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (cost, user_id))
            chance = enchant_success_chance(lvl)
            if random.random() < chance:
                bonus = (lvl + 1) * 2
                new_power = (target["power"] or 0) + bonus
                qexec("UPDATE inventory SET power = ?, enchantments = ? WHERE user_id = ? AND item_name = ?",
                      (new_power, str(lvl + 1), user_id, target["item_name"]))
                mark_player_dirty(user_id)
                emoji_anim = "✨ 🌟 💫 ✨ 🌟 💫 ✨ 🌟 💫" * 4
                await message.reply(f"{emoji_anim}\n✨ **ENCHANT SUCCESS!** **{target['item_name']}** ✦{lvl} → ✦{lvl+1}!\n💥 Power {target['power'] or 0} → {new_power}  (-{cost:,}g)\n{emoji_anim}")
            else:
                mark_player_dirty(user_id)
                await message.reply(f"💔 **ENCHANT FAILED!** **{target['item_name']}** stays at ✦{lvl}. Lost {cost:,} gold. (odds were {int(chance*100)}%)")
            return
        
        # DAILY REWARD
        if any(word in content for word in ["daily", "reward", "claim", "bonus", "free gold"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            last_claim = db.execute("SELECT created_at FROM economy_log WHERE user_id = ? AND transaction_type = 'daily' ORDER BY created_at DESC LIMIT 1", 
                                   (user_id,)).fetchone()
            
            if last_claim and (ts() - last_claim["created_at"]) < 86400:
                hours_left = (86400 - (ts() - last_claim["created_at"])) // 3600
                await message.reply(f"⏰ Already claimed! Come back in {hours_left} hours.")
                return
            
            daily_gold = 500 + (p["level"] * 50)
            daily_xp = 200 + (p["level"] * 20)
            
            qexec("UPDATE players SET gold = gold + ?, xp = xp + ? WHERE user_id = ?", 
                  (daily_gold, daily_xp, user_id))
            qexec("INSERT INTO economy_log(user_id, transaction_type, amount, reason, created_at) VALUES(?,?,?,?,?)",
                  (user_id, "daily", daily_gold, "Daily reward", ts()))
            mark_player_dirty(user_id)
            
            embed = discord.Embed(title="🎁 ✨ DAILY REWARD! ✨ 🎁", color=discord.Colour.green())
            embed.add_field(name="💰 GOLD 💰", value=f"✨💫 +{daily_gold} 💫✨", inline=True)
            embed.add_field(name="⭐ XP BONUS ⭐", value=f"🌟💥 +{daily_xp} 💥🌟", inline=True)
            embed.set_footer(text="[cubewhirl](https://cdn.discordapp.com/emojis/1310200165595877387.webp?size=48&animated=true&name=cubewhirl&lossless=true) [spin](https://cdn.discordapp.com/emojis/1310199842634485881.webp?size=48&animated=true&name=spin&lossless=true) [pulse](https://cdn.discordapp.com/emojis/1310199943516598323.webp?size=48&animated=true&name=pulse&lossless=true)")
            daily_anim = "[cubebounce](https://cdn.discordapp.com/emojis/1310200248932577331.webp?size=48&animated=true&name=cubebounce&lossless=true) " * 5
            await message.reply(f"{daily_anim}", embed=embed)
            return
        
        # LOOT BOX
        if any(word in content for word in ["lootbox", "box", "crate", "chest", "open box"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "buy" in content or "open" in content:
                boxes = {"wood": 150, "iron": 450, "gold": 1200, "mythic": 5000, "legendary": 12000}
                
                for box_type, price in boxes.items():
                    if box_type in content:
                        if p["gold"] < price:
                            await message.reply(f"❌ Need {price} gold!")
                            return
                        
                        qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (price, user_id))
                        
                        # Random loot
                        rarities = ["common", "uncommon", "rare", "epic", "mythic"]
                        weights = [50, 30, 15, 4, 1] if box_type != "legendary" else [10, 20, 30, 30, 10]
                        rarity = random.choices(rarities, weights=weights)[0]
                        
                        loot_items = {
                            "common": ["herbs", "cloth", "iron ore", "copper ore"],
                            "uncommon": ["silver bar", "leather", "ancient coin", "wolf fang"],
                            "rare": ["void shard", "crystal", "dragon scale", "mana stone"],
                            "epic": ["mythic core", "godly essence", "elder rune", "celestial fragment"],
                            "mythic": ["void crystal", "legendary essence", "ancient tome"],
                        }
                        
                        item = random.choice(loot_items[rarity])
                        add_item(user_id, item, "material", rarity, random.randint(1, 3))
                        mark_player_dirty(user_id)
                        
                        emoji_anim = "🎪 ✨ 🎨 🎪 ✨ 🎨 🎪 ✨ 🎨" * 6
                        await message.reply(f"{emoji_anim}\n🎁✨ Opened **{box_type}** box! ✨🎁\n{rarity_emoji(rarity)} **{item}** acquired! {rarity_emoji(rarity)}\n{emoji_anim}")
                        return
                
                boxes_str = "\n".join(f"**{k}** - {v} gold" for k, v in boxes.items())
                embed = discord.Embed(title="🎁 LOOT BOXES", description=boxes_str, color=discord.Colour.orange())
                embed.set_footer(text="Pick a box from the dropdown to open it!")
                await message.reply(embed=embed, view=LootBoxView())
                return
            
            boxes_str = "\n".join(f"🎁 **{k.title()}** - {v} gold" for k, v in LOOT_BOXES.items())
            embed = discord.Embed(title="🎁 LOOT BOXES", description=boxes_str, color=discord.Colour.orange())
            embed.set_footer(text="Pick a box from the dropdown to open it!")
            await message.reply(embed=embed, view=LootBoxView())
            return
        
        # GAMBLE/BET
        if any(word in content for word in ["gamble", "bet", "dice", "flip", "roulette"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            bet_amount = 100
            words = content.split()
            for word in words:
                if word.isdigit():
                    bet_amount = int(word)
                    break
            
            if p["gold"] < bet_amount:
                await message.reply(f"❌ You only have {p['gold']} gold!")
                return
            
            if random.random() > 0.45:
                qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (bet_amount, user_id))
                emoji_anim = "🌟 💫 ⭐ 🌟 💫 ⭐ 🌟 💫 ⭐" * 5
                await message.reply(f"{emoji_anim}\n🎲 **🏆 JACKPOT WIN! 🏆** +{bet_amount} gold! 🎉✨\n{emoji_anim}")
            else:
                qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (bet_amount, user_id))
                emoji_anim = "⚡ 🔥 💥 ⚡ 🔥 💥 ⚡ 🔥 💥" * 5
                await message.reply(f"{emoji_anim}\n🎲 **💔 OH NO! LOST!** -{bet_amount} gold 😢\n{emoji_anim}")
            
            mark_player_dirty(user_id)
            return
        
        # BOOSTS/BUFFS
        if any(word in content for word in ["boost", "buff", "strength potion", "defense potion"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            boosts = {
                "strength potion": {"atk": 5, "cost": 200, "emoji": "💪"},
                "defense potion": {"defense": 5, "cost": 200, "emoji": "🛡️"},
                "mega boost": {"atk": 10, "defense": 10, "cost": 1000, "emoji": "⚡"},
                "godly boost": {"atk": 20, "defense": 20, "cost": 5000, "emoji": "✨"},
            }
            
            for item_name, boost in boosts.items():
                if item_name.split()[0].lower() in content.lower():
                    if p["gold"] < boost["cost"]:
                        await message.reply(f"❌ Need {boost['cost']} gold!")
                        return
                    
                    updates = []
                    if "atk" in boost:
                        qexec("UPDATE players SET atk = atk + ? WHERE user_id = ?", (boost["atk"], user_id))
                        updates.append(f"ATK+{boost['atk']}")
                    if "defense" in boost:
                        qexec("UPDATE players SET defense = defense + ? WHERE user_id = ?", (boost["defense"], user_id))
                        updates.append(f"DEF+{boost['defense']}")
                    
                    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (boost["cost"], user_id))
                    mark_player_dirty(user_id)
                    
                    emoji_anim = "🎊 🎉 🎁 🎊 🎉 🎁 🎊 🎉 🎁" * 5
                    await message.reply(f"{emoji_anim}\n{boost['emoji']} **⚡ {item_name.upper()} ACTIVATED! ⚡**\n✨ {', '.join(updates)} ✨\n{emoji_anim}")
                    return
            
            return
        
        # ACHIEVEMENTS/BADGES
        if any(word in content for word in ["achievement", "badge", "unlocked", "milestone"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            achievements = db.execute("SELECT * FROM achievements WHERE user_id = ?", (user_id,)).fetchall()
            if not achievements:
                await message.reply("🎖️ No achievements yet! Keep grinding!")
                return
            
            ach_list = "\n".join(f"🏅✨ Achievement #{i+1} ✨🏅" for i, a in enumerate(achievements[:15]))
            embed = discord.Embed(title="🎖️ ✨ YOUR ACHIEVEMENTS ✨ 🎖️", description=ach_list, color=discord.Colour.gold())
            embed.add_field(name="🌟 TOTAL UNLOCKED 🌟", value=f"💫✨ {len(achievements)} ✨💫", inline=False)
            embed.set_footer(text="[trophy](https://cdn.discordapp.com/emojis/1310200165595877387.webp?size=48&animated=true&name=trophy&lossless=true) [star](https://cdn.discordapp.com/emojis/1310199943516598323.webp?size=48&animated=true&name=star&lossless=true)")
            emoji_anim = "💎 ✨ 🌟 💎 ✨ 🌟 💎 ✨ 🌟" * 5
            await message.reply(f"{emoji_anim}\n", embed=embed)
            return
        
        # FISHING
        if any(word in content for word in ["fish", "fishing", "cast", "bait"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            fish_types = {
                "common fish": {"gold": 50, "rarity": "common", "emoji": "🐟"},
                "golden fish": {"gold": 200, "rarity": "rare", "emoji": "🟡"},
                "void fish": {"gold": 800, "rarity": "epic", "emoji": "🌀"},
                "legendary leviathan": {"gold": 3000, "rarity": "legendary", "emoji": "🐋"},
            }
            
            catch = random.choices(list(fish_types.items()), weights=[50, 30, 15, 5])[0]
            fish_name, fish_data = catch
            gold_earned = fish_data["gold"]
            
            qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (gold_earned, user_id))
            mark_player_dirty(user_id)
            
            emoji_anim = "🎣 💧 🐟 🎣 💧 🐟 🎣 💧 🐟" * 6
            await message.reply(f"{emoji_anim}\n🎣 **CAUGHT: {fish_data['emoji']} {fish_name}!** 🎣\n💰 +{gold_earned} gold! 💰\n{emoji_anim}")
            return
        
        # MINING
        if any(word in content for word in ["mine", "mining", "dig", "ore"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            ore_types = {
                "copper ore": {"gold": 80, "rarity": "common"},
                "iron ore": {"gold": 150, "rarity": "uncommon"},
                "silver ore": {"gold": 400, "rarity": "rare"},
                "mithril ore": {"gold": 1000, "rarity": "epic"},
                "void ore": {"gold": 4000, "rarity": "legendary"},
            }
            
            ore = random.choices(list(ore_types.items()), weights=[45, 30, 15, 8, 2])[0]
            ore_name, ore_data = ore
            gold_earned = ore_data["gold"]
            
            qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (gold_earned, user_id))
            mark_player_dirty(user_id)
            
            emoji_anim = "⛏️ 🪨 💎 ⛏️ 🪨 💎 ⛏️ 🪨 💎" * 6
            await message.reply(f"{emoji_anim}\n⛏️ **MINED: {ore_name}!** ⛏️\n💰 +{gold_earned} gold! 💰\n{emoji_anim}")
            return
        
        # DUEL (1v1 PVP with stakes)
        if any(word in content for word in ["duel", "challenge", "face off"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            # Check if player is challenging someone or accepting
            if "@" in content or "duel" in content:
                stake = 100
                words = content.split()
                for i, word in enumerate(words):
                    if word.isdigit():
                        stake = int(word)
                        break
                
                if p["gold"] < stake:
                    await message.reply(f"❌ Need {stake} gold to duel! You have {p['gold']}")
                    return
                
                if random.random() > 0.5:
                    reward = int(stake * 1.5)
                    qexec("UPDATE players SET gold = gold + ? WHERE user_id = ?", (reward, user_id))
                    emoji_anim = "⚔️ 🔥 💪 ⚔️ 🔥 💪 ⚔️ 🔥 💪" * 6
                    await message.reply(f"{emoji_anim}\n⚔️ **DUEL WON!** ⚔️\n💰 **+{reward} gold!** 💰\n{emoji_anim}")
                else:
                    qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (stake, user_id))
                    emoji_anim = "💔 😢 ⚔️ 💔 😢 ⚔️ 💔 😢 ⚔️" * 6
                    await message.reply(f"{emoji_anim}\n😢 **DUEL LOST!** 😢\n💸 **-{stake} gold...** 💸\n{emoji_anim}")
                
                mark_player_dirty(user_id)
                return
        
        # BOUNTIES (Kill monsters for gold/xp rewards)
        if any(word in content for word in ["bounty", "bounties", "contract", "hunt"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "list" in content:
                bounties = "🎯 **ACTIVE BOUNTIES:**\n💰 Slay 10 Goblins - 500 gold\n💰 Defeat Void King - 25000 gold\n💰 Hunt 50 Dragons - 10000 gold\n💰 Destroy Shadow Lord - 50000 gold"
                await message.reply(bounties)
                return
            
            reward_gold = random.randint(200, 2000)
            reward_xp = random.randint(500, 5000)
            
            qexec("UPDATE players SET gold = gold + ?, xp = xp + ? WHERE user_id = ?", 
                  (reward_gold, reward_xp, user_id))
            mark_player_dirty(user_id)
            
            emoji_anim = "🎯 🎪 ✨ 🎯 🎪 ✨ 🎯 🎪 ✨" * 5
            await message.reply(f"{emoji_anim}\n🎯 **BOUNTY COMPLETE!** 🎯\n💰 +{reward_gold} gold | ⭐ +{reward_xp} XP\n{emoji_anim}")
            return
        
        # ALCHEMY (Create potions & buffs)
        if any(word in content for word in ["alchemy", "brew", "potion", "alchemist"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "craft" in content or "brew" in content:
                recipes = {
                    "strength elixir": {"cost": 300, "power": 10},
                    "wisdom brew": {"cost": 250, "power": 8},
                    "defense potion": {"cost": 350, "power": 12},
                    "eternal essence": {"cost": 2000, "power": 50},
                }
                
                for recipe_name, recipe_data in recipes.items():
                    if recipe_name.split()[0].lower() in content.lower():
                        if p["gold"] < recipe_data["cost"]:
                            await message.reply(f"❌ Need {recipe_data['cost']} gold!")
                            return
                        
                        qexec("UPDATE players SET gold = gold - ? WHERE user_id = ?", (recipe_data["cost"], user_id))
                        add_item(user_id, recipe_name, "consumable", "epic", 1)
                        mark_player_dirty(user_id)
                        
                        emoji_anim = "🧪 🔮 ✨ 🧪 🔮 ✨ 🧪 🔮 ✨" * 5
                        await message.reply(f"{emoji_anim}\n🧪 **{recipe_name.upper()} BREWED!** 🧪\n✨ Powerful potion created! ✨\n{emoji_anim}")
                        return
                
                recipes_str = "\n".join(f"🧪 **{k}** - {v['cost']} gold" for k, v in recipes.items())
                await message.reply(f"🧪 **ALCHEMY RECIPES:**\n{recipes_str}")
                return
            
            return
        
        # QUESTS (Story-driven missions)
        if any(word in content for word in ["quest", "mission", "adventure"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if "list" in content:
                quests = "📜 **AVAILABLE QUESTS:**\n📜 The Lost Artifact - Lvl 10\n📜 Slay the Beast - Lvl 25\n📜 Save the Kingdom - Lvl 50\n📜 Become a Legend - Lvl 100"
                await message.reply(quests)
                return
            
            xp_reward = random.randint(1000, 5000)
            gold_reward = random.randint(500, 3000)
            
            qexec("UPDATE players SET xp = xp + ?, gold = gold + ? WHERE user_id = ?", 
                  (xp_reward, gold_reward, user_id))
            mark_player_dirty(user_id)
            
            emoji_anim = "📜 🗺️ 🏆 📜 🗺️ 🏆 📜 🗺️ 🏆" * 5
            await message.reply(f"{emoji_anim}\n📜 **QUEST COMPLETED!** 📜\n⭐ +{xp_reward} XP | 💰 +{gold_reward} gold\n{emoji_anim}")
            return
        
        # PRESTIGE (Reset for bonuses)
        if any(word in content for word in ["prestige", "reset", "ascend"]):
            p = get_player(user_id)
            if not p:
                await message.reply("❌ Create character first!")
                return
            
            if p["level"] < 50:
                await message.reply("❌ Need level 50 to prestige!")
                return
            
            prestige_bonus = p["prestige"] + 1
            qexec("UPDATE players SET prestige = ?, level = 1, xp = 0, atk = atk + ?, defense = defense + ? WHERE user_id = ?",
                  (prestige_bonus, 2 * prestige_bonus, 2 * prestige_bonus, user_id))
            mark_player_dirty(user_id)
            
            emoji_anim = "👑 ✨ 💫 👑 ✨ 💫 👑 ✨ 💫" * 6
            await message.reply(f"{emoji_anim}\n👑 **ASCENDED TO PRESTIGE {prestige_bonus}!** 👑\n✨ You're stronger than before! ✨\n{emoji_anim}")
            return
        
        # LEADERBOARDS
        if any(word in content for word in ["leaderboard", "top", "rank", "best"]):
            top_players = db.execute("""
                SELECT user_id, level, xp, gold FROM players 
                ORDER BY level DESC, xp DESC LIMIT 10
            """).fetchall()
            
            if not top_players:
                await message.reply("No players yet!")
                return
            
            leaderboard = "\n".join(f"#{i+1}. <@{p['user_id']}> - Lvl {p['level']} | {p['xp']} XP | 💰 {p['gold']}" 
                                   for i, p in enumerate(top_players))
            embed = discord.Embed(title="🏆 TOP PLAYERS LEADERBOARD 🏆", description=leaderboard, color=discord.Colour.gold())
            emoji_anim = "🏆 👑 ⭐ 🏆 👑 ⭐ 🏆 👑 ⭐" * 4
            await message.reply(f"{emoji_anim}\n", embed=embed)
            return
        
        # Default fallback
        await message.reply("💬 Try: `attack`, `status`, `shop`, `fish`, `mine`, `duel`, `bounty`, `quest`, `leaderboard`!")
    
    except Exception as exc:
        import traceback
        print("=" * 60)
        print(f"Error handling message: {message.content!r}")
        traceback.print_exc()
        print("=" * 60)
        try:
            await message.reply(f"⚠️ Error: {type(exc).__name__}: {exc}")
        except:
            pass

@tasks.loop(seconds=SAVE_INTERVAL_SECONDS)
async def autosave_loop():
    async with db_lock:
        now = ts()
        for user_id in list(dirty_players):
            db.execute("UPDATE players SET updated_at = ? WHERE user_id = ?", (now, user_id))
        for user_id in list(dirty_fights):
            db.execute("UPDATE fights SET updated_at = ? WHERE user_id = ?", (now, user_id))
        db.commit()
        dirty_players.clear()
        dirty_fights.clear()
        # Periodic WAL checkpoint (~every minute) keeps the DB file compact & durable without lag
        autosave_loop._ticks = getattr(autosave_loop, "_ticks", 0) + 1
        if autosave_loop._ticks % 12 == 0:
            try:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass


@tasks.loop(seconds=30)
async def events_loop():
    """Activate scheduled events when due and expire active ones, announcing both."""
    try:
        now = ts()
        # Activate scheduled events that have reached their start time
        due = db.execute(
            "SELECT * FROM server_events WHERE status='scheduled' AND start_at<=? AND end_at>?",
            (now, now),
        ).fetchall()
        for ev in due:
            qexec("UPDATE server_events SET status='active' WHERE event_id=?", (ev["event_id"],))
            guild = bot.get_guild(ev["guild_id"])
            info = EVENT_TYPES.get(ev["event_key"], {"name": ev["name"], "emoji": "🎉"})
            await announce_event_start(guild, info, ev["end_at"] - now)
        # End active events whose time is up
        ended = db.execute(
            "SELECT * FROM server_events WHERE status='active' AND end_at<=?",
            (now,),
        ).fetchall()
        for ev in ended:
            qexec("UPDATE server_events SET status='ended' WHERE event_id=?", (ev["event_id"],))
            guild = bot.get_guild(ev["guild_id"])
            await _announce(guild, f"🏁 The **{ev['name']}** event has ended! Thanks for playing. 🎮")
        # Mark any scheduled events that fully elapsed while offline
        qexec("UPDATE server_events SET status='ended' WHERE status='scheduled' AND end_at<=?", (now,))
    except Exception as e:
        print(f"events_loop error: {e}")

# ============================================================================
# MAIN
# ============================================================================

def bootstrap():
    """Initialize everything on startup."""
    init_db()
    ensure_theme_asset()
    print(f"✅ All systems ready!")

if __name__ == "__main__":
    bootstrap()
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\n⚠️ Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
