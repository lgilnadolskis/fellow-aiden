#!/usr/bin/env python3
"""
Coffee Bag Scanner — Photograph a coffee bag, generate 4 brew profiles, and save them to your Fellow Aiden.

Modes:
  1. Single image:    python bag_to_profile.py photo.jpg
  2. Folder watcher:  python bag_to_profile.py --watch /path/to/folder
  3. Dropbox watcher: python bag_to_profile.py --dropbox

The watched folder can be a Dropbox or Google Drive synced folder so you can
snap a photo on your phone and have it processed automatically.

Required env vars:
  OPENAI_API_KEY    — OpenAI API key (needs gpt-4o and o3-mini access)
  FELLOW_EMAIL      — Fellow account email
  FELLOW_PASSWORD   — Fellow account password

For --dropbox mode:
  DROPBOX_APP_KEY       — Dropbox app key (from App Console > Settings)
  DROPBOX_FOLDER        — Dropbox folder path (default: /coffee_database)
"""

import argparse
import base64
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from openai import OpenAI
from fellow_aiden import FellowAiden
from fellow_aiden.profile import CoffeeProfile

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bag_to_profile")

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

IMAGE_ANALYSIS_PROMPT = """\
You are a specialty coffee expert. Analyze this photo of a coffee bag and extract
every detail you can see. Return a JSON object (no markdown fences) with:
{
  "roaster": "...",
  "coffee_name": "...",
  "origin": "...",
  "region": "...",
  "process": "...",
  "roast_level": "...",
  "tasting_notes": "...",
  "variety": "...",
  "elevation": "...",
  "additional_info": "...",
  "is_fellow_drops": true or false
}
If a field is not visible, set it to null. Be thorough — read all text on the bag.

For "is_fellow_drops": set to true if this coffee is from Fellow's "Drops" program
(formerly Fellow Drops, Fellow Products coffee subscription). Look for Fellow
branding, the word "Drops", Fellow's logo, or any indication this is a Fellow
curated/subscription coffee. If you are unsure, set to false.
"""

RECIPE_SYSTEM = """\
Assume the role of a master coffee brewer. You focus exclusively on the pour over method and specialty coffee only. You often work with single origin coffees, but you also experiment with blends. Your recipes are executed by a robot, not a human, so maximum precision can be achieved. Temperatures are all maintained and stable in all steps. Always lead with the recipe, and only include explanations below that text, NOT inline. Below are the components of a recipe. 

Core brew settings: These settings are static and must match for single and batch brew.
Title: An interesting and creative name based on the coffee details. 
Ratio: How much coffee per water. Values MUST be between 14 and 20 with 0.5 step increments.
Bloom ratio: Water to use in bloom stage. Values MUST be between 1 and 3 with 0.5 step increments.
Bloom time: How long the bloom phase should last. Values MUST be between 1 and 120 seconds.
Bloom temperature: Temperature of the water. Values MUST be between 50 and 99 celsius.

Pulse settings: These are independent and can vary for single and batch brews. 
Number of pulses: Steps in which water is poured over coffee. Values MUST be between 1 and 10.
Time between pulses: Time in between each pulse. Values MUST be between 5 and 60 seconds. This MUST be included even if a single pulse is performed. 
Pulse temperate. Independent temperature to use for a given pulse.  Values MUST be between 50 and 99 celsius.
"""

REFORMAT_SYSTEM = """\
Assume the role of a data engineer. You need to parse coffee recipes and their explanations so the data can be structured. Below are the important components of the recipe.

Core brew settings: These settings are static and must match for single and batch brew.
Title: An interesting and creative name based on the coffee details. 
Ratio: How much coffee per water. Values range from 1:14 to 1:20 with 0.5 steps.
Bloom ratio: Water to use in bloom stage. Values range from 1 to 3 with 0.5 steps.
Bloom time: How long the bloom phase should last. Values range from 1 to 120 seconds.
Bloom temperature: Temperature of the water. Values range from 50 celsius to 99 celsius.

Pulse settings: These are independent and can vary for single and batch brews. 
Number of pulses: Steps in which water is poured over coffee. Values range from 1 to 10.
Time between pulses: Time in between each pulse. Values range from 5 to 60 seconds. This must be included even if a single pulse is performed. 
Pulse temperate. Independent temperature to use for a given pulse.  Values range from 50 celsius to 99 celsius. 
"""

