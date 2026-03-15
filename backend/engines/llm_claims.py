"""
engines/llm_claims.py

Phase 7 — LLM claim intelligence via Groq API.

Runs AFTER the rule-based contradiction engine as a second pass.
The rule engine catches clear numeric violations (sugar-free but 10g sugar).
The LLM catches softer issues: vague efficacy claims, comparative claims
without evidence, misleading implications, unsubstantiated certifications.

Design principles:
  - Fails gracefully: if Groq is down or key missing, returns empty results
    and the rule-based engine output is used as-is.
  - Additive: never removes rule-based contradictions, only adds new ones.
  - Structured output: prompt forces JSON so no parsing guesswork.
  - Fast: single API call per product, ~1-2s on Groq free tier.
"""

import json
import logging
import httpx

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"   # fast + free tier
TIMEOUT_S    = 15


SYSTEM_PROMPT = """You are a nutrition claim auditor specialising in Indian food supplement regulations (FSSAI).

You will be given:
1. A list of marketing claims from a product page
2. The product's nutrition facts per 100g
3. The product category

Your job is to classify each claim and flag problematic ones.

Claim types:
- FACTUAL    : verifiable numeric claim consistent with nutrition label
- CERTIFIED  : references a legitimate certification (FSSAI, NSF, Informed Sport, Labdoor, ISO)
- COMPARATIVE: compares to a competitor or category ("best", "highest", "superior") — flag if no evidence
- EFFICACY   : claims a health outcome ("builds muscle", "burns fat", "boosts immunity") — flag if unsubstantiated
- VAGUE      : meaningless marketing language ("natural", "premium", "advanced formula")
- MISLEADING : technically true but creates a false impression

Return ONLY a JSON object in this exact format, no preamble, no markdown:
{
  "claim_classifications": [
    {
      "claim": "<original claim text>",
      "type": "<FACTUAL|CERTIFIED|COMPARATIVE|EFFICACY|VAGUE|MISLEADING>",
      "flagged": <true|false>,
      "severity": "<HIGH|MEDIUM|LOW|null>",
      "reason": "<one sentence explanation, or null if not flagged>"
    }
  ],
  "overall_assessment": "<one sentence summary of the product's claim integrity>"
}

Rules:
- Only flag claims where there is a genuine concern — do not over-flag
- EFFICACY claims are LOW severity unless they imply a medical outcome (fat burning, disease prevention)
- COMPARATIVE claims without any qualifier ("scientifically proven to be the best") are MEDIUM severity
- MISLEADING is reserved for claims that are technically true but designed to deceive
- If nutrition data is missing, do not flag claims that would require it to verify
"""


def _build_user_prompt(claims: list, nutrition_per_100g: dict, category: str) -> str:
    claims_formatted = "\n".join(
        f"- {c.get('text', c) if isinstance(c, dict) else c}"
        for c in claims[:30]  # cap at 30 to stay within context
    )
    nutrition_formatted = "\n".join(
        f"  {k}: {v}"
        for k, v in (nutrition_per_100g or {}).items()
        if v is not None
    )
    return f"""Product category: {category}

Marketing claims:
{claims_formatted}

Nutrition facts (per 100g):
{nutrition_formatted}

Classify each claim and flag any concerns."""


def analyse_claims_with_llm(
    claims: list,
    nutrition_per_100g: dict,
    category: str,
    groq_api_key: str,
) -> dict:
    """
    Analyse product claims using Groq LLM.

    Returns:
        {
            "claim_classifications": [...],
            "overall_assessment": "...",
            "llm_used": True,
            "model": "llama-3.1-8b-instant"
        }

    On any failure returns:
        {
            "claim_classifications": [],
            "overall_assessment": null,
            "llm_used": False,
            "error": "<reason>"
        }
    """
    if not groq_api_key:
        return {"claim_classifications": [], "overall_assessment": None,
                "llm_used": False, "error": "GROQ_API_KEY not configured"}

    if not claims:
        return {"claim_classifications": [], "overall_assessment": None,
                "llm_used": False, "error": "no claims to analyse"}

    try:
        response = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": _build_user_prompt(claims, nutrition_per_100g, category)},
                ],
                "temperature": 0.1,   # low temperature = consistent structured output
                "max_tokens":  1024,
            },
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()

        raw_text = response.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if model adds them despite instructions
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        parsed = json.loads(raw_text)

        return {
            **parsed,
            "llm_used": True,
            "model": GROQ_MODEL,
        }

    except httpx.TimeoutException:
        logger.warning("[llm_claims] Groq API timed out — falling back to rule-based only")
        return {"claim_classifications": [], "overall_assessment": None,
                "llm_used": False, "error": "Groq API timeout"}

    except httpx.HTTPStatusError as e:
        logger.warning(f"[llm_claims] Groq API error {e.response.status_code} — falling back")
        return {"claim_classifications": [], "overall_assessment": None,
                "llm_used": False, "error": f"Groq API HTTP {e.response.status_code}"}

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"[llm_claims] Failed to parse Groq response: {e}")
        return {"claim_classifications": [], "overall_assessment": None,
                "llm_used": False, "error": f"parse error: {e}"}

    except Exception as e:
        logger.exception(f"[llm_claims] Unexpected error: {e}")
        return {"claim_classifications": [], "overall_assessment": None,
                "llm_used": False, "error": str(e)}


def merge_llm_into_analysis(
    rule_contradictions: list,
    rule_vague:          list,
    llm_result:          dict,
) -> tuple[list, list, list, list]:
    """
    Merge rule-based and LLM results into unified claim lists.

    Returns: (contradictions, vague_claims, factual_claims, certified_claims)

    Rule-based results take precedence for contradictions — LLM adds new ones
    not caught by rules (efficacy, comparative, misleading).
    """
    contradictions   = list(rule_contradictions)
    vague_claims     = list(rule_vague)
    factual_claims   = []
    certified_claims = []

    if not llm_result.get("llm_used"):
        return contradictions, vague_claims, factual_claims, certified_claims

    # Track claims already flagged by rule engine to avoid duplicates
    rule_flagged_lower = {c["claim"].lower() for c in rule_contradictions}
    rule_vague_lower   = {v["claim"].lower() for v in rule_vague}

    for item in llm_result.get("claim_classifications", []):
        claim_text = item.get("claim", "")
        claim_lower = claim_text.lower()
        ctype      = item.get("type", "VAGUE")
        flagged    = item.get("flagged", False)
        severity   = item.get("severity")
        reason     = item.get("reason")

        if ctype == "FACTUAL":
            factual_claims.append({"claim": claim_text, "type": "FACTUAL",
                                   "confidence": 0.9, "reason": reason})

        elif ctype == "CERTIFIED":
            certified_claims.append({"claim": claim_text, "type": "CERTIFIED",
                                     "confidence": 0.9, "reason": reason})

        elif flagged and severity in ("HIGH", "MEDIUM", "LOW"):
            # New contradiction not caught by rules
            if claim_lower not in rule_flagged_lower:
                contradictions.append({
                    "claim":       claim_text,
                    "explanation": reason or f"LLM flagged as {ctype}",
                    "severity":    severity,
                    "citation":    None,
                    "source":      "llm",
                })

        elif ctype == "VAGUE" and claim_lower not in rule_vague_lower:
            vague_claims.append({"claim": claim_text,
                                 "reason": reason or "Vague marketing language"})

    return contradictions, vague_claims, factual_claims, certified_claims