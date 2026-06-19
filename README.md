<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0B0B14,50:7E57C2,100:00E5FF&height=200&section=header&text=DXN1-RPG%27S&fontSize=72&fontColor=ffffff&fontAlignY=38&desc=Ultimate%20Discord%20RPG%20Bot%20v2.1&descAlignY=60&descSize=20&animation=fadeIn" width="100%"/>

<br/>

[![Discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Pillow](https://img.shields.io/badge/Pillow-Image%20Gen-FFD43B?style=for-the-badge&logo=python&logoColor=black)](https://pillow.readthedocs.io)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Version](https://img.shields.io/badge/Version-v2.1-FF4081?style=for-the-badge&logo=rocket&logoColor=white)](https://github.com/DXN1-termux/DXN1-RPG)
[![GitHub Stars](https://img.shields.io/github/stars/DXN1-termux/DXN1-RPG?style=for-the-badge&logo=github&color=FFD700)](https://github.com/DXN1-termux/DXN1-RPG/stargazers)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-00C853?style=for-the-badge&logo=checkmarx&logoColor=white)](https://github.com/DXN1-termux/DXN1-RPG)

<br/>

> **🎮 A fully autonomous Discord RPG — auto-responds to every message, auto-creates characters, and ships a complete ARPG economy out of the box. Just paste your token and go.**

<br/>

[🚀 Quick Start](#-quick-start) • [✨ Features](#-features) • [📜 Commands](#-commands) • [🛡️ Staff Tools](#️-staff-tools) • [🏗️ Architecture](#️-architecture) • [🤝 Contributing](#-contributing)

</div>

---

## 🌟 Highlights at a Glance

| | |
|--|--|
| 🎲 **8 Rarity Tiers** | Common → Chromatic with live luck-scaled RNG |
| ⚔️ **13 Unique Classes** | 2 secret classes unlockable via Astral Shards |
| 🔥 **10 Elements** | Super-effective (×1.5) / resisted (×0.75) matchups |
| 💠 **Gems & Sockets** | 7 gem types — socket into gear for permanent stat boosts |
| 🔗 **Item Sets** | Dragonlord, Voidwalker & Celestial — equip pieces for escalating bonuses |
| 🏰 **14 Gated Worlds** | Level/Prestige/Rebirth-locked channels with auto-granted roles |
| 🏪 **Dual Market System** | Wandering Merchant + full Player Shop with Pillow image cards |
| 💠 **Astral Shards** | Endgame currency — drops in Shadow Nexus, spent at the Astral Exchange |
| 👥 **Guild Diplomacy** | Peace/Alliance/Tribute pacts, treasury heists, clan wars |
| 👹 **Multi-Phase Bosses** | Awakened → Enraged → Final Form with elemental abilities |
| 📸 **Dynamic Images** | All item cards, shop banners & gear previews rendered with Pillow in real-time |
| 🤖 **Zero Config** | Auto-creates characters, DB, channels, roles, and assets on first run |

---

## 🚀 Quick Start

<details>
<summary><b>📦 1. Installation (click to expand)</b></summary>

<br/>

**Prerequisites:** Python 3.10+

```bash
# Clone the repo
git clone https://github.com/DXN1-termux/DXN1-RPG.git
cd DXN1-RPG

# Install dependencies
pip install discord.py Pillow
```

> **Termux users:**
> ```bash
> pkg install python
> pip install discord.py Pillow
> ```

</details>

<details>
<summary><b>🤖 2. Discord Bot Setup (click to expand)</b></summary>

<br/>

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → name it whatever you like
3. Go to **Bot** tab → click **Add Bot**
4. Under **Privileged Gateway Intents** enable:
   - ✅ `SERVER MEMBERS INTENT`
   - ✅ `MESSAGE CONTENT INTENT`
5. Copy your **Bot Token**
6. Go to **OAuth2 → URL Generator**, select:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Administrator`
7. Open the generated URL and invite the bot to your server

</details>

<details>
<summary><b>▶️ 3. Run the Bot (click to expand)</b></summary>

<br/>

```bash
python bot_upgraded.py
```

On **first run**, you'll see:

```
============================================================
🤖 DISCORD BOT - FIRST RUN SETUP
============================================================

Paste your Discord bot token below:
(Get it from: https://discord.com/developers/applications)
------------------------------------------------------------
Enter your bot token: 
```

Paste your token → press Enter → **done.** The bot will:
- ✅ Save your token to `.discord_token` (chmod 600)
- ✅ Initialize the SQLite database with all 25+ tables
- ✅ Generate the dark-matter theme asset
- ✅ Set up server channels, roles, and worlds automatically

</details>

<details>
<summary><b>⚙️ 4. First-Time Server Setup (click to expand)</b></summary>

<br/>

Once the bot is in your server and running, type in any channel:

```
setup
```

This creates:
- 🌍 **14 gated World channels** (Meadows → Omega Singularity)
- 🛡️ **ADMIN** (red) and **OWNER** (gold) roles
- 📢 Announcements, Changelog, Guide, Events, and Planning channels
- 🎫 Ticketing channel for guild broadcast requests
- 🛡️ Admin-only staff channel

Then give yourself the **OWNER** role and set your tax config:

```
s!setowner @YourName
s!settax 2.27
```

</details>

---

## ✨ Features

<details>
<summary><b>⚔️ Combat System</b></summary>

<br/>

The combat engine is fully dynamic and persists HP between turns — healing, shields, and big hits all genuinely matter.

| Feature | Details |
|---------|---------|
| **Attack** | `attack` / `fight` / `hunt` — fight zone enemies |
| **Elements** | 10 elements with super-effective ×1.5 / resisted ×0.75 |
| **Class Skills** | Auto-cast when mana fills — unique per class (Arcane Nova, Backstab, Holy Light…) |
| **Boss Fights** | 8 bosses, multi-phase (Awakened → Enraged → Final Form), each hits harder per phase |
| **Dungeon Crawl** | Floor-by-floor crawl with escalating enemies |
| **PvP / Duel** | Challenge other players with optional gold bet |
| **Co-op** | `help @user` joins a guildmate's fight |
| **Ambushes** | Random enemy encounters with Run / Fight / Ping-Guild buttons |
| **Bounties** | Contracts for bonus gold + XP rewards |

**Combat formula:**
```
Damage = rand(ATK×0.75, ATK×1.25) - DEF×0.5
       × element_multiplier
       × crit_multiplier (×1.75 on crit)
```

</details>

<details>
<summary><b>🎲 Loot & Item System</b></summary>

<br/>

Every drop is fully procedurally rolled — no two items are the same.

**8 Rarity Tiers:**

| Tier | Emoji | Base Odds | Stat Multiplier |
|------|-------|-----------|-----------------|
| Common | ⚪ | 61.7% | ×1.00 |
| Uncommon | 🟢 | 25.9% | ×1.18 |
| Rare | 🔵 | 9.25% | ×1.45 |
| Epic | 🟣 | 2.78% | ×1.85 |
| Legendary | 🟠 | 0.56% | ×2.40 |
| Mythic | 🔴 | 0.10% | ×3.20 |
| Secret | 🔐 | 0.015% | ×4.30 |
| Chromatic | 🌈 | 0.002% | ×6.00 |

> **Luck scaling** — your level, crit chance and equipped gear power all push odds toward higher tiers.

**Item rolls include:**
- HP / ATK / DEF / CRIT stats (budget-based, quality-weighted)
- Prefix + Suffix affixes (e.g. *Savage Void-Touched Frozen Rapier of the Fox*)
- Elemental imbue (chance scales with rarity)
- Sockets (up to 3 on high-rarity gear)
- Set membership (Dragonlord / Voidwalker / Celestial)
- Item level + quality stars (★☆☆☆☆ → ★★★★★)

</details>

<details>
<summary><b>🏪 Economy & Trading</b></summary>

<br/>

DXN1-RPG ships **two parallel trading systems**:

**1. Wandering Merchant** (daily rotating stock)
- 10 items refreshed every 24 hours
- Dynamic pricing (±30% hourly fluctuation)
- `shop` / `buy <item>`

**2. Player Marketplace**
- List any item from your inventory: `market sell <item> <price>`
- Browse by category with interactive buttons
- Configurable tax rate (default 2.27%) — set with `s!settax`
- Tax can be routed to a designated owner wallet: `s!setowner @user`
- If no owner is set, tax is a **gold sink** (removed from economy)

**3. Player Shops (v2.1)**
- Create your own persistent vendor stall: `playershop setup`
- Stock it: `playershop stock`
- Shoppers browse via category buttons → dropdown → instant purchase
- Beautiful Pillow-rendered item cards on every transaction

**Economy features:**
- 💰 Gold (primary)
- 💠 Astral Shards (endgame — drops in Shadow Nexus zones)
- ✨ Stardust (from salvaging gear — spend at Gem Exchange)
- Daily rewards, gambling, fortune wheel, loot boxes (6 tiers)

</details>

<details>
<summary><b>👥 Guild System</b></summary>

<br/>

| Feature | Command |
|---------|---------|
| Create guild | `guild create <name>` (costs 💰10,000,000) |
| Join guild | `guild join` (dropdown) or `guild join <name>` |
| Leave / Disband | `guild leave` / `guild disband` |
| Upgrade (×0.1 income/XP per level) | `guild upgrade` |
| Promote / Demote / Kick | `guild promote/demote/kick @user` |
| Guild Treasury | `guild donate <amount>` |
| War declaration | `guild war <name>` |
| Diplomacy Pact | `guild pact <id> <type> <cost> <hours>` |

**Ranks:** Member → Senior → Admin → Leader

**Guild Levels 1–10:** Each level adds +10% gold & XP for all members (max ×2.0 at L10).

**Clan Wars:** Winners steal 10% of the losing guild's treasury.

**Pact types:** Peace / Alliance / Tribute

</details>

<details>
<summary><b>🌍 World System (14 Gated Channels)</b></summary>

<br/>

| World | Level | Prestige | Rebirth |
|-------|-------|----------|---------|
| 🌿 Meadows | 1 | 0 | 0 |
| 🌲 Forest | 5 | 0 | 0 |
| 🕳️ Caves | 15 | 0 | 0 |
| 🏜️ Desert | 30 | 0 | 0 |
| 🌋 Volcano | 50 | 0 | 0 |
| 🌀 The Void | 80 | 1 | 0 |
| ✨ Celestial Plane | 120 | 2 | 0 |
| 🕋 The Abyss | 160 | 3 | 1 |
| ♾️ Eternal Realm | 220 | 5 | 2 |
| 🌑 Shadow Nexus | 300 | 8 | 3 |
| 🗿 Titan Bastion | 450 | 12 | 4 |
| 🌌 Cosmic Expanse | 650 | 18 | 6 |
| 🌟 Genesis Core | 900 | 25 | 8 |
| 🔺 Omega Singularity | 1500 | 40 | 12 |

Each world is a Discord channel — visible to all, but only role-holders can send messages. Roles are granted automatically when requirements are met.

</details>

<details>
<summary><b>🧬 Classes</b></summary>

<br/>

| Class | HP | Mana | ATK | DEF | CRIT | Skill |
|-------|----|------|-----|-----|------|-------|
| ⚔️ Warrior | 120 | 30 | 16 | 12 | 5% | Shield Slam |
| 🔮 Mage | 85 | 75 | 12 | 6 | 8% | Arcane Nova |
| 🗡️ Rogue | 95 | 40 | 14 | 8 | 16% | Backstab |
| 🛡️ Paladin | 110 | 55 | 13 | 14 | 6% | Holy Light |
| 🏹 Ranger | 100 | 35 | 15 | 9 | 12% | Piercing Shot |
| 🌿 Druid | 105 | 65 | 11 | 10 | 7% | Regrowth |
| 🪓 Berserker | 140 | 20 | 20 | 8 | 10% | Bloodrage |
| 🐴 Knight | 150 | 30 | 14 | 18 | 4% | Bulwark |
| 🥷 Assassin | 90 | 45 | 17 | 7 | 22% | Death Mark |
| 💀 Necromancer | 95 | 90 | 15 | 7 | 9% | Soul Drain |
| 🧘 Monk | 115 | 60 | 14 | 12 | 13% | Chi Burst |
| 🌀 Voidreaper 🔐 | 160 | 80 | 24 | 14 | 20% | Void Collapse |
| 👼 Celestial 🔐 | 175 | 110 | 22 | 18 | 15% | Judgment |

> 🔐 **Secret classes** require Astral Shards at the Astral Exchange (`astralshop`).

</details>

---

## 📜 Commands

<details>
<summary><b>🧍 Character Commands</b></summary>

<br/>

| Command | Description |
|---------|-------------|
| `start [class]` | Create your character |
| `status` / `me` | View full stats, level, gold, shards & XP bar |
| `class` / `class [name]` | List classes or switch class |
| `inventory` / `bag` | See items + equipped gear |
| `equip [item]` | Equip a weapon/armor/accessory |
| `rebirth` | Hard reset for permanent power boost |
| `prestige` | Soft reset (level 50+) for permanent stat bonus |
| `config` / `settings` | Private profile config (titles, tradeable, pings) |

</details>

<details>
<summary><b>⚔️ Combat Commands</b></summary>

<br/>

| Command | Description |
|---------|-------------|
| `attack` / `fight` / `hunt` | Start or continue a battle |
| `heal` / `potion` | Use a potion to restore HP |
| `boss` | Challenge a powerful boss |
| `dungeon` | Crawl dungeon floors |
| `pvp` / `duel [bet]` | Battle another player |
| `help @user` | Join a guildmate's fight (co-op) |
| `bounty` | Take a bounty contract for rewards |
| `zone [name]` | Travel to a different zone |

</details>

<details>
<summary><b>💰 Economy Commands</b></summary>

<br/>

| Command | Description |
|---------|-------------|
| `shop` / `buy [item]` | Wandering merchant (daily rotating stock) |
| `sell` | Sell items via dropdown menu |
| `market` | Browse player marketplace |
| `market sell [item] [price]` | List an item on the marketplace |
| `playershop` | Browse all player shops |
| `playershop setup` | Create your own shop |
| `playershop stock` | Add items to your shop |
| `astralshop` | Spend 💠 Astral Shards |
| `daily` | Claim daily reward |
| `gamble [amount]` | 3-reel slot machine |
| `spin` | Free daily fortune wheel |
| `lootbox` | Open loot boxes (6 tiers) |
| `trade @user` | Open a private trade room |

</details>

<details>
<summary><b>🔮 Gear & Crafting Commands</b></summary>

<br/>

| Command | Description |
|---------|-------------|
| `enchant [item]` | Enchant gear (✦1→✦20, escalating cost & risk) |
| `reforge [item]` | Reroll an item's stats for gold |
| `salvage [item]` | Destroy item → gold + ✨ Stardust |
| `inspect [item]` | Full item card with all stats |
| `compare [item]` | Side-by-side stat delta vs equipped gear |
| `gem` | Browse gem exchange |
| `gem buy [gem]` | Buy a gem with Stardust |
| `socket [item] \| [gem]` | Infuse a gem into gear permanently |
| `craft` | Craft items from materials |
| `alchemy` | Brew potions |
| `fish` | Fish for resources |
| `mine` | Mine for materials |
| `merge [enchant] [tier]` | Fuse 2×T(n) → 1×T(n+1) (max T7) |
| `apply [enchant] [tier]` | Apply custom enchant to your armor |
| `odds` | Show your live luck-adjusted drop odds |

</details>

<details>
<summary><b>👥 Guild & Social Commands</b></summary>

<br/>

| Command | Description |
|---------|-------------|
| `guild` | View your guild info |
| `guild create [name]` | Found a guild (💰10M, 1 per person) |
| `guild join [name]` | Join a guild |
| `guild leave` / `guild disband` | Leave or disband |
| `guild upgrade` | Upgrade guild (+0.1× income per level) |
| `guild promote/demote/kick @user` | Manage members |
| `guild donate [amount]` | Donate to guild treasury |
| `guild war [name]` | Declare war on another guild |
| `guild pact` | Propose a diplomacy pact |
| `team` / `lobby` | Group up with others |
| `private` | Create a quiet personal channel |
| `leaderboard` | Top players by level |
| `g.m` / `g.m @user` | Message activity stats |
| `worlds` | View world unlock requirements |
| `quest` | Take a quest |
| `pet` | Browse & adopt combat pets |

</details>

---

## 🛡️ Staff Tools

<details>
<summary><b>⚙️ Staff Commands (ADMIN + OWNER)</b></summary>

<br/>

All staff commands use the `s!` prefix and require the **ADMIN** or **OWNER** role.

| Command | Description |
|---------|-------------|
| `s!warn @user [reason]` | Issue a warning |
| `s!unwarn @user` | Remove last warning |
| `s!warnings @user` | List all warnings |
| `s!kick @user [reason]` | Kick from server |
| `s!ban @user [reason]` | Ban from server |
| `s!unban <id>` | Unban by user ID |
| `s!mute @user [minutes]` | Mute for N minutes |
| `s!unmute @user` | Remove mute |
| `s!cleanup [full\|worlds\|general]` | Purge channels/roles |
| `s!give <item> [amount] [@user]` | Give items to players |

</details>

<details>
<summary><b>👑 Owner-Only Commands</b></summary>

<br/>

These require the **OWNER** role (gold colored).

| Command | Description |
|---------|-------------|
| `s!settax <percent>` | Set the marketplace tax rate (0–25%) |
| `s!setowner @user` | Set who receives the marketplace tax |
| `event` *(in #🎉-events)* | Launch a server-wide event |
| `planning` *(in #🗓️-planning)* | Schedule a future event |
| `world setup` | Recreate all world channels & roles |

**Example:**
```
s!settax 2.5        → Sets marketplace tax to 2.5%
s!setowner @DXN1   → Routes all tax gold to @DXN1
s!settax 0          → Tax becomes a pure gold sink
```

> Tax config is saved to `bot_config.json` and applies **instantly** without restart.

</details>

<details>
<summary><b>🎉 Event System</b></summary>

<br/>

Staff can launch or schedule server-wide multiplier events from the dedicated channels.

**Available event types:**

| Key | Name | Effect |
|-----|------|--------|
| `luck2` / `luck3` | Luck Boost | ×2 or ×3 drop luck |
| `xp2` / `xp3` / `xp5` | XP Boost | ×2, ×3, or ×5 XP |
| `gold2` / `gold3` | Gold Boost | ×2 or ×3 gold |
| `drops2` / `drops3` | Drop Boost | ×2 or ×3 loot |
| `double` / `triple` | Everything | ×2 or ×3 all |
| `weekend` | Weekend Madness | ×2 XP + Gold |

Events auto-start and auto-expire. Scheduled events fire even if the bot was offline when they were due.

</details>

---

## 🏗️ Architecture

<details>
<summary><b>📂 File Structure</b></summary>

<br/>

```
DXN1-RPG/
├── bot_upgraded.py     # Main bot — 9,800+ lines, all-in-one
├── rpg.db              # SQLite database (auto-created)
├── bot_config.json     # Runtime config (auto-created)
├── .discord_token      # Saved token (auto-created, chmod 600)
├── darkmatter.png      # Dark-matter embed banner (auto-generated)
└── README.md           # This file
```

</details>

<details>
<summary><b>🗄️ Database Schema (25+ Tables)</b></summary>

<br/>

```
players              — Core player stats, level, gold, shards
inventory            — Items with HP/ATK/DEF/enchant columns
equipment            — Equipped weapon/armor/accessory per player
fights               — Active combat state
guilds               — Guild metadata + treasury
guild_members        — Membership + ranks
guild_pacts          — Diplomacy pacts
clan_wars            — Active wars + scores
clan_war_participants — Per-player war damage tracking
market_listings      — Player marketplace listings
player_shops         — Player shop metadata
shop_inventory       — Player shop items
pets                 — Owned pets
dungeons             — Dungeon floor progress
boss_defeats         — Boss kill tracking
quests               — Active + completed quests
achievements         — Unlocked achievements
seasons              — Season definitions
season_progress      — Per-player season tiers
pvp_battles          — PvP history
crafting             — Recipe completion counts
trades               — Active trade sessions
advanced_trading     — Multi-item escrow trades
trade_ratings        — Post-trade reputation scores
server_events        — Scheduled/active events
msg_stats            — Message activity per day
log                  — Action audit log
warnings             — Moderation warnings
leaderboards         — Guild-scoped stat rankings
teams / lobbies      — Group play sessions
economy_log          — Transaction history
```

> All tables use `WAL` mode + `NORMAL` sync for maximum performance with zero data loss risk.

</details>

<details>
<summary><b>🎨 The V Class (Visual + RNG Engine)</b></summary>

<br/>

All item rolling, rarity math, visual rendering, and combat resolution lives in the `V` namespace:

```python
V.roll_rarity(luck)           # Luck-scaled rarity picker
V.roll_item(name, type, ...)  # Multi-stat item roller
V.roll_drop(pool, level, ...) # Full drop from the catalog
V.item_card(item)             # Full ASCII item card
V.drop_reveal_frames(item)    # Animated reveal frames
V.damage_calc(atk, crit, ...) # Elemental damage formula
V.cast_skill(class, atk, ...) # Class skill resolver
V.boss_phase(hp, max_hp)      # Multi-phase boss logic
V.set_bonus(set_counts)       # Item set bonus calculator
V.gem_stats(gems)             # Gem socket stat calculator
V.odds_table(luck)            # Human-readable odds display
V.xp_bar / V.hp_color_bar     # Fancy Unicode progress bars
```

</details>

<details>
<summary><b>⚡ Performance Notes</b></summary>

<br/>

- **Autosave loop** — dirty player/fight IDs batched and flushed every **5 seconds**
- **WAL checkpoint** — runs every 60 seconds to keep the DB file compact
- **Drop pool cached** — `_build_drop_pool()` builds once and caches forever
- **Fuzzy correction disabled** — exact command matching for zero false-triggers
- **Image generation** — Pillow renders are on-demand and streamed directly; no disk cache needed
- **DB lock** — `asyncio.Lock()` guards all write batches from the autosave loop

</details>

---

## 🤝 Contributing

<details>
<summary><b>🐛 Bug Reports & Feature Requests</b></summary>

<br/>

1. Check [existing issues](https://github.com/DXN1-termux/DXN1-RPG/issues) first
2. Open a new issue with:
   - Clear description of the bug or feature
   - Steps to reproduce (for bugs)
   - Any relevant error output

</details>

<details>
<summary><b>🔧 Pull Requests</b></summary>

<br/>

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push and open a PR

**Please keep PRs focused** — one feature or fix per PR makes review much easier.

</details>

---

## 📄 License

This project is licensed under the **MIT License** — see [`LICENSE`](LICENSE) for details.

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:00E5FF,50:7E57C2,100:0B0B14&height=120&section=footer&animation=fadeIn" width="100%"/>

**Made with 🌌 by [DXN1-termux](https://github.com/DXN1-termux)**

[![GitHub](https://img.shields.io/badge/GitHub-DXN1--termux-181717?style=for-the-badge&logo=github)](https://github.com/DXN1-termux)

*Star ⭐ the repo if this bot runs on your server!*

</div>
