"""
engines/ranker.py

Accountability score (0–10) per product.
Transparent formula — any brand can verify it.

Score = value_score (35%) + quality_score (30%) + integrity_score (35%)

Category-agnostic design:
  - CATEGORY_PROFILES defines which nutrient matters for value, and which
    nutrients and thresholds define quality — per category.
  - Adding a new food category = adding a dict entry, zero code changes.
  - compute_score() signature is unchanged.
"""

import re

# ─── Category profiles ────────────────────────────────────────────────────────
#
# value_nutrient    : key from nutrition_per_rs100 used for the value score
# value_median      : market median for value_nutrient per ₹100 (grams or kcal)
# quality_base      : starting quality score before rules are applied
# quality_rules     : list of scoring rules applied in order
#
# Each quality rule:
#   nutrient    — key from nutrition_per_100g
#   direction   — "more_is_good" | "less_is_good"
#   mode        — "exclusive"  → only the first (highest) matching threshold fires
#                 "cumulative" → every matching threshold fires (additive)
#   thresholds  — list of (value, delta) sorted high → low

CATEGORY_PROFILES = {
    "protein_powder": {
        "value_nutrient": "protein_g",
        "value_median":   26.0,   # g protein per ₹100 — Indian market median
        "quality_base":    6.5,
        "quality_rules": [
            {
                "nutrient":   "protein_g",
                "direction":  "more_is_good",
                "mode":       "exclusive",
                "thresholds": [(70.0, +2.0), (55.0, +1.0)],
            },
            {
                "nutrient":   "sugar_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(5.0, -2.5), (2.0, -1.0)],
            },
            {
                "nutrient":   "saturated_fat_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(10.0, -1.0)],
            },
            {
                "nutrient":   "sodium_mg",
                "direction":  "less_is_good",
                "mode":       "cumulative",
                "thresholds": [(500.0, -1.0), (300.0, -0.5)],
            },
        ],
    },

    "health_bar": {
        "value_nutrient": "protein_g",
        "value_median":    8.0,
        "quality_base":    6.5,
        "quality_rules": [
            {
                "nutrient":   "protein_g",
                "direction":  "more_is_good",
                "mode":       "exclusive",
                "thresholds": [(15.0, +2.0), (8.0, +1.0)],
            },
            {
                "nutrient":   "sugar_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(20.0, -2.5), (10.0, -1.0)],
            },
            {
                "nutrient":   "saturated_fat_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(5.0, -1.0)],
            },
            {
                "nutrient":   "dietary_fiber_g",
                "direction":  "more_is_good",
                "mode":       "exclusive",
                "thresholds": [(5.0, +1.0), (2.0, +0.5)],
            },
        ],
    },

    "breakfast_cereal": {
        "value_nutrient": "protein_g",
        "value_median":    4.0,
        "quality_base":    6.5,
        "quality_rules": [
            {
                "nutrient":   "protein_g",
                "direction":  "more_is_good",
                "mode":       "exclusive",
                "thresholds": [(10.0, +2.0), (5.0, +1.0)],
            },
            {
                "nutrient":   "sugar_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(15.0, -2.5), (5.0, -1.0)],
            },
            {
                "nutrient":   "dietary_fiber_g",
                "direction":  "more_is_good",
                "mode":       "exclusive",
                "thresholds": [(6.0, +1.5), (3.0, +0.5)],
            },
            {
                "nutrient":   "sodium_mg",
                "direction":  "less_is_good",
                "mode":       "cumulative",
                "thresholds": [(400.0, -1.0), (200.0, -0.5)],
            },
        ],
    },

    "cooking_oil": {
        "value_nutrient": "energy_kcal",
        "value_median":   900.0,   # kcal per ₹100 — ~= 100g refined oil
        "quality_base":    7.0,
        "quality_rules": [
            {
                "nutrient":   "saturated_fat_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(30.0, -2.5), (15.0, -1.0)],
            },
            {
                "nutrient":   "trans_fat_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(2.0, -2.0), (0.5, -1.0)],
            },
        ],
    },

    "general": {
        "value_nutrient": "protein_g",
        "value_median":   10.0,
        "quality_base":    6.5,
        "quality_rules": [
            {
                "nutrient":   "protein_g",
                "direction":  "more_is_good",
                "mode":       "exclusive",
                "thresholds": [(20.0, +2.0), (10.0, +1.0)],
            },
            {
                "nutrient":   "sugar_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(15.0, -2.5), (5.0, -1.0)],
            },
            {
                "nutrient":   "saturated_fat_g",
                "direction":  "less_is_good",
                "mode":       "exclusive",
                "thresholds": [(10.0, -1.0)],
            },
            {
                "nutrient":   "sodium_mg",
                "direction":  "less_is_good",
                "mode":       "cumulative",
                "thresholds": [(500.0, -1.0), (300.0, -0.5)],
            },
        ],
    },
}

