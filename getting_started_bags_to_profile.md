# Getting Started — Bag to Profile

Scan a coffee bag photo and automatically generate 4 brew profiles on your Fellow Aiden.

---

## Prerequisites

- Python 3.11+
- A Fellow Aiden brewer with an active account
- An OpenAI API key with access to **gpt-4o** and **o3-mini**
- (Optional) A Dropbox account for the phone-to-machine workflow

---

## 1. Clone & Install

```bash
git clone https://github.com/lgilnadolskis/fellow-aiden.git
cd fellow-aiden
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install openai dropbox
```

---

## 2. Environment Variables

Create a `.env` file or export these in your shell:

```bash
# Required — Fellow Aiden credentials
export FELLOW_EMAIL="your-fellow-email@example.com"
export FELLOW_PASSWORD="your-fellow-password"

# Required — OpenAI
export OPENAI_API_KEY="sk-..."

# Optional — Dropbox integration (only for --dropbox mode)
export DROPBOX_APP_KEY="your-dropbox-app-key"
export DROPBOX_FOLDER="/coffee_database"   # default, can be changed
```

> **Tip:** Add these to your `~/.bashrc` or `~/.zshrc` so they persist across sessions.

---

## 3. Dropbox Setup (one-time)

This is only needed if you want the phone → Dropbox → Aiden workflow.

### 3a. Create a Dropbox App

1. Go to [https://www.dropbox.com/developers/apps](https://www.dropbox.com/developers/apps)
2. Click **Create app**
3. Choose **Scoped access** → **Full Dropbox**
4. Name it (e.g., `bag_to_aiden`)
5. Copy the **App key** from the **Settings** tab
6. Set it: `export DROPBOX_APP_KEY="your-app-key"`

### 3b. Create the Dropbox folder

On your Dropbox account (phone or web), create a folder called `coffee_database`.

### 3c. Authorize (first run only)

The first time you run `--dropbox`, the script will print a URL. Open it in your browser, click **Allow**, and paste the authorization code back into the terminal. The refresh token is cached at `~/.bag_to_profile_dropbox_token.json` so you won't need to do this again.

---

## 4. Usage

### Process a single photo

```bash
python bag_to_profile.py photo.jpg
```

### Watch a local folder

If you have Dropbox Desktop or Google Drive syncing to your machine:

```bash
python bag_to_profile.py --watch ~/Dropbox/coffee_database/
```

### Watch via Dropbox API (no desktop client needed)

```bash
python bag_to_profile.py --dropbox
```

The script polls every 15 seconds. Drop a photo into your Dropbox `coffee_database/` folder from your phone and it will be processed automatically.

---

## 5. What It Does

1. **Reads the coffee bag** — GPT-4o vision extracts roaster, origin, process, tasting notes, etc.
2. **Checks for Fellow Drops** — If it's a Fellow Drops coffee and a matching profile already exists on your Aiden, it skips generation and tells you which profile to use.
3. **Generates 4 profiles** (if not a Drops coffee):
   - **Balanced** — equal emphasis on all tasting notes
   - **Bright & Acidic** — highlights fruity and floral notes
   - **Full Body** — maximizes sweetness and mouthfeel
   - **Experimental** — unconventional brewing approach
4. **Saves all profiles** directly to your Aiden.
5. **Moves processed photos** to `coffee_database/processed/` (Dropbox mode) or renames them with `.done` (local watch mode).

---

## 6. File Structure

| File | Purpose |
|------|---------|
| `bag_to_profile.py` | Main script — image analysis, recipe generation, Aiden sync |
| `list_profiles_schedules.py` | List all profiles and schedules, export to CSV |
| `~/.bag_to_profile_dropbox_token.json` | Cached Dropbox refresh token (auto-generated) |

---

## 7. Troubleshooting

| Problem | Solution |
|---------|----------|
| `Missing OPENAI_API_KEY` | Export the env var or add it to your shell profile |
| `Email or password incorrect` | Check `FELLOW_EMAIL` and `FELLOW_PASSWORD` |
| `Dropbox SDK not installed` | Run `pip install dropbox` |
| `Missing DROPBOX_APP_KEY` | Copy the App key from your Dropbox developer console |
| `Cached Dropbox token invalid` | Delete `~/.bag_to_profile_dropbox_token.json` and re-run to re-authorize |
| Fellow debug logs are noisy | The `fellow_aiden` library logs at DEBUG level by default — this is normal |

---

## 8. Quick Reference

```bash
# One-liner setup after cloning
source .venv/bin/activate && pip install -e . && pip install openai dropbox

# Scan a bag
python bag_to_profile.py photo.jpg

# Watch Dropbox
python bag_to_profile.py --dropbox

# List all profiles & schedules on your Aiden
python list_profiles_schedules.py
```