PROFILE_STYLES = [
    {
        "label": "Balanced",
        "guidance": (
            "Create a well-balanced recipe for this coffee that brings out the "
            "best of all listed tasting notes equally. Use moderate temperatures "
            "and a standard bloom. Provide your explanations below the recipe."
        ),
    },
    {
        "label": "Bright & Acidic",
        "guidance": (
            "Create a recipe optimized for brightness and acidity — highlight "
            "fruity and floral notes. Use higher temperatures and a shorter bloom "
            "to extract more acidity. Provide your explanations below the recipe."
        ),
    },
    {
        "label": "Full Body",
        "guidance": (
            "Create a recipe that maximizes body and sweetness. Use a longer bloom, "
            "lower pulse temperatures, and a tighter ratio to produce a heavier, "
            "more syrupy cup. Provide your explanations below the recipe."
        ),
    },
    {
        "label": "Experimental",
        "guidance": (
            "Create a creative and unconventional recipe that pushes boundaries — "
            "try unusual pulse patterns, temperature ramps, or bloom strategies "
            "to discover new flavors. Provide your explanations below the recipe."
        ),
    },
]

# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def encode_image_to_base64(path: str) -> str:
    """Read an image file and return a base64 encoded string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_media_type(path: str) -> str:
    """Infer MIME type from extension."""
    ext = Path(path).suffix.lower()
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }
    return mapping.get(ext, "image/jpeg")


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def analyze_image(client: OpenAI, image_path: str) -> dict:
    """Use GPT-4o vision to extract coffee details from a bag photo."""
    log.info("Analyzing image: %s", image_path)
    b64 = encode_image_to_base64(image_path)
    media_type = get_image_media_type(image_path)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": IMAGE_ANALYSIS_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{b64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        max_tokens=1000,
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown fences if model included them
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    coffee_info = json.loads(raw)
    log.info("Detected coffee: %s — %s", coffee_info.get("roaster"), coffee_info.get("coffee_name"))
    return coffee_info


def find_drops_profile(aiden: FellowAiden, coffee_info: dict) -> dict | None:
    """Search existing profiles on the machine for a Fellow Drops match.

    Checks by coffee name, then by roaster name (fuzzy), since Drops profiles
    are typically named after the coffee or roaster.
    """
    candidates = [
        coffee_info.get("coffee_name"),
        coffee_info.get("roaster"),
    ]
    for name in candidates:
        if not name:
            continue
        match = aiden.get_profile_by_title(name, fuzzy=True)
        if match:
            return match
    # Also try a substring search through all profile titles
    profiles = aiden.get_profiles()
    coffee_name = (coffee_info.get("coffee_name") or "").lower()
    roaster = (coffee_info.get("roaster") or "").lower()
    for profile in profiles:
        title = profile.get("title", "").lower()
        if coffee_name and coffee_name in title:
            return profile
        if roaster and roaster in title:
            return profile
    return None


def build_coffee_description(info: dict) -> str:
    """Build a rich text description from the extracted coffee info."""
    parts = []
    if info.get("coffee_name"):
        parts.append(f"Coffee: {info['coffee_name']}")
    if info.get("roaster"):
        parts.append(f"Roaster: {info['roaster']}")
    if info.get("origin"):
        parts.append(f"Origin: {info['origin']}")
    if info.get("region"):
        parts.append(f"Region: {info['region']}")
    if info.get("process"):
        parts.append(f"Process: {info['process']}")
    if info.get("roast_level"):
        parts.append(f"Roast: {info['roast_level']}")
    if info.get("tasting_notes"):
        parts.append(f"Tasting notes: {info['tasting_notes']}")
    if info.get("variety"):
        parts.append(f"Variety: {info['variety']}")
    if info.get("elevation"):
        parts.append(f"Elevation: {info['elevation']}")
    if info.get("additional_info"):
        parts.append(f"Additional: {info['additional_info']}")
    return "\n".join(parts)


def generate_recipe(client: OpenAI, coffee_description: str, style: dict) -> str:
    """Generate a recipe for the given coffee and style using o3-mini."""
    log.info("  Generating '%s' recipe...", style["label"])
    prompt = f"{style['guidance']}\n\n{coffee_description}"
    completion = client.chat.completions.create(
        model="o3-mini",
        messages=[
            {"role": "user", "content": RECIPE_SYSTEM + prompt},
        ],
    )
    return completion.choices[0].message.content


def extract_profile(client: OpenAI, recipe_text: str) -> CoffeeProfile | None:
    """Parse a recipe text into a validated CoffeeProfile using GPT-4o structured output."""
    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": REFORMAT_SYSTEM},
                {"role": "user", "content": recipe_text},
            ],
            response_format=CoffeeProfile,
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        log.error("Failed to extract profile: %s", e)
        return None


def process_image(client: OpenAI, aiden: FellowAiden, image_path: str) -> list[dict]:
    """Full pipeline: image → coffee info → 4 recipes → save to machine."""
    print("\n" + "=" * 70)
    print(f"  Processing: {image_path}")
    print("=" * 70)

    # Step 1 — Read the bag
    coffee_info = analyze_image(client, image_path)
    description = build_coffee_description(coffee_info)

    print(f"\n  Coffee detected:")
    for line in description.split("\n"):
        print(f"    {line}")

    is_drops = coffee_info.get("is_fellow_drops", False)

    # Step 1.5 — If this is a Fellow Drops coffee, look for an existing profile
    if is_drops:
        print(f"\nFellow Drops coffee detected. Checking for existing profile...")
        existing = find_drops_profile(aiden, coffee_info)
        if existing:
            print(f"Found existing Drops profile on your Aiden:")
            print(f"  Title: {existing.get('title')}")
            print(f"  ID: {existing.get('id')}")
            print(f"  Ratio: 1:{existing.get('ratio')}")
            bloom = "Enabled" if existing.get("bloomEnabled") else "Disabled"
            print(f"  Bloom: {bloom}")
            if existing.get("bloomEnabled"):
                print(f"  Bloom duration: {existing.get('bloomDuration')} seconds")
                print(f"  Bloom temperature: {existing.get('bloomTemperature')} degrees C")
            print(f"\nNo new profiles generated. Using the Drops profile.")
            return [{"style": "Fellow Drops", "profile_id": existing.get("id"), "title": existing.get("title"), "recipe_text": "(existing)"}]
        else:
            print(f"Warning: Fellow Drops coffee detected but no matching profile found on your Aiden.")
            print(f"The Drops profile may not have been synced yet.")
            print(f"Generating custom profiles instead.\n")

    # Step 2 — Generate 4 profiles
    saved_profiles = []
    for style in PROFILE_STYLES:
        print(f"\nStyle: {style['label']}")

        # Generate recipe text
        recipe_text = generate_recipe(client, description, style)
        print(f"Recipe generated.")

        # Parse into structured profile
        profile = extract_profile(client, recipe_text)
        if not profile:
            print(f"Failed to parse recipe. Skipping.")
            continue

        profile_data = profile.model_dump()
        profile_data["profileType"] = 0
        print(f"Title: {profile_data['title']}")
        print(f"Ratio: 1:{profile_data['ratio']}")

        # Step 3: Save to machine
        try:
            created = aiden.create_profile(profile_data)
            print(f"Saved to Aiden. ID: {created.get('id', 'unknown')}")
            saved_profiles.append({
                "style": style["label"],
                "profile_id": created.get("id"),
                "title": profile_data["title"],
                "recipe_text": recipe_text,
            })
        except Exception as e:
            log.error("Failed to save: %s", e)

    # Summary
    print(f"\nSummary: {len(saved_profiles)} of {len(PROFILE_STYLES)} profiles saved to Aiden.")
    for sp in saved_profiles:
        print(f"  {sp['style']}: {sp['title']}, ID {sp['profile_id']}")

    return saved_profiles


# ---------------------------------------------------------------------------
# Folder watcher (for Dropbox / Google Drive sync folders)
# ---------------------------------------------------------------------------

def watch_folder(client: OpenAI, aiden: FellowAiden, folder: str, poll_interval: float = 5.0):
    """
    Poll a folder for new image files. When a new image appears, process it
    and rename it with a .done suffix so it isn't processed again.

    This works with any synced folder (Dropbox, Google Drive, iCloud, etc).
    """
    folder = Path(folder)
    if not folder.is_dir():
        log.error("Watch folder does not exist: %s", folder)
        sys.exit(1)

    log.info("Watching folder: %s (poll every %.1fs)", folder, poll_interval)
    log.info("Drop a coffee bag photo into this folder to process it.")
    log.info("Press Ctrl+C to stop.\n")

    seen: set[str] = set()
    # Record existing files so we don't process old ones
    for f in folder.iterdir():
        seen.add(f.name)

    try:
        while True:
            for f in sorted(folder.iterdir()):
                if f.name in seen:
                    continue
                if f.suffix.lower() not in IMAGE_EXTENSIONS:
                    seen.add(f.name)
                    continue
                # Wait a moment for the file to finish syncing
                time.sleep(2)
                seen.add(f.name)
                try:
                    process_image(client, aiden, str(f))
                    # Mark as processed
                    done_path = f.with_suffix(f.suffix + ".done")
                    f.rename(done_path)
                    seen.add(done_path.name)
                    log.info("Renamed to %s", done_path.name)
                except Exception:
                    log.exception("Error processing %s", f.name)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\nStopped watching.")


# ---------------------------------------------------------------------------
# Dropbox API watcher (no desktop client needed)
# ---------------------------------------------------------------------------

DROPBOX_DEFAULT_FOLDER = "/coffee_database"
DROPBOX_PROCESSED_TAG = ".processed"
DROPBOX_TOKEN_CACHE = os.path.join(os.path.expanduser("~"), ".bag_to_profile_dropbox_token.json")
DROPBOX_SCOPES = [
    "account_info.read",
    "files.metadata.read",
    "files.metadata.write",
    "files.content.read",
    "files.content.write",
]


def get_dropbox_client():
    """
    Authenticate with Dropbox using the OAuth2 PKCE flow.
    Caches the refresh token locally so you only need to authorize once.

    Requires: DROPBOX_APP_KEY env var (from App Console > Settings, NOT a token).
    """
    try:
        import dropbox
        from dropbox import DropboxOAuth2FlowNoRedirect
    except ImportError:
        log.error("Dropbox SDK not installed. Run: pip install dropbox")
        sys.exit(1)

    app_key = os.environ.get("DROPBOX_APP_KEY")
    if not app_key:
        log.error("Missing DROPBOX_APP_KEY environment variable.")
        log.error("")
        log.error("To get your app key:")
        log.error("  1. Go to https://www.dropbox.com/developers/apps")
        log.error("  2. Open your app (or create one: Scoped access, Full Dropbox)")
        log.error("  3. Copy the 'App key' from the Settings tab")
        log.error("  4. export DROPBOX_APP_KEY='your-app-key-here'")
        sys.exit(1)

    # Try to load cached refresh token
    if os.path.exists(DROPBOX_TOKEN_CACHE):
        try:
            with open(DROPBOX_TOKEN_CACHE, "r") as f:
                cached = json.load(f)
            refresh_token = cached.get("refresh_token")
            if refresh_token:
                dbx = dropbox.Dropbox(
                    oauth2_refresh_token=refresh_token,
                    app_key=app_key,
                )
                # Verify it works
                account = dbx.users_get_current_account()
                log.info("Connected to Dropbox: %s (%s)", account.name.display_name, account.email)
                return dbx
        except Exception as e:
            log.warning("Cached Dropbox token invalid, re-authenticating: %s", e)

    # Run OAuth2 PKCE flow (one-time browser authorization)
    auth_flow = DropboxOAuth2FlowNoRedirect(
        app_key,
        use_pkce=True,
        token_access_type="offline",
        scope=DROPBOX_SCOPES,
    )

    authorize_url = auth_flow.start()
    print("\n" + "=" * 60)
    print("  DROPBOX AUTHORIZATION (one-time setup)")
    print("=" * 60)
    print(f"\n  1. Open this URL in your browser:\n")
    print(f"     {authorize_url}\n")
    print(f"  2. Click 'Allow' to grant access")
    print(f"  3. Copy the authorization code and paste it below\n")

    auth_code = input("  Enter the authorization code: ").strip()
    print()

    try:
        oauth_result = auth_flow.finish(auth_code)
    except Exception as e:
        log.error("Authorization failed: %s", e)
        sys.exit(1)

    # Cache the refresh token
    with open(DROPBOX_TOKEN_CACHE, "w") as f:
        json.dump({"refresh_token": oauth_result.refresh_token}, f)
    os.chmod(DROPBOX_TOKEN_CACHE, 0o600)
    log.info("Dropbox authorization successful. Token cached at %s", DROPBOX_TOKEN_CACHE)

    dbx = dropbox.Dropbox(
        oauth2_refresh_token=oauth_result.refresh_token,
        app_key=app_key,
    )
    account = dbx.users_get_current_account()
    log.info("Connected to Dropbox: %s (%s)", account.name.display_name, account.email)
    return dbx


def watch_dropbox(client: OpenAI, aiden: FellowAiden, poll_interval: float = 15.0):
    """
    Poll a Dropbox folder via the API for new image files.
    Downloads new images to a temp dir, processes them, then moves them to
    a 'processed/' subfolder in Dropbox so they aren't re-processed.

    Requires: pip install dropbox
    Env vars: DROPBOX_APP_KEY, DROPBOX_FOLDER (optional, default /coffee_database)
    """
    try:
        from dropbox.exceptions import ApiError
    except ImportError:
        log.error("Dropbox SDK not installed. Run: pip install dropbox")
        sys.exit(1)

    dbx = get_dropbox_client()

    folder = os.environ.get("DROPBOX_FOLDER", DROPBOX_DEFAULT_FOLDER)
    # Ensure folder starts with /
    if not folder.startswith("/"):
        folder = "/" + folder
    processed_folder = folder.rstrip("/") + "/processed"

    # Ensure processed subfolder exists
    try:
        dbx.files_get_metadata(processed_folder)
    except ApiError:
        try:
            dbx.files_create_folder_v2(processed_folder)
            log.info("Created Dropbox folder: %s", processed_folder)
        except Exception:
            pass  # Folder may already exist in a race condition

    log.info("Watching Dropbox folder: %s (poll every %.0fs)", folder, poll_interval)
    log.info("Save a coffee bag photo to your Dropbox '%s' folder to process it.", folder.lstrip("/"))
    log.info("Press Ctrl+C to stop.\n")

    seen: set[str] = set()

    try:
        while True:
            try:
                result = dbx.files_list_folder(folder, recursive=False)
                entries = result.entries
            except ApiError as e:
                log.error("Error listing Dropbox folder: %s", e)
                time.sleep(poll_interval)
                continue

            for entry in entries:
                # Skip folders and already-seen files
                if not hasattr(entry, "path_lower"):
                    continue
                if entry.path_lower in seen:
                    continue
                if not hasattr(entry, "size"):  # It's a folder
                    seen.add(entry.path_lower)
                    continue

                # Check if it's an image
                ext = Path(entry.name).suffix.lower()
                if ext not in IMAGE_EXTENSIONS:
                    seen.add(entry.path_lower)
                    continue

                seen.add(entry.path_lower)
                log.info("New image detected: %s", entry.name)

                # Download to temp file
                try:
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        tmp_path = tmp.name
                        metadata, response = dbx.files_download(entry.path_lower)
                        tmp.write(response.content)

                    log.info("Downloaded to: %s", tmp_path)

                    # Process the image
                    process_image(client, aiden, tmp_path)

                    # Move to processed folder in Dropbox
                    dest = processed_folder + "/" + entry.name
                    try:
                        dbx.files_move_v2(entry.path_lower, dest)
                        log.info("Moved to %s", dest)
                    except ApiError:
                        # If file with same name exists, add timestamp
                        import datetime
                        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        stem = Path(entry.name).stem
                        dest = f"{processed_folder}/{stem}_{ts}{ext}"
                        dbx.files_move_v2(entry.path_lower, dest)
                        log.info("Moved to %s", dest)

                except Exception:
                    log.exception("Error processing %s", entry.name)
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\nStopped watching Dropbox.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scan a coffee bag photo and generate 4 brew profiles for Fellow Aiden.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Process a single photo
  python bag_to_profile.py photo.jpg

  # Watch a local folder (Dropbox desktop app / Google Drive)
  python bag_to_profile.py --watch ~/Dropbox/coffee_database/

  # Watch Dropbox folder via API (no desktop client needed)
  python bag_to_profile.py --dropbox

Environment variables:
  OPENAI_API_KEY         OpenAI API key (gpt-4o + o3-mini)
  FELLOW_EMAIL           Fellow account email
  FELLOW_PASSWORD        Fellow account password
  DROPBOX_APP_KEY        (--dropbox mode) Dropbox app key (from App Console)
  DROPBOX_FOLDER         (--dropbox mode) Folder path (default: /coffee_database)
""",
    )
    parser.add_argument(
        "image",
        nargs="?",
        help="Path to a coffee bag photo (jpg, png, webp).",
    )
    parser.add_argument(
        "--watch",
        metavar="FOLDER",
        help="Watch a local folder for new images (e.g. a synced Dropbox/Google Drive folder).",
    )
    parser.add_argument(
        "--dropbox",
        action="store_true",
        help="Watch your Dropbox coffee_database/ folder via the API (no desktop client needed).",
    )
    args = parser.parse_args()

    if not args.image and not args.watch and not args.dropbox:
        parser.print_help()
        sys.exit(1)

    # Validate env vars
    openai_key = os.environ.get("OPENAI_API_KEY")
    fellow_email = os.environ.get("FELLOW_EMAIL")
    fellow_password = os.environ.get("FELLOW_PASSWORD")

    missing = []
    if not openai_key:
        missing.append("OPENAI_API_KEY")
    if not fellow_email:
        missing.append("FELLOW_EMAIL")
    if not fellow_password:
        missing.append("FELLOW_PASSWORD")
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    # Initialize clients
    client = OpenAI(api_key=openai_key)
    log.info("Connecting to Fellow Aiden...")
    aiden = FellowAiden(fellow_email, fellow_password)
    log.info("Connected to: %s", aiden.get_display_name())

    if args.dropbox:
        watch_dropbox(client, aiden)
    elif args.watch:
        watch_folder(client, aiden, args.watch)
    else:
        if not Path(args.image).is_file():
            log.error("File not found: %s", args.image)
            sys.exit(1)
        process_image(client, aiden, args.image)


if __name__ == "__main__":
    main()
