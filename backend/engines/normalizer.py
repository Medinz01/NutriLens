"""
engines/normalizer.py

Converts raw per-serving nutrition facts into:
  - per_100g  (canonical comparison unit)
  - per_rs100 (value metric: how much nutrient per ₹100 spent)
"""


def normalize_nutrition(raw: dict) -> dict:
    nutrition_facts = raw.get("nutrition_facts") or {}
    serving_size_g  = raw.get("serving_size_g")
    price_inr       = raw.get("price_inr")
    quantity_g      = raw.get("quantity_g")

    # Price per 100g
    price_per_100g = None
    if price_inr and quantity_g and quantity_g > 0:
        price_per_100g = round((price_inr / quantity_g) * 100, 2)

    # Per-100g normalization
    per_100g = None

    if nutrition_facts:
        if serving_size_g and serving_size_g > 0:
            # Best case: normalize from per-serving values
            factor   = 100 / serving_size_g
            per_100g = {k: round(v * factor, 2) for k, v in nutrition_facts.items()
                        if isinstance(v, (int, float))}
        else:
            # Fallback: assume values are already per-100g
            # This is common when Amazon shows nutrition as per 100g directly
            per_100g = {k: round(v, 2) for k, v in nutrition_facts.items()
                        if isinstance(v, (int, float))}

    # Per-₹100 normalization
    per_rs100 = None
    if per_100g and price_per_100g and price_per_100g > 0:
        factor    = 100 / price_per_100g
        per_rs100 = {k: round(v * factor, 2) for k, v in per_100g.items()}

    return {
        "per_100g":       per_100g,
        "per_rs100":      per_rs100,
        "price_per_100g": price_per_100g,
    }

    # Per-₹100 normalization
    per_rs100 = None
    if per_100g and price_per_100g and price_per_100g > 0:
        factor   = 100 / price_per_100g
        per_rs100 = {k: round(v * factor, 2) for k, v in per_100g.items()}

    return {
        "per_100g":      per_100g,
        "per_rs100":     per_rs100,
        "price_per_100g": price_per_100g,
    }