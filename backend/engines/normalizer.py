"""
engines/normalizer.py

Converts nutrition facts to:
  - per_100g  (canonical comparison unit)
  - per_rs100 (value metric: nutrient per ₹100 spent on the pack)

IMPORTANT: OCR parser returns values already per-100g.
           DOM extraction returns values per-serving.
           The caller must set nutrition_unit = "per_100g" | "per_serving".
           Default assumption: per_serving (safe fallback).
"""


def normalize_nutrition(raw: dict) -> dict:
    nutrition_facts  = raw.get("nutrition_facts") or {}
    serving_size_g   = raw.get("serving_size_g")
    price_inr        = raw.get("price_inr")
    quantity_g       = raw.get("quantity_g")
    nutrition_unit   = raw.get("nutrition_unit", "per_serving")  # "per_100g" | "per_serving"

    # ── Price per 100g ────────────────────────────────────────────────────────
    price_per_100g = None
    if price_inr and quantity_g and quantity_g > 0:
        price_per_100g = round((price_inr / quantity_g) * 100, 2)

    # ── Per-100g ──────────────────────────────────────────────────────────────
    per_100g = {}

    if nutrition_facts:
        if nutrition_unit == "per_100g":
            # OCR path — values already per-100g, no conversion needed
            per_100g = {k: round(v, 2) for k, v in nutrition_facts.items()
                        if isinstance(v, (int, float))}

        elif serving_size_g and serving_size_g > 0:
            # DOM path — normalize per-serving → per-100g
            factor   = 100 / serving_size_g
            per_100g = {k: round(v * factor, 2) for k, v in nutrition_facts.items()
                        if isinstance(v, (int, float))}

        else:
            # No serving size — assume already per-100g
            per_100g = {k: round(v, 2) for k, v in nutrition_facts.items()
                        if isinstance(v, (int, float))}

    # ── Per-₹100 (protein/₹, energy/₹, etc.) ─────────────────────────────────
    # Formula: how much of this nutrient do you get per ₹100 spent on the FULL pack
    # = (nutrient_per_100g / price_per_100g) * 100
    per_rs100 = {}
    if per_100g and price_per_100g and price_per_100g > 0:
        per_rs100 = {k: round(v / price_per_100g * 100, 2) for k, v in per_100g.items()}

    return {
        "per_100g":       per_100g or None,
        "per_rs100":      per_rs100 or None,
        "price_per_100g": price_per_100g,
    }