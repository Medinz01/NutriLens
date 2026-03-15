from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer, Boolean,
    DateTime, ForeignKey, Text, Enum as SAEnum, ARRAY
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class ExtractionSource(str, enum.Enum):
    extension_dom   = "extension_dom"
    ocr_verified    = "ocr_verified"
    manual_verified = "manual_verified"
    open_food_facts = "open_food_facts"


class ClaimType(str, enum.Enum):
    factual     = "FACTUAL"
    certified   = "CERTIFIED"
    vague       = "VAGUE"
    misleading  = "MISLEADING"


class JobStatus(str, enum.Enum):
    queued     = "queued"
    processing = "processing"
    complete   = "complete"
    failed     = "failed"


# ─── Products ─────────────────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id                = Column(String, primary_key=True)
    platform_id       = Column(String, nullable=False, index=True)
    platform_name     = Column(String, nullable=False)
    product_name      = Column(String)
    brand             = Column(String)
    url               = Column(Text)
    primary_image_url = Column(Text)
    created_at        = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_extracted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    nutrition_facts  = relationship("NutritionFacts", back_populates="product", uselist=False,
                                    cascade="all, delete-orphan")
    extracted_claims = relationship("ExtractedClaim", back_populates="product",
                                    cascade="all, delete-orphan")
    contradictions   = relationship("Contradiction", back_populates="product",
                                    cascade="all, delete-orphan")
    scores           = relationship("ProductScore", back_populates="product", uselist=False,
                                    cascade="all, delete-orphan")


class NutritionFacts(Base):
    __tablename__ = "nutrition_facts"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    product_id     = Column(String, ForeignKey("products.id", ondelete="CASCADE"), unique=True)

    # Pricing
    price_inr      = Column(Float)
    quantity_g     = Column(Float)
    price_per_100g = Column(Float)

    # Per serving (as listed)
    serving_size_g = Column(Float)

    # Per 100g (normalized — primary comparison unit)
    energy_kcal     = Column(Float)
    protein_g       = Column(Float)
    total_fat_g     = Column(Float)
    saturated_fat_g = Column(Float)
    trans_fat_g     = Column(Float)
    carbohydrates_g = Column(Float)
    sugar_g         = Column(Float)
    dietary_fiber_g = Column(Float)
    sodium_mg       = Column(Float)
    cholesterol_mg  = Column(Float)
    calcium_mg      = Column(Float)
    iron_mg         = Column(Float)

    # Per ₹100 — all nutrients, keyed by nutrient name.
    # Which fields are meaningful depends on category (e.g. cooking_oil uses energy_kcal).
    per_rs100_json  = Column(JSONB, default=dict)

    # Data quality
    source           = Column(SAEnum(ExtractionSource), default=ExtractionSource.extension_dom)
    confidence       = Column(Float, default=0.5)
    extraction_notes = Column(Text)

    product = relationship("Product", back_populates="nutrition_facts")


class ExtractedClaim(Base):
    __tablename__ = "extracted_claims"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    product_id          = Column(String, ForeignKey("products.id", ondelete="CASCADE"))
    raw_text            = Column(Text, nullable=False)
    classification_type = Column(SAEnum(ClaimType))
    confidence_score    = Column(Float)
    model_version       = Column(String, default="v0-rule-based")
    created_at          = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="extracted_claims")


class Contradiction(Base):
    __tablename__ = "contradictions"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    product_id   = Column(String, ForeignKey("products.id", ondelete="CASCADE"))
    claim_text   = Column(Text)
    rule_id      = Column(String)
    severity     = Column(String)
    explanation  = Column(Text)
    citation_url = Column(Text)

    product = relationship("Product", back_populates="contradictions")


class ProductScore(Base):
    __tablename__ = "product_scores"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    product_id      = Column(String, ForeignKey("products.id", ondelete="CASCADE"), unique=True)
    category        = Column(String)
    value_nutrient  = Column(String)   # which nutrient drove the value score (e.g. protein_g)
    value_score     = Column(Float)
    quality_score   = Column(Float)
    integrity_score = Column(Float)
    total           = Column(Float)
    computed_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="scores")


class ClaimVerification(Base):
    __tablename__ = "claim_verifications"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    product_id  = Column(String, ForeignKey("products.id", ondelete="CASCADE"), index=True)
    claim_text  = Column(Text, nullable=False)
    nutrient    = Column(String)
    claimed_val = Column(Float)
    actual_val  = Column(Float)
    unit        = Column(String)
    verdict     = Column(String)
    explanation = Column(Text)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ─── Async Jobs ───────────────────────────────────────────────────────────────

class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id          = Column(String, primary_key=True)
    product_id  = Column(String, index=True)
    status      = Column(SAEnum(JobStatus), default=JobStatus.queued)
    eta_seconds = Column(Integer, default=10)
    error       = Column(Text)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))