"""
engines/ranker.py

Computes a transparent, explainable NutriScore (0–10) per product.
Formula is public and documented so any brand can verify it.

Score = value_score (40%) + quality_score (35%) + integrity_score (25%)
"""

# Category-specific benchmarks (protein per ₹100)
# Based on market survey of ~50 products (update these as data accumulates)
BENCHMARKS = {
    "protein_powder": {
        "protein_per_rs100_median": 26.0,   # g protein per ₹100
        "sugar_threshold_high":      5.0,    # g per 100g
        "sugar_threshold_ok":        2.0,
        "protein_per_100g_good":    70.0,
        "protein_per_100g_ok":      60.0,
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


def compute_score(
    nutrition_per_100g: dict,
    nutrition_per_rs100: dict,
    contradictions: list,
    vague_claims: list,
    category: str = "general",
) -> dict:
    """
    Returns dict with value_score, quality_score, integrity_score, total (all 0–10).
    Returns all None if insufficient data.
    """
    n100  = nutrition_per_100g  or {}
    nrs   = nutrition_per_rs100 or {}
    bench = BENCHMARKS.get(category, BENCHMARKS["general"])

    # Need at least protein data to score meaningfully
    if not n100.get("protein_g") and not n100.get("energy_kcal"):
        return {
            "value_score":     None,
            "quality_score":   None,
            "integrity_score": None,
            "total":           None,
            "category":        category,
        }

    # ── Value Score (0–10): protein per ₹100 vs category median ─────────────
    protein_per_rs = nrs.get("protein_g", 0)
    median         = bench["protein_per_rs100_median"]

    if median > 0 and protein_per_rs > 0:
        # Linear scale: median = 5.0, double median = 10.0, zero = 0
        value_score = min((protein_per_rs / median) * 5.0, 10.0)
    else:
        value_score = 5.0  # No price data — neutral score

    # ── Quality Score (0–10): penalise high sugar, reward high protein ───────
    quality_score = 7.0  # Start at neutral

    # Sugar penalty
    sugar = n100.get("sugar_g", 0)
    if sugar > bench["sugar_threshold_high"]:
        quality_score -= 3.0
    elif sugar > bench["sugar_threshold_ok"]:
        quality_score -= 1.5

    # Protein bonus
    protein = n100.get("protein_g", 0)
    if protein >= bench["protein_per_100g_good"]:
        quality_score += 2.0
    elif protein >= bench["protein_per_100g_ok"]:
        quality_score += 1.0

    # Saturated fat penalty
    sat_fat = n100.get("saturated_fat_g", 0)
    if sat_fat > 10:
        quality_score -= 1.0

    # Sodium penalty
    sodium = n100.get("sodium_mg", 0)
    if sodium > 400:
        quality_score -= 1.0

    quality_score = max(0.0, min(quality_score, 10.0))

    # ── Integrity Score (0–10): label honesty ─────────────────────────────────
    integrity_score = 10.0
    integrity_score -= 2.5 * len([c for c in contradictions if c["severity"] == "HIGH"])
    integrity_score -= 1.5 * len([c for c in contradictions if c["severity"] == "MEDIUM"])
    integrity_score -= 0.5 * len([c for c in contradictions if c["severity"] == "LOW"])
    integrity_score -= 0.3 * len(vague_claims)
    integrity_score  = max(0.0, integrity_score)

    # ── Weighted total ────────────────────────────────────────────────────────
    total = (
        value_score     * 0.40 +
        quality_score   * 0.35 +
        integrity_score * 0.25
    )

    return {
        "value_score":     round(value_score, 1),
        "quality_score":   round(quality_score, 1),
        "integrity_score": round(integrity_score, 1),
        "total":           round(total, 1),
        "category":        category,
    }
