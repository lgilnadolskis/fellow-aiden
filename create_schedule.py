#!/usr/bin/env python3
"""
Create a brew schedule on your Fellow Aiden.

Modes:
  Interactive:  python create_schedule.py
  Quick brew:   python create_schedule.py --now
  One-liner:    python create_schedule.py --profile "My Coffee" --time 7:30am --days weekdays --water 450

Required env vars:
  FELLOW_EMAIL      — Fellow account email
  FELLOW_PASSWORD   — Fellow account password
"""

import argparse
import os
import sys
import logging
from datetime import datetime, timedelta

from fellow_aiden import FellowAiden

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("create_schedule")

# Silence the fellow_aiden library's verbose DEBUG handler
logging.getLogger("FELLOW-AIDEN").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Day helpers
# ---------------------------------------------------------------------------

DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

DAY_SHORTCUTS = {
    'everyday':  [True, True, True, True, True, True, True],
    'weekdays':  [False, True, True, True, True, True, False],
    'weekends':  [True, False, False, False, False, False, True],
    'sunday':    [True, False, False, False, False, False, False],
    'sun':       [True, False, False, False, False, False, False],
    'monday':    [False, True, False, False, False, False, False],
    'mon':       [False, True, False, False, False, False, False],
    'tuesday':   [False, False, True, False, False, False, False],
    'tue':       [False, False, True, False, False, False, False],
    'wednesday': [False, False, False, True, False, False, False],
    'wed':       [False, False, False, True, False, False, False],
    'thursday':  [False, False, False, False, True, False, False],
    'thu':       [False, False, False, False, True, False, False],
    'friday':    [False, False, False, False, False, True, False],
    'fri':       [False, False, False, False, False, True, False],
    'saturday':  [False, False, False, False, False, False, True],
    'sat':       [False, False, False, False, False, False, True],
}


def parse_days(text: str) -> list[bool]:
    """Parse a days string into a 7-element bool list [Sun..Sat].

    Accepts: 'everyday', 'weekdays', 'weekends', or comma-separated day names
    like 'mon,wed,fri' or 'monday,wednesday,friday'.
    """
    text = text.strip().lower()
    if text in DAY_SHORTCUTS:
        return DAY_SHORTCUTS[text]

    # Comma-separated list
    result = [False] * 7
    for part in text.split(','):
        part = part.strip()
        if part in DAY_SHORTCUTS:
            shortcut = DAY_SHORTCUTS[part]
            result = [a or b for a, b in zip(result, shortcut)]
        else:
            raise ValueError(
                f"Unknown day '{part}'. Use: everyday, weekdays, weekends, "
                f"or day names (sun, mon, tue, wed, thu, fri, sat)."
            )
    return result


def days_to_string(days: list[bool]) -> str:
    """Convert bool list to readable string."""
    active = [DAY_NAMES[i] for i, on in enumerate(days) if on]
    if all(days):
        return "Everyday"
    if days == DAY_SHORTCUTS['weekdays']:
        return "Weekdays (Mon-Fri)"
    if days == DAY_SHORTCUTS['weekends']:
        return "Weekends (Sat-Sun)"
    return ', '.join(active) if active else 'None'


def parse_time(text: str) -> int:
    """Parse a time string into seconds from midnight.

    Accepts: '7:30am', '7:30 AM', '14:30', '2:30pm', '7:30', '730am', etc.
    """
    text = text.strip().lower().replace(' ', '')

    # Detect am/pm
    is_pm = 'pm' in text
    is_am = 'am' in text
    text = text.replace('am', '').replace('pm', '')

    # Handle HH:MM or HHMM
    if ':' in text:
        parts = text.split(':')
        hour = int(parts[0])
        minute = int(parts[1])
    elif len(text) <= 2:
        hour = int(text)
        minute = 0
    elif len(text) == 3:
        hour = int(text[0])
        minute = int(text[1:])
    elif len(text) == 4:
        hour = int(text[:2])
        minute = int(text[2:])
    else:
        raise ValueError(f"Cannot parse time: '{text}'")

    # Apply am/pm
    if is_pm and hour < 12:
        hour += 12
    if is_am and hour == 12:
        hour = 0

    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"Invalid time: {hour}:{minute:02d}")

    return hour * 3600 + minute * 60


