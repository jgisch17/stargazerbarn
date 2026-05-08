# Stargazer BSR Daily Automation — Overview

**What it does:** Every morning at 6:30am local time, the Mac automatically scrapes Amazon's Best Sellers Rank for Fresh Cut Flowers and updates the Stargazer dashboard.

---

## How It's Triggered

| Component | Details |
|-----------|---------|
| **Scheduler** | `cron` (macOS system cron) |
| **Cron entry** | `30 6 * * * /bin/bash "/Volumes/GISCH SSD/CLAUDE/Stargazer/run_bsr.sh"` |
| **Schedule** | 6:30am local time daily |
| **Note** | The Mac must be awake at 6:30am — cron does NOT run on wake if missed |

> **Migration note:** Previously triggered by `launchd` via `~/Library/LaunchAgents/com.stargazer.bsr-update.plist`. That plist still exists on disk but is no longer the active scheduler — cron is now in charge.

---

## The 3-Step Pipeline

```
cron (6:30am)
    └── run_bsr.sh
            ├── 1. scrape_bsr.py   → scrapes Amazon → outputs JSON ranks
            └── 2. bsr_updater.py  → reads JSON → writes to dashboard_data.js
                                                  (powers index.html dashboard)
```

---

## Files Involved

| File | Location | Role |
|------|----------|------|
| `run_bsr.sh` | `Stargazer/` | Shell wrapper — runs both Python scripts, handles errors |
| `scrape_bsr.py` | `Stargazer/` | Scrapes Amazon BSR top 30 using headless browser |
| `bsr_updater.py` | `Stargazer/` | Injects today's ranks into `dashboard_data.js` |
| `dashboard_data.js` | `Stargazer/` | Live data store — updated daily by the automation |
| `index.html` | `Stargazer/` | Dashboard — reads `dashboard_data.js` to display rankings |
| `logs/bsr_YYYY-MM-DD.log` | `Stargazer/logs/` | Daily log file per run |
| `com.stargazer.bsr-update.plist` | `~/Library/LaunchAgents/` | Legacy launchd config (inactive — cron is now used) |

---

## Python Tools / Libraries Used

| Library | Purpose |
|---------|---------|
| `playwright` (Python) | Headless Chromium browser — loads Amazon page like a real browser |
| `playwright_stealth` | Applies stealth patches to avoid Amazon bot detection |
| `json`, `re`, `datetime` | Standard library — parse/write data, update JS file |
| **Chromium** (bundled) | Browser engine installed via `playwright install chromium` |

Python binary used: `/usr/bin/python3` (system Python 3.9)
Playwright binary: `~/Library/Python/3.9/bin/playwright`

---

## What Gets Tracked

- **All Stargazer Barn ASINs** — tracked at whatever rank they appear, regardless of whether they're in the top 30. If a Stargazer ASIN is in ASIN_TO_PRODUCT it is always captured.
- **All top-30 competitor items** — any ASIN appearing at rank ≤ 30 that is not a known Stargazer product gets a product name auto-derived from its Amazon listing title and is tracked going forward.
- **New products auto-added** — `bsr_updater.py` automatically adds any product that appears in today's scraped data but doesn't yet exist in `bsr_data.rankings`, padding historical ranks with null.
- Ranks are pulled from: `amazon.com/Best-Sellers-Fresh-Cut-Flowers/zgbs/grocery/12902901`
- If a product has two ASINs (rotating), the better (lower) rank is kept

---

## Data Flow Detail

1. `scrape_bsr.py` launches a headless Chrome window, navigates to the Amazon BSR page, scrolls to trigger lazy-load, then extracts rank + ASIN pairs via JavaScript DOM query
2. ASINs are mapped to friendly product names (defined inside `scrape_bsr.py`)
3. The resulting `{"ProductName": rank}` JSON is passed as a CLI argument to `bsr_updater.py`
4. `bsr_updater.py` reads `dashboard_data.js`, appends today's date and ranks, and writes the file back
5. `index.html` loads `dashboard_data.js` as a script tag — no server needed, works as a local file

---

## How to Check If It Ran

```bash
# View today's log
cat "/Volumes/GISCH SSD/CLAUDE/Stargazer/logs/bsr_$(date +%Y-%m-%d).log"

# Check cron job is registered
crontab -l | grep stargazer
```

---

## How to Re-Run Manually

```bash
bash "/Volumes/GISCH SSD/CLAUDE/Stargazer/run_bsr.sh"
```

---

## How to Edit the Cron Schedule

```bash
crontab -e
# Current entry: 30 6 * * * /bin/bash "/Volumes/GISCH SSD/CLAUDE/Stargazer/run_bsr.sh"
# Format: minute hour * * * command
```

---

## Programs & Tools — Plain English Summary

| Tool | Type | What It Is |
|------|------|------------|
| **cron** | macOS Scheduler | Unix job scheduler — fires the script at 6:30am daily based on the crontab entry. |
| **bash** | Shell | Runs `run_bsr.sh` — the wrapper that calls both Python scripts in order and handles errors. |
| **Python 3** | Language | The main programming language. System Python 3.9 at `/usr/bin/python3`. |
| **Playwright** | Python Library | Controls a real browser from Python code — opens pages, scrolls, reads content. |
| **playwright-stealth** | Python Library | Patches Playwright so Amazon doesn't detect it as a bot. |
| **Chromium** | Browser Engine | Headless (invisible) browser installed via `playwright install chromium`. This is what actually loads the Amazon page. |

**In plain English:** cron wakes up bash at 6:30am → bash runs Python → Python drives Chromium (via Playwright + stealth) to load the Amazon BSR page → ranks are extracted → written back into the dashboard JS file.

---

*Documented 2026-04-17 | Updated 2026-04-19 — migrated scheduler from launchd to cron*
