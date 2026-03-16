# Mewgenics Storage QOL

A **PySide6 desktop app** for managing your [Mewgenics](https://store.steampowered.com/app/2059360/Mewgenics/) inventories without launching the game.  
It reads and writes the Steam save file directly (`.sav` = SQLite database).

---

## Requirements

- Python 3.13+
- PySide6

```bash
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

The app auto-detects your save file from:
```
%APPDATA%\Glaiel Games\Mewgenics\<SteamID>\saves\steamcampaign01.sav
```

---

## Features

### 🗂️ Inventory Viewer

- Displays **Storage** and **Trash** inventories as a 7-column icon grid
- Item icons rendered from the game's SVG assets, background tinted by rarity
- Click an item to see its **detail panel** (name, rarity, category, charges, description)
- **Sorting** options: Default (save order) · Name · Rarity · Category
  - Category view groups items under labelled headers with row breaks between groups

### 🔄 Save File Handling

- **Reload** button re-reads the save file at any time — shows the save's last-modified date/time
- **Polling timer** (every 3 s) highlights the Reload button in orange with `⚠ New save!` when the file has been modified externally (by the game or a file replacement)
- **Write protection**: before any operation that modifies the save, the app checks whether the file has changed since the last load. If so, a confirmation dialog shows the file's current date and warns about overwriting

### 💀 Sacrifice System

| Action | Where | Description |
|---|---|---|
| **Sacrifice item** | Storage / Trash | Removes the item and earns 1 token of its rarity |
| **Sacrifice Selected** | Storage (multi-select) | Sacrifice all Ctrl-selected items at once — confirmation shows a per-rarity token summary |
| **Sacrifice All → Tokens** | Trash | Sacrifice every non-broken item in Trash — confirmation shows total gains |

All sacrifice actions show a confirmation dialog with the exact tokens you will earn.

### 🟢 Multi-Selection (Storage)

- **Ctrl+Click** toggles an item in/out of the multi-selection (bright green border)
- A green action bar appears above the grid showing the count of selected items
- Actions available: **✦ Sacrifice** (with gains summary) · **🗑 Trash** · **✕ Clear**
- Regular click exits multi-select mode and returns to single-select

### 🪙 Token Economy

Four token rarities: **Common · Uncommon · Rare · Very Rare**  
Tokens are displayed in the status bar with their respective icons.

- Tokens are **linked to the save file's timestamp** — if you load an older save, the app restores the token state that was current at that point in time
- Token history is stored in `custom/tokens_bank.json` alongside your save

### 🔧 Broken Items

Broken items (identified by `sep_flag = 5` in the trash) receive special treatment:

- Displayed with a **dark overlay + red ✗** (icon still visible underneath)
- Cannot be sacrificed or moved to Storage
- **Repair** button available in Trash: costs **3 tokens** of the item's rarity, resets the broken flag, and moves the item to Storage — confirmation shows the cost

### 📦 Item Pool

- All items ever seen in Storage or Trash are automatically added to a persistent **Pool** (stored in `custom/items_pool.json`)
- Pool tab shows discovered items normally, then **all undiscovered catalog items** below a separator with a darkened locked overlay
- Undiscovered items use **virtual scrolling** — only visible rows are rendered, making large lists fast

### 🏪 Token Shop

Accessible from the status bar button. Spend tokens to receive random items from your pool.

| Rarity | Cost | Pool required | Upgrade chance |
|---|---|---|---|
| Common | 3 tokens | 20 discovered | 1 % → Uncommon |
| Uncommon | 3 tokens | 20 discovered | 1 % → Rare |
| Rare | 3 tokens | 20 discovered | — |
| Very Rare | 3 tokens | **10 discovered** | — |

- Preview the item you receive before accepting
- **3 rerolls** available per purchase
- Confirmation dialog before spending tokens
- Warning if the save file changed while the shop was open

### 💰 Gold

Current gold is displayed in the status bar with a coin icon.

---

## Data Storage

| File | Purpose |
|---|---|
| `custom/tokens_bank.json` | Token counts with per-save-mtime history |
| `custom/items_pool.json` | All ever-discovered item definitions |

---

## Architecture Notes

- `.sav` files are **SQLite databases**; inventory blobs are binary (little-endian, custom format)
- All parsing/writing is in `parse/` and `utils/` — no external dependencies beyond PySide6
- `ItemCatalog` singleton (`catalogs/itemcatalog.py`) enriches raw items with name, icon, rarity, and category from `data/items/`