# Keep BENCHMARKS as an alias so existing tests that import it don't break
# Maps old benchmark keys to equivalent profile values for backward compat
BENCHMARKS = {
    cat: {
        "protein_per_rs100_median": p["value_median"],
        "protein_per_100g_good":    next(
            (t[0] for r in p["quality_rules"] if r["nutrient"] == "protein_g"
             and r["direction"] == "more_is_good" for t in [r["thresholds"][0]]), 20.0),
        "protein_per_100g_ok":      next(
            (t[0] for r in p["quality_rules"] if r["nutrient"] == "protein_g"
             and r["direction"] == "more_is_good" and len(r["thresholds"]) > 1
             for t in [r["thresholds"][1]]), 10.0),
        "sugar_threshold_high":     next(
            (t[0] for r in p["quality_rules"] if r["nutrient"] == "sugar_g"
             for t in [r["thresholds"][0]]), 15.0),
        "sugar_threshold_ok":       next(
            (t[0] for r in p["quality_rules"] if r["nutrient"] == "sugar_g"
             and len(r["thresholds"]) > 1 for t in [r["thresholds"][1]]), 5.0),
    }
    for cat, p in CATEGORY_PROFILES.items()
}


# ─── Quality rule evaluator ───────────────────────────────────────────────────

def _apply_quality_rules(n100: dict, rules: list) -> float:
    """
    Evaluate all quality rules against per-100g nutrition data.
    Returns the total delta to apply to quality_base.
    """
    delta = 0.0
    for rule in rules:
        value = n100.get(rule["nutrient"], 0) or 0
        direction  = rule["direction"]
        mode       = rule["mode"]
        thresholds = rule["thresholds"]  # sorted high → low

        if mode == "exclusive":
            for threshold, score_delta in thresholds:
                if direction == "more_is_good" and value >= threshold:
                    delta += score_delta
                    break
                elif direction == "less_is_good" and value > threshold:
                    delta += score_delta
                    break
        elif mode == "cumulative":
            for threshold, score_delta in thresholds:
                if direction == "more_is_good" and value >= threshold:
                    delta += score_delta
                elif direction == "less_is_good" and value > threshold:
                    delta += score_delta

    return delta


# ─── Numeric claim checker ────────────────────────────────────────────────────

CLAIM_NUTRIENT_PATTERNS = [
    ("protein_g",       re.compile(r"(\d+(?:\.\d+)?)\s*g\s+protein|protein[^,\.]{0,10}?(\d+(?:\.\d+)?)\s*g", re.I)),
    ("energy_kcal",     re.compile(r"(\d+(?:\.\d+)?)\s*kcal|(\d+(?:\.\d+)?)\s*calories", re.I)),
    ("sugar_g",         re.compile(r"(\d+(?:\.\d+)?)\s*g\s+sugar|zero\s+sugar|0\s*g\s+sugar", re.I)),
    ("total_fat_g",     re.compile(r"(\d+(?:\.\d+)?)\s*g\s+fat|low\s+fat", re.I)),
    ("carbohydrates_g", re.compile(r"(\d+(?:\.\d+)?)\s*g\s+carb", re.I)),
    ("sodium_mg",       re.compile(r"(\d+(?:\.\d+)?)\s*mg\s+sodium|low\s+sodium", re.I)),
]

TOLERANCE = 0.15


def check_numeric_claims(claims: list, nutrition_per_100g: dict, serving_size_g: float) -> dict:
    """
    Cross-check numeric claims against nutrition label data.
    Returns verified / contradicted / unverifiable buckets.
    """
    if not claims or not nutrition_per_100g:
        return {"verified": [], "contradicted": [], "unverifiable": []}

    verified     = []
    contradicted = []
    unverifiable = []

    for claim in claims:
        text   = claim.get("text", "") if isinstance(claim, dict) else claim
        source = claim.get("source", "bullet") if isinstance(claim, dict) else "bullet"
        if source == "title":
            continue

        for nutrient_key, pattern in CLAIM_NUTRIENT_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue

            claimed_val_str = (
                m.group(1) or m.group(2)
                if m.lastindex and m.lastindex >= 2
                else m.group(1) if m.lastindex else None
            )

            if "zero" in text.lower() and nutrient_key == "sugar_g":
                claimed_val_str = "0"

            if claimed_val_str is None:
                unverifiable.append({"claim": text[:120], "reason": "no numeric value extracted"})
                break

            claimed_val     = float(claimed_val_str)
            actual_per_100g = nutrition_per_100g.get(nutrient_key)

            if actual_per_100g is None:
                unverifiable.append({"claim": text[:120], "reason": f"{nutrient_key} not in nutrition data"})
                break

            actual = actual_per_100g * (serving_size_g / 100) if (serving_size_g and serving_size_g > 0) else actual_per_100g
            diff   = abs(claimed_val - actual) / actual if actual > 0 else abs(claimed_val)

            entry = {
                "claim":    text[:120],
                "nutrient": nutrient_key,
                "claimed":  claimed_val,
                "actual":   round(actual, 2),
                "unit":     "mg" if "mg" in nutrient_key else "kcal" if "kcal" in nutrient_key else "g",
            }

            if diff <= TOLERANCE:
                verified.append({**entry, "match": True})
            else:
                contradicted.append({**entry, "match": False,
                    "explanation": f"Claimed {claimed_val}, label shows {round(actual, 1)}"})
            break

    return {"verified": verified, "contradicted": contradicted, "unverifiable": unverifiable}


