"""Helpers for matching user input to Fellow profile titles."""

from difflib import SequenceMatcher
import re


def normalize_profile_text(text: str) -> str:
    """Lowercase text and strip all non-alphanumeric characters."""
    return re.sub(r'[^a-z0-9]+', '', text.lower())


def profile_match_score(selection: str, title: str) -> float:
    """Return a similarity score between a user selection and a title."""
    selection_norm = normalize_profile_text(selection)
    title_norm = normalize_profile_text(title)
    if not selection_norm or not title_norm:
        return 0.0
    if selection_norm == title_norm:
        return 1.0
    if selection_norm in title_norm or title_norm in selection_norm:
        return 0.95
    return SequenceMatcher(None, selection_norm, title_norm).ratio()


def select_best_profile(profiles: list[dict], selection: str) -> dict:
    """Select the best matching profile from a list."""
    selection = selection.strip()
    if not selection:
        raise ValueError("No profile selection provided")

    try:
        idx = int(selection) - 1
        if 0 <= idx < len(profiles):
            return profiles[idx]
    except ValueError:
        pass

    best_profile = None
    best_score = 0.0
    for profile in profiles:
        title = profile.get('title', '')
        score = profile_match_score(selection, title)
        if score > best_score:
            best_score = score
            best_profile = profile

    if best_profile and best_score >= 0.6:
        return best_profile

    raise ValueError(f"No profile matching '{selection}'")