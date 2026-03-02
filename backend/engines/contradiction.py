"""
engines/contradiction.py

Rule-based contradiction detection grounded in FSSAI regulations.
Each rule has:
  - trigger_phrases: claim text patterns to match
  - condition: function(nutrition_per_100g) → bool (True = contradiction found)
  - severity: HIGH | MEDIUM | LOW
  - explanation: human-readable message shown in the extension
  - citation: FSSAI document reference

Sources:
  - FSSAI Food Safety and Standards (Labelling and Display) Regulations, 2020
  - FSSAI Draft Food Safety and Standards (Health Claims) Regulations
  - https://www.fssai.gov.in/upload/uploadfiles/files/Compendium_Labelling_Regulations.pdf
"""

import re
from typing import Optional


FSSAI_RULES = [
    # ── Sugar claims ─────────────────────────────────────────────────────────
    {
        "id": "sugar_free",
        "trigger_phrases": ["sugar free", "sugar-free", "zero sugar", "no sugar", "without sugar"],
        "condition": lambda n: (n.get("sugar_g") or 0) > 0.5,
        "severity": "HIGH",
        "explanation": "Claims to be sugar-free but label shows {sugar_g}g sugar per 100g. "
                       "FSSAI permits 'sugar free' only when sugar content is ≤0.5g per 100g.",
        "citation": "https://www.fssai.gov.in/upload/uploadfiles/files/Compendium_Labelling_Regulations.pdf"
    },
    {
        "id": "no_added_sugar",
        "trigger_phrases": ["no added sugar", "without added sugar", "zero added sugar"],
        "condition": lambda n: (n.get("sugar_g") or 0) > 5,
        "severity": "MEDIUM",
        "explanation": "Claims no added sugar but total sugar is {sugar_g}g per 100g, "
                       "which may indicate naturally high sugar content not disclosed prominently.",
        "citation": "https://www.fssai.gov.in"
    },
    {
        "id": "low_sugar",
        "trigger_phrases": ["low sugar", "reduced sugar", "less sugar"],
        "condition": lambda n: (n.get("sugar_g") or 0) > 5,
        "severity": "MEDIUM",
        "explanation": "Claims 'low sugar' but contains {sugar_g}g sugar per 100g. "
                       "FSSAI requires ≤5g sugar per 100g for a 'low sugar' claim.",
        "citation": "https://www.fssai.gov.in"
    },

    # ── Fat claims ────────────────────────────────────────────────────────────
    {
        "id": "fat_free",
        "trigger_phrases": ["fat free", "fat-free", "zero fat", "no fat", "0% fat"],
        "condition": lambda n: (n.get("total_fat_g") or 0) > 0.5,
        "severity": "HIGH",
        "explanation": "Claims fat-free but label shows {total_fat_g}g fat per 100g. "
                       "FSSAI permits 'fat free' only when fat is ≤0.5g per 100g.",
        "citation": "https://www.fssai.gov.in"
    },
    {
        "id": "low_fat",
        "trigger_phrases": ["low fat", "reduced fat", "light", "lite"],
        "condition": lambda n: (n.get("total_fat_g") or 0) > 3,
        "severity": "MEDIUM",
        "explanation": "Claims low fat but contains {total_fat_g}g fat per 100g. "
                       "FSSAI requires ≤3g fat per 100g for a 'low fat' claim on solid foods.",
        "citation": "https://www.fssai.gov.in"
    },

    # ── Sodium claims ─────────────────────────────────────────────────────────
    {
        "id": "low_sodium",
        "trigger_phrases": ["low sodium", "low salt", "reduced sodium", "less salt"],
        "condition": lambda n: (n.get("sodium_mg") or 0) > 120,
        "severity": "MEDIUM",
        "explanation": "Claims low sodium but contains {sodium_mg}mg sodium per 100g. "
                       "FSSAI requires ≤120mg sodium per 100g for a 'low sodium' claim.",
        "citation": "https://www.fssai.gov.in"
    },
    {
        "id": "sodium_free",
        "trigger_phrases": ["sodium free", "salt free", "zero sodium", "no salt"],
        "condition": lambda n: (n.get("sodium_mg") or 0) > 5,
        "severity": "HIGH",
        "explanation": "Claims sodium-free but contains {sodium_mg}mg sodium per 100g. "
                       "FSSAI permits 'sodium free' only when sodium is ≤5mg per 100g.",
        "citation": "https://www.fssai.gov.in"
    },

    # ── Protein claims ────────────────────────────────────────────────────────
    {
        "id": "high_protein",
        "trigger_phrases": ["high protein", "protein rich", "excellent source of protein"],
        "condition": lambda n: (n.get("protein_g") or 0) < 20,
        "severity": "MEDIUM",
        "explanation": "Claims 'high protein' but contains only {protein_g}g protein per 100g. "
                       "FSSAI requires ≥20g protein per 100g (or ≥20% of energy from protein) "
                       "for a 'high protein' claim.",
        "citation": "https://www.fssai.gov.in"
    },
    {
        "id": "source_of_protein",
        "trigger_phrases": ["source of protein", "good source of protein", "contains protein"],
        "condition": lambda n: (n.get("protein_g") or 0) < 10,
        "severity": "LOW",
        "explanation": "Claims 'source of protein' but contains only {protein_g}g protein per 100g. "
                       "FSSAI requires ≥10g per 100g for a 'source of protein' claim.",
        "citation": "https://www.fssai.gov.in"
    },

    # ── Calorie claims ────────────────────────────────────────────────────────
    {
        "id": "low_calorie",
        "trigger_phrases": ["low calorie", "low cal", "reduced calorie", "diet", "light"],
        "condition": lambda n: (n.get("energy_kcal") or 0) > 40,
        "severity": "MEDIUM",
        "explanation": "Claims 'low calorie' but contains {energy_kcal} kcal per 100g. "
                       "FSSAI requires ≤40 kcal per 100g for solids for a 'low calorie' claim.",
        "citation": "https://www.fssai.gov.in"
    },
    {
        "id": "calorie_free",
        "trigger_phrases": ["calorie free", "zero calories", "no calories", "0 cal"],
        "condition": lambda n: (n.get("energy_kcal") or 0) > 4,
        "severity": "HIGH",
        "explanation": "Claims calorie-free but contains {energy_kcal} kcal per 100g. "
                       "FSSAI permits 'calorie free' only when energy is ≤4 kcal per 100g.",
        "citation": "https://www.fssai.gov.in"
    },
]