# ─── Main scorer ──────────────────────────────────────────────────────────────

def compute_score(
    nutrition_per_100g:  dict,
    nutrition_per_rs100: dict,
    contradictions:      list,
    vague_claims:        list,
    category:            str   = "general",
    fssai:               str   = None,
    claims:              list  = None,
    serving_size_g:      float = None,
) -> dict:
    """
    Returns value_score, quality_score, integrity_score, total (all 0–10).
    Signature unchanged — drop-in replacement for the previous implementation.
    """
    n100    = nutrition_per_100g  or {}
    nrs     = nutrition_per_rs100 or {}
    profile = CATEGORY_PROFILES.get(category, CATEGORY_PROFILES["general"])

    # Require at least one meaningful nutrient value to score
    if not any(n100.get(k) for k in ("protein_g", "energy_kcal", "total_fat_g", "carbohydrates_g")):
        return {
            "value_score":     None,
            "quality_score":   None,
            "integrity_score": None,
            "total":           None,
            "category":        category,
            "claim_check":     {},
        }

    # ── 1. Value score (0–10) ─────────────────────────────────────────────────
    # How much of the category's key nutrient do you get per ₹100?
    value_nutrient    = profile["value_nutrient"]
    value_median      = profile["value_median"]
    nutrient_per_rs   = nrs.get(value_nutrient, 0) or 0

    if value_median > 0 and nutrient_per_rs > 0:
        value_score = min((nutrient_per_rs / value_median) * 5.0, 10.0)
    else:
        value_score = 5.0  # no price data — neutral

    # ── 2. Quality score (0–10) ───────────────────────────────────────────────
    quality_delta = _apply_quality_rules(n100, profile["quality_rules"])
    quality_score = round(max(0.0, min(profile["quality_base"] + quality_delta, 10.0)), 1)

    # ── 3. Integrity score (0–10) ─────────────────────────────────────────────
    integrity_score = 10.0
    integrity_notes = []

    # FSSAI compliance
    if not fssai:
        integrity_score -= 3.0
        integrity_notes.append("FSSAI license not found")
    else:
        integrity_notes.append(f"FSSAI verified: {fssai}")

    # Energy cross-check (Codex CAC/GL 2-1985 s3.3.1)
    # Expected kcal = (protein * 4) + (carbs * 4) + (fat * 9)
    declared_kcal = n100.get("energy_kcal")
    _protein      = n100.get("protein_g", 0) or 0
    _carbs        = n100.get("carbohydrates_g", 0) or 0
    _fat          = n100.get("total_fat_g", 0) or 0

    if declared_kcal and (_protein or _carbs or _fat):
        expected_kcal = (_protein * 4) + (_carbs * 4) + (_fat * 9)
        if expected_kcal > 0:
            energy_diff = abs(declared_kcal - expected_kcal) / expected_kcal
            if energy_diff > 0.10:
                integrity_score -= 1.0
                integrity_notes.append(
                    f"Energy mismatch: declared {declared_kcal}kcal, "
                    f"macro calculation gives {round(expected_kcal)}kcal "
                    f"({round(energy_diff * 100)}% deviation)"
                )

    # Numeric claim accuracy
    claim_check = {}
    if claims and n100:
        claim_check    = check_numeric_claims(claims, n100, serving_size_g or 0)
        n_contradicted = len(claim_check.get("contradicted", []))
        n_verified     = len(claim_check.get("verified", []))
        if n_contradicted > 0:
            integrity_score -= min(n_contradicted * 2.0, 4.0)
            integrity_notes.append(f"{n_contradicted} numeric claims contradict label")
        if n_verified > 0:
            integrity_notes.append(f"{n_verified} numeric claims verified against label")

    # Severity-based contradiction deductions
    integrity_score -= 2.5 * len([c for c in contradictions if c.get("severity") == "HIGH"])
    integrity_score -= 1.5 * len([c for c in contradictions if c.get("severity") == "MEDIUM"])
    integrity_score -= 0.5 * len([c for c in contradictions if c.get("severity") == "LOW"])

    # Vague claims (light penalty — LLM layer will deepen this)
    integrity_score -= 0.2 * len(vague_claims)

    integrity_score = round(max(0.0, min(integrity_score, 10.0)), 1)

    # ── Weighted total ────────────────────────────────────────────────────────
    total = round(
        value_score     * 0.35 +
        quality_score   * 0.30 +
        integrity_score * 0.35,
        1
    )

    return {
        "value_score":     round(value_score, 1),
        "quality_score":   round(quality_score, 1),
        "integrity_score": round(integrity_score, 1),
        "total":           total,
        "category":        category,
        "value_nutrient":  value_nutrient,   # tells the popup which nutrient drove value score
        "integrity_notes": integrity_notes,
        "claim_check":     claim_check,
    }