def seconds_to_time_str(seconds: int) -> str:
    """Convert seconds from midnight to readable time string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    period = "AM" if hours < 12 else "PM"
    display_hour = hours % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{minutes:02d} {period}"


def get_now_plus_10() -> tuple[int, list[bool]]:
    """Get time (now + 10 min) and today's day as a schedule.

    Returns (seconds_from_midnight, days_list).
    """
    now = datetime.now()
    brew_time = now + timedelta(minutes=10)
    seconds = brew_time.hour * 3600 + brew_time.minute * 60

    # datetime weekday: 0=Mon, need to map to [Sun=0, Mon=1, ..., Sat=6]
    py_weekday = brew_time.weekday()  # 0=Mon
    schedule_idx = (py_weekday + 1) % 7  # Sun=0
    days = [False] * 7
    days[schedule_idx] = True

    return seconds, days


# ---------------------------------------------------------------------------
# Profile display
# ---------------------------------------------------------------------------

def display_profiles(profiles: list[dict]):
    """Print profiles in a numbered list, grouped by folder."""
    # Group by folder
    groups: dict[str, list[tuple[int, dict]]] = {}
    for idx, p in enumerate(profiles, 1):
        folder = p.get('folder', 'Other') or 'Other'
        groups.setdefault(folder, []).append((idx, p))

    # Determine column width from longest title
    max_title = max((len(p.get('title', '')) for p in profiles), default=20)
    col = max(max_title + 2, 25)

    print(f"\nAvailable profiles ({len(profiles)}):\n")
    # Show Custom first, then Fellow, then Drops, then anything else
    order = ['Custom', 'Fellow', 'Drops']
    for folder in order + [f for f in groups if f not in order]:
        if folder not in groups:
            continue
        print(f"[{folder}]")
        for idx, p in groups[folder]:
            bloom = "bloom" if p.get("bloomEnabled") else "no bloom"
            title = p.get('title', 'Untitled')
            print(f"  {idx:>2}. {title:<{col}} ratio 1:{p.get('ratio')}, {bloom}")
        print()


def select_profile(profiles: list[dict], selection: str = None) -> dict:
    """Select a profile by number or name."""
    if selection is not None:
        # Try as number
        try:
            idx = int(selection) - 1
            if 0 <= idx < len(profiles):
                return profiles[idx]
        except ValueError:
            pass
        # Try as name (fuzzy)
        selection_lower = selection.lower()
        for p in profiles:
            if selection_lower in p.get('title', '').lower():
                return p
        raise ValueError(f"No profile matching '{selection}'")
    return None


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def interactive_mode(aiden: FellowAiden):
    """Step-by-step schedule creation wizard."""
    print("\nSchedule Creator\n")

    # Step 1: Select profile
    profiles = aiden.get_profiles()
    if not profiles:
        print("No profiles found on your Aiden. Create one first.")
        return None

    display_profiles(profiles)

    while True:
        choice = input("Select a profile (number or name): ").strip()
        try:
            profile = select_profile(profiles, choice)
            if profile:
                break
        except ValueError as e:
            print(f"Error: {e}")

    print(f"Selected: {profile['title']}")

    # Step 2: Days
    print()
    print("When should this brew?")
    print("Options: everyday, weekdays, weekends, or specific days like mon,wed,fri")

    while True:
        days_input = input("Days: ").strip()
        try:
            days = parse_days(days_input)
            break
        except ValueError as e:
            print(f"Error: {e}")

    print(f"Days: {days_to_string(days)}")

    # Step 3: Time
    print()
    print("What time? Examples: 7:30am, 14:30, 6am")

    while True:
        time_input = input("Time: ").strip()
        try:
            seconds = parse_time(time_input)
            break
        except ValueError as e:
            print(f"Error: {e}")

    print(f"Time: {seconds_to_time_str(seconds)}")

    # Step 4: Water amount
    print()
    print("How much water? 150 to 1500 ml, default 450.")

    while True:
        water_input = input("Water in ml: ").strip()
        if not water_input:
            water = 450
            break
        try:
            water = int(water_input.replace('ml', '').strip())
            if 150 <= water <= 1500:
                break
            print("Error: Must be between 150 and 1500 ml.")
        except ValueError:
            print("Error: Enter a number between 150 and 1500.")

    print(f"Water: {water} ml")

    # Confirm
    print()
    print("Schedule summary:")
    print(f"  Profile: {profile['title']}")
    print(f"  Days: {days_to_string(days)}")
    print(f"  Time: {seconds_to_time_str(seconds)}")
    print(f"  Water: {water} ml")
    print()

    confirm = input("Create this schedule? Y or n: ").strip().lower()
    if confirm and confirm != 'y':
        print("Cancelled.")
        return None

    return create_and_save_schedule(aiden, profile['id'], days, seconds, water)


# ---------------------------------------------------------------------------
# Quick brew (--now)
# ---------------------------------------------------------------------------

def now_mode(aiden: FellowAiden, water: int = 450):
    """Pick a profile and brew in ~10 minutes."""
    print("\nQuick Brew - starts in about 10 minutes\n")

    profiles = aiden.get_profiles()
    if not profiles:
        print("No profiles found on your Aiden. Create one first.")
        return None

    display_profiles(profiles)

    while True:
        choice = input("Pick a profile (number or name): ").strip()
        try:
            profile = select_profile(profiles, choice)
            if profile:
                break
        except ValueError as e:
            print(f"Error: {e}")

    seconds, days = get_now_plus_10()

    print(f"\nProfile: {profile['title']}")
    print(f"Brew at: {seconds_to_time_str(seconds)} (now plus 10 minutes)")
    print(f"Water: {water} ml")
    print()

    confirm = input("Start? Y or n: ").strip().lower()
    if confirm and confirm != 'y':
        print("Cancelled.")
        return None

    return create_and_save_schedule(aiden, profile['id'], days, seconds, water)


# ---------------------------------------------------------------------------
# Create schedule
# ---------------------------------------------------------------------------

def create_and_save_schedule(aiden: FellowAiden, profile_id: str, days: list[bool],
                             seconds: int, water: int) -> dict | None:
    """Build and push a schedule to the Aiden."""
    schedule_data = {
        "days": days,
        "secondFromStartOfTheDay": seconds,
        "enabled": True,
        "amountOfWater": water,
        "profileId": profile_id,
    }

    print("\nSaving schedule to Aiden...")
    try:
        result = aiden.create_schedule(schedule_data)
        print(f"Schedule created. ID: {result.get('id', 'unknown')}")
        return result
    except Exception as e:
        print(f"Failed to create schedule: {e}")
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Create a brew schedule on your Fellow Aiden.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Interactive wizard
  python create_schedule.py

  # Quick brew — pick a profile, brew in 10 minutes
  python create_schedule.py --now

  # Quick brew with specific water amount
  python create_schedule.py --now --water 600

  # One-liner
  python create_schedule.py --profile "My Coffee" --time 7:30am --days weekdays --water 450

  # One-liner with day list
  python create_schedule.py --profile "Fruit Cake" --time 6am --days mon,wed,fri

Environment variables:
  FELLOW_EMAIL       Fellow account email
  FELLOW_PASSWORD    Fellow account password
""",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Quick brew: pick a profile and schedule it for now + 10 minutes.",
    )
    parser.add_argument(
        "--profile",
        metavar="NAME",
        help="Profile name or number (use with --time and --days for one-liner mode).",
    )
    parser.add_argument(
        "--time",
        metavar="TIME",
        help="Brew time (e.g., 7:30am, 14:30, 6am).",
    )
    parser.add_argument(
        "--days",
        metavar="DAYS",
        help="Days to brew (everyday, weekdays, weekends, or mon,wed,fri).",
    )
    parser.add_argument(
        "--water",
        type=int,
        default=450,
        metavar="ML",
        help="Water amount in ml (150-1500, default: 450).",
    )
    args = parser.parse_args()

    # Validate env vars
    fellow_email = os.environ.get("FELLOW_EMAIL")
    fellow_password = os.environ.get("FELLOW_PASSWORD")

    if not fellow_email or not fellow_password:
        log.error("Missing FELLOW_EMAIL and/or FELLOW_PASSWORD environment variables.")
        sys.exit(1)

    # Connect
    log.info("Connecting to Fellow Aiden...")
    aiden = FellowAiden(fellow_email, fellow_password)
    log.info("Connected to: %s", aiden.get_display_name())

    # Dispatch
    if args.now:
        now_mode(aiden, water=args.water)

    elif args.profile and args.time and args.days:
        # One-liner mode
        profiles = aiden.get_profiles()
        if not profiles:
            log.error("No profiles found on your Aiden.")
            sys.exit(1)

        try:
            profile = select_profile(profiles, args.profile)
        except ValueError as e:
            log.error(str(e))
            sys.exit(1)

        try:
            days = parse_days(args.days)
        except ValueError as e:
            log.error(str(e))
            sys.exit(1)

        try:
            seconds = parse_time(args.time)
        except ValueError as e:
            log.error(str(e))
            sys.exit(1)

        water = args.water
        if not (150 <= water <= 1500):
            log.error("Water must be between 150 and 1500ml.")
            sys.exit(1)

        print(f"\nProfile: {profile['title']}")
        print(f"Days: {days_to_string(days)}")
        print(f"Time: {seconds_to_time_str(seconds)}")
        print(f"Water: {water} ml")

        create_and_save_schedule(aiden, profile['id'], days, seconds, water)

    elif args.profile or args.time or args.days:
        log.error("One-liner mode requires all three: --profile, --time, and --days")
        sys.exit(1)

    else:
        interactive_mode(aiden)


if __name__ == "__main__":
    main()
