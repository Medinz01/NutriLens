"""
engines/ranker.py

Accountability score (0–10) per product.
Transparent formula — any brand can verify it.

Score = value_score (35%) + quality_score (30%) + integrity_score (35%)

integrity_score now includes:
  - FSSAI compliance
  - Numeric claim accuracy (cross-checked against nutrition label)
  - Vague/misleading claim penalties (LLM layer — deferred)
"""

import re

# ─── Category benchmarks ──────────────────────────────────────────────────────
# protein_per_rs100 = grams of protein per ₹100 spent on the full pack

BENCHMARKS = {
    "protein_powder": {
        "protein_per_rs100_median": 26.0,
        "sugar_threshold_high":      5.0,
        "sugar_threshold_ok":        2.0,
        "protein_per_100g_good":    70.0,
        "protein_per_100g_ok":      55.0,
    },
    "health_bar": {
        "protein_per_rs100_median":  8.0,
        "sugar_threshold_high":     20.0,
        "sugar_threshold_ok":       10.0,
        "protein_per_100g_good":    15.0,
        "protein_per_100g_ok":       8.0,
    },
    "breakfast_cereal": {
        "protein_per_rs100_median":  4.0,
        "sugar_threshold_high":     15.0,
        "sugar_threshold_ok":        5.0,
        "protein_per_100g_good":    10.0,
        "protein_per_100g_ok":       5.0,
    },
    "general": {
        "protein_per_rs100_median": 10.0,
        "sugar_threshold_high":     15.0,
        "sugar_threshold_ok":        5.0,
        "protein_per_100g_good":    20.0,
        "protein_per_100g_ok":      10.0,
    },
}

# ─── Numeric claim checker ────────────────────────────────────────────────────
# Extracts numbers from claim text and cross-checks against nutrition label.
# E.g. "25g protein per scoop" + serving_size=36g + protein_per_100g=70g
#      → expected = 70 * 0.36 = 25.2g → matches 25g ✓

CLAIM_NUTRIENT_PATTERNS = [
    # (nutrient_key, regex to extract claimed value)
    ("protein_g",       re.compile(r"(\d+(?:\.\d+)?)\s*g\s+protein|protein[^,\.]{0,10}?(\d+(?:\.\d+)?)\s*g", re.I)),
    ("energy_kcal",     re.compile(r"(\d+(?:\.\d+)?)\s*kcal|(\d+(?:\.\d+)?)\s*calories", re.I)),
    ("sugar_g",         re.compile(r"(\d+(?:\.\d+)?)\s*g\s+sugar|zero\s+sugar|0\s*g\s+sugar", re.I)),
    ("total_fat_g",     re.compile(r"(\d+(?:\.\d+)?)\s*g\s+fat|low\s+fat", re.I)),
    ("carbohydrates_g", re.compile(r"(\d+(?:\.\d+)?)\s*g\s+carb", re.I)),
    ("sodium_mg",       re.compile(r"(\d+(?:\.\d+)?)\s*mg\s+sodium|low\s+sodium", re.I)),
]

TOLERANCE = 0.15  # 15% tolerance for rounding / measurement variance

