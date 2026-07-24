"""Small brew recommendation helpers for dose, grind, and basket selection."""


def estimate_dose_grams(water_ml: int, ratio: float) -> float:
    """Estimate coffee dose from brew water and brew ratio."""
    if ratio <= 0:
        raise ValueError("ratio must be positive")
    return round(water_ml / ratio, 1)


def recommend_ode_gen2_setting(ratio: float) -> str:
    """Return a conservative Ode Gen 2 starting point for pour-over."""
    if ratio >= 17.5:
        return "6.5"
    if ratio >= 16.5:
        return "6.0"
    if ratio >= 15.5:
        return "5.5"
    if ratio >= 14.5:
        return "5.0"
    return "4.5"


def recommend_basket(dose_grams: float) -> str:
    """Pick a basket size based on the estimated coffee dose."""
    if dose_grams <= 15:
        return "1-cup / small single-serve basket"
    if dose_grams <= 22:
        return "2-cup basket"
    return "3-cup or larger basket"


def build_brew_recommendation(water_ml: int, ratio: float) -> dict:
    """Build a best-effort brew recommendation for the requested water amount."""
    dose_grams = estimate_dose_grams(water_ml, ratio)
    return {
        "dose_grams": dose_grams,
        "ode_gen2_setting": recommend_ode_gen2_setting(ratio),
        "basket": recommend_basket(dose_grams),
    }