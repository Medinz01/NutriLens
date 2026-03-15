from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ─── Inbound (from extension) ─────────────────────────────────────────────────

class NutritionFactsInput(BaseModel):
    energy_kcal:      Optional[float] = None
    protein_g:        Optional[float] = None
    total_fat_g:      Optional[float] = None
    saturated_fat_g:  Optional[float] = None
    trans_fat_g:      Optional[float] = None
    carbohydrates_g:  Optional[float] = None
    sugar_g:          Optional[float] = None
    dietary_fiber_g:  Optional[float] = None
    sodium_mg:        Optional[float] = None
    cholesterol_mg:   Optional[float] = None
    calcium_mg:       Optional[float] = None
    iron_mg:          Optional[float] = None


class ClaimInput(BaseModel):
    source: str   # "bullet" | "title" | "aplus_headline"
    text:   str


class ProductSubmitRequest(BaseModel):
    # Identity
    platform:     str
    platform_id:  str
    url:          str
    extracted_at: Optional[str] = None

    # Product info
    product_name: Optional[str] = None
    brand:        Optional[str] = None

    # Pricing & quantity
    price_inr:      Optional[float] = None
    quantity_g:     Optional[float] = None
    price_per_100g: Optional[float] = None

    # Nutrition
    serving_size_g:  Optional[float] = None
    nutrition_facts: Optional[NutritionFactsInput] = None

    # Claims
    claims:           Optional[list[ClaimInput]] = []
    claims_text:      Optional[str] = Field(None, max_length=5000)
    ingredients_text: Optional[str] = Field(None, max_length=2000)

    # FSSAI
    fssai: Optional[str] = None

    # Media
    primary_image_url: Optional[str] = None
    ocr_target_urls:   Optional[list[str]] = None
    total_images:      Optional[int] = None

    # Quality signals
    extraction_method:    Optional[str] = None
    nutrition_confidence: Optional[str] = None


# ─── Outbound (to extension) ──────────────────────────────────────────────────

class ClaimResult(BaseModel):
    claim: str
    type: str          # FACTUAL | CERTIFIED | VAGUE | MISLEADING
    confidence: Optional[float] = None
    reason: Optional[str] = None
    citation: Optional[str] = None


class ContradictionResult(BaseModel):
    claim: str
    explanation: str
    severity: str
    citation: Optional[str] = None


class AnalysisResult(BaseModel):
    factual_claims:   list[ClaimResult] = []
    certified_claims: list[ClaimResult] = []
    vague_claims:     list[ClaimResult] = []
    contradictions:   list[ContradictionResult] = []


class ScoreResult(BaseModel):
    value_score:     Optional[float] = None
    quality_score:   Optional[float] = None
    integrity_score: Optional[float] = None
    total:           Optional[float] = None
    category:        Optional[str]   = None
    value_nutrient:  Optional[str]   = None   # which nutrient drove the value score


class NutritionPer100g(BaseModel):
    energy_kcal:      Optional[float] = None
    protein_g:        Optional[float] = None
    total_fat_g:      Optional[float] = None
    saturated_fat_g:  Optional[float] = None
    trans_fat_g:      Optional[float] = None
    carbohydrates_g:  Optional[float] = None
    sugar_g:          Optional[float] = None
    dietary_fiber_g:  Optional[float] = None
    sodium_mg:        Optional[float] = None
    cholesterol_mg:   Optional[float] = None
    calcium_mg:       Optional[float] = None
    iron_mg:          Optional[float] = None


# Mirrors NutritionPer100g — all nutrients expressed per ₹100 spent on the pack.
# Which ones have meaningful values depends on category (e.g. cooking_oil uses energy_kcal).
class NutritionPerRs100(BaseModel):
    energy_kcal:      Optional[float] = None
    protein_g:        Optional[float] = None
    total_fat_g:      Optional[float] = None
    saturated_fat_g:  Optional[float] = None
    trans_fat_g:      Optional[float] = None
    carbohydrates_g:  Optional[float] = None
    sugar_g:          Optional[float] = None
    dietary_fiber_g:  Optional[float] = None
    sodium_mg:        Optional[float] = None
    cholesterol_mg:   Optional[float] = None
    calcium_mg:       Optional[float] = None
    iron_mg:          Optional[float] = None


class EnrichedProduct(BaseModel):
    platform_id:           str
    platform:              str
    url:                   str
    product_name:          Optional[str]   = None
    brand:                 Optional[str]   = None
    price_inr:             Optional[float] = None
    quantity_g:            Optional[float] = None
    price_per_100g:        Optional[float] = None
    serving_size_g:        Optional[float] = None
    nutrition_per_100g:    Optional[NutritionPer100g]  = None
    nutrition_per_rs100:   Optional[NutritionPerRs100] = None
    analysis:              Optional[AnalysisResult]    = None
    scores:                Optional[ScoreResult]       = None
    nutrition_confidence:  Optional[str]   = None
    extraction_method:     Optional[str]   = None
    status:                str = "ready"


# ─── Job / Polling ────────────────────────────────────────────────────────────

class SubmitResponse(BaseModel):
    cached:      bool
    job_id:      Optional[str]            = None
    data:        Optional[EnrichedProduct] = None
    eta_seconds: Optional[int]            = None


class JobStatusResponse(BaseModel):
    status:      str   # queued | processing | complete | failed
    eta_seconds: Optional[int]            = None
    data:        Optional[EnrichedProduct] = None
    error:       Optional[str]            = None


# ─── Rank ─────────────────────────────────────────────────────────────────────

class RankRequest(BaseModel):
    platform_ids: list[str]


class RankedProduct(BaseModel):
    platform_id:  str
    rank:         int
    score:        float
    product_name: Optional[str] = None


class RankResponse(BaseModel):
    ranked: list[RankedProduct]