def check_numeric_claims(claims: list, nutrition_per_100g: dict, serving_size_g: float) -> dict:
    """
    Cross-check numeric claims against nutrition label data.

    Returns:
        {
          "verified":     [{"claim": ..., "nutrient": ..., "claimed": ..., "actual": ..., "match": True}],
          "contradicted": [{"claim": ..., "nutrient": ..., "claimed": ..., "actual": ..., "match": False}],
          "unverifiable": [{"claim": ..., "reason": ...}]
        }
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
            continue  # title claims too broad to check numerically

        matched_any = False
        for nutrient_key, pattern in CLAIM_NUTRIENT_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue

            # Extract the claimed value
            claimed_val_str = m.group(1) or m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1) if m.lastindex else None

            # Handle "zero sugar" / "0g sugar" style claims
            if "zero" in text.lower() and nutrient_key == "sugar_g":
                claimed_val_str = "0"

            if claimed_val_str is None:
                unverifiable.append({"claim": text[:120], "reason": "no numeric value extracted"})
                matched_any = True
                break

            claimed_val = float(claimed_val_str)

            # Get actual per-serving value from nutrition data
            actual_per_100g = nutrition_per_100g.get(nutrient_key)
            if actual_per_100g is None:
                unverifiable.append({"claim": text[:120], "reason": f"{nutrient_key} not in nutrition data"})
                matched_any = True
                break

            # Convert to per-serving if serving size known
            if serving_size_g and serving_size_g > 0:
                actual_per_serving = actual_per_100g * (serving_size_g / 100)
            else:
                actual_per_serving = actual_per_100g

            # Check within tolerance
            if actual_per_serving > 0:
                diff = abs(claimed_val - actual_per_serving) / actual_per_serving
            else:
                diff = abs(claimed_val)

            entry = {
                "claim":    text[:120],
                "nutrient": nutrient_key,
                "claimed":  claimed_val,
                "actual":   round(actual_per_serving, 2),
                "unit":     "mg" if "mg" in nutrient_key else "kcal" if "kcal" in nutrient_key else "g",
            }

            if diff <= TOLERANCE:
                verified.append({**entry, "match": True})
            else:
                contradicted.append({**entry, "match": False,
                    "explanation": f"Claimed {claimed_val}, label shows {round(actual_per_serving, 1)}"})

            matched_any = True
            break  # one nutrient match per claim is enough

    return {"verified": verified, "contradicted": contradicted, "unverifiable": unverifiable}


# ─── Main scorer ──────────────────────────────────────────────────────────────

def compute_score(
    nutrition_per_100g:  dict,
    nutrition_per_rs100: dict,
    contradictions:      list,
    vague_claims:        list,
    category:            str  = "general",
    fssai:               str  = None,
    claims:              list = None,
    serving_size_g:      float = None,
) -> dict:
    """
    Returns value_score, quality_score, integrity_score, total (all 0–10).
    Also returns claim_check results for storage.
    """
    n100  = nutrition_per_100g  or {}
    nrs   = nutrition_per_rs100 or {}
    bench = BENCHMARKS.get(category, BENCHMARKS["general"])

    if not n100.get("protein_g") and not n100.get("energy_kcal"):
        return {
            "value_score":     None,
            "quality_score":   None,
            "integrity_score": None,
            "total":           None,
            "category":        category,
            "claim_check":     {},
        }

    # ── 1. Value score (0–10): protein per ₹100 vs category median ───────────
    protein_per_rs = nrs.get("protein_g", 0) or 0
    median         = bench["protein_per_rs100_median"]

    if median > 0 and protein_per_rs > 0:
        value_score = min((protein_per_rs / median) * 5.0, 10.0)
    else:
        value_score = 5.0  # no price data — neutral

    # ── 2. Quality score (0–10): nutritional composition ─────────────────────
    quality_score = 6.5

    protein = n100.get("protein_g", 0) or 0
    sugar   = n100.get("sugar_g", 0)   or 0
    sat_fat = n100.get("saturated_fat_g", 0) or 0
    sodium  = n100.get("sodium_mg", 0) or 0

    if protein >= bench["protein_per_100g_good"]:  quality_score += 2.0
    elif protein >= bench["protein_per_100g_ok"]:  quality_score += 1.0

    if sugar   > bench["sugar_threshold_high"]:    quality_score -= 2.5
    elif sugar > bench["sugar_threshold_ok"]:      quality_score -= 1.0

    if sat_fat > 10:   quality_score -= 1.0
    if sodium  > 500:  quality_score -= 1.0
    if sodium  > 300:  quality_score -= 0.5

    quality_score = round(max(0.0, min(quality_score, 10.0)), 1)

    # ── 3. Integrity score (0–10): label honesty & compliance ────────────────
    integrity_score = 10.0
    integrity_notes = []

    # FSSAI compliance (-3 if missing, mandatory by law)
    if not fssai:
        integrity_score -= 3.0
        integrity_notes.append("FSSAI license not found")
    else:
        integrity_notes.append(f"FSSAI verified: {fssai}")

    # Numeric claim accuracy
    claim_check = {}
    if claims and n100:
        claim_check = check_numeric_claims(claims, n100, serving_size_g or 0)
        n_contradicted = len(claim_check.get("contradicted", []))
        n_verified     = len(claim_check.get("verified", []))
        if n_contradicted > 0:
            integrity_score -= min(n_contradicted * 2.0, 4.0)
            integrity_notes.append(f"{n_contradicted} numeric claims contradict label")
        if n_verified > 0:
            integrity_notes.append(f"{n_verified} numeric claims verified against label")

    # Rule-based contradictions (existing engine)
    integrity_score -= 2.5 * len([c for c in contradictions if c.get("severity") == "HIGH"])
    integrity_score -= 1.5 * len([c for c in contradictions if c.get("severity") == "MEDIUM"])
    integrity_score -= 0.5 * len([c for c in contradictions if c.get("severity") == "LOW"])

    # Vague claims penalty (light — LLM will do deeper analysis later)
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
        "integrity_notes": integrity_notes,
        "claim_check":     claim_check,
    }