# Vague/unverifiable claims — not contradictions but worth flagging
VAGUE_CLAIM_PATTERNS = [
    ("boosts immunity",         "No scientific consensus supports generic 'immunity boosting' claims for this ingredient category."),
    ("immunity booster",        "No scientific consensus supports generic 'immunity boosting' claims for this ingredient category."),
    ("superfood",               "The term 'superfood' has no regulatory definition under FSSAI or any major food authority."),
    ("detox",                   "'Detox' is not a recognised nutritional claim under FSSAI regulations."),
    ("detoxify",                "'Detox' is not a recognised nutritional claim under FSSAI regulations."),
    ("gut health",              "Generic 'gut health' claims are not permitted without specific probiotic strain evidence under FSSAI."),
    ("boosts metabolism",       "No standardised criterion exists for 'boosts metabolism' claims under FSSAI."),
    ("anti-aging",              "Anti-aging claims are not permitted on food products under FSSAI labelling regulations."),
    ("anti aging",              "Anti-aging claims are not permitted on food products under FSSAI labelling regulations."),
    ("burns fat",               "Fat-burning claims are considered medicinal and are not permitted on food products."),
    ("fat burner",              "Fat-burning claims are considered medicinal and are not permitted on food products."),
    ("clinically proven",       "Requires citation of specific peer-reviewed evidence — check product for study reference."),
    ("scientifically proven",   "Requires citation of specific peer-reviewed evidence — check product for study reference."),
    ("natural",                 "The term 'natural' has no strict regulatory definition under FSSAI."),
    ("100% natural",            "'100% natural' has no strict regulatory definition under FSSAI."),
    ("chemical free",           "All food is composed of chemicals — this claim is scientifically meaningless."),
    ("no chemicals",            "All food is composed of chemicals — this claim is scientifically meaningless."),
]


def run_contradiction_engine(
    claims_text: str,
    nutrition_per_100g: dict,
) -> tuple[list[dict], list[dict]]:
    """
    Returns:
      contradictions: list of {claim, explanation, severity, citation}
      vague_claims:   list of {claim, reason}
    """
    if not claims_text:
        return [], []

    text_lower = claims_text.lower()
    contradictions = []
    vague_claims   = []
    seen_rules     = set()

    # ── Contradiction check ──────────────────────────────────────────────────
    for rule in FSSAI_RULES:
        if rule["id"] in seen_rules:
            continue

        matched_phrase = None
        for phrase in rule["trigger_phrases"]:
            if phrase in text_lower:
                matched_phrase = phrase
                break

        if not matched_phrase:
            continue

        # Only flag if nutrition data is available to verify
        if not nutrition_per_100g:
            continue

        try:
            is_contradiction = rule["condition"](nutrition_per_100g)
        except Exception:
            continue

        if is_contradiction:
            # Format explanation with actual values
            explanation = rule["explanation"]
            for key, val in nutrition_per_100g.items():
                placeholder = "{" + key + "}"
                if placeholder in explanation:
                    explanation = explanation.replace(placeholder, f"{val:.1f}")

            contradictions.append({
                "claim":       matched_phrase,
                "explanation": explanation,
                "severity":    rule["severity"],
                "citation":    rule.get("citation"),
            })
            seen_rules.add(rule["id"])

    # ── Vague claim check ────────────────────────────────────────────────────
    seen_vague = set()
    for phrase, reason in VAGUE_CLAIM_PATTERNS:
        if phrase in text_lower and phrase not in seen_vague:
            vague_claims.append({"claim": phrase, "reason": reason})
            seen_vague.add(phrase)

    return contradictions, vague_claims