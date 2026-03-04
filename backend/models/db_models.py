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
    misleading  = "MISLEADING"  # set by contradiction engine, not classifier


class JobStatus(str, enum.Enum):
    queued     = "queued"
    processing = "processing"
    complete   = "complete"
    failed     = "failed"


# ─── Products ────────────────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id                = Column(String, primary_key=True)  # "{platform}:{platform_id}"
    platform_id       = Column(String, nullable=False, index=True)
    platform_name     = Column(String, nullable=False)
    product_name      = Column(String)
    brand             = Column(String)
    url               = Column(Text)
    primary_image_url = Column(Text)
    created_at        = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_extracted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    nutrition_facts = relationship("NutritionFacts", back_populates="product", uselist=False,
                                   cascade="all, delete-orphan")
    extracted_claims = relationship("ExtractedClaim", back_populates="product",
                                    cascade="all, delete-orphan")
    contradictions  = relationship("Contradiction", back_populates="product",
                                   cascade="all, delete-orphan")
    scores          = relationship("ProductScore", back_populates="product", uselist=False,
                                   cascade="all, delete-orphan")


class NutritionFacts(Base):
    __tablename__ = "nutrition_facts"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    product_id      = Column(String, ForeignKey("products.id", ondelete="CASCADE"), unique=True)

    # Pricing
    price_inr       = Column(Float)
    quantity_g      = Column(Float)
    price_per_100g  = Column(Float)

    # Per serving (as listed)
    serving_size_g  = Column(Float)

    # Per 100g (normalized — primary comparison unit)
    energy_kcal     = Column(Float)
    protein_g       = Column(Float)
    total_fat_g     = Column(Float)
    saturated_fat_g = Column(Float)
    carbohydrates_g = Column(Float)
    sugar_g         = Column(Float)
    dietary_fiber_g = Column(Float)
    sodium_mg       = Column(Float)
    cholesterol_mg  = Column(Float)
    calcium_mg      = Column(Float)
    iron_mg         = Column(Float)

    # Per ₹100 (value metric)
    protein_per_rs100    = Column(Float)
    energy_per_rs100     = Column(Float)

    # Data quality
    source           = Column(SAEnum(ExtractionSource), default=ExtractionSource.extension_dom)
    confidence       = Column(Float, default=0.5)   # 0.0–1.0
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
    rule_id      = Column(String)           # FK to fssai_rules.id
    severity     = Column(String)           # HIGH / MEDIUM / LOW
    explanation  = Column(Text)
    citation_url = Column(Text)

    product = relationship("Product", back_populates="contradictions")


class ProductScore(Base):
    __tablename__ = "product_scores"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    product_id      = Column(String, ForeignKey("products.id", ondelete="CASCADE"), unique=True)
    category        = Column(String)           # protein_powder, health_bar, etc.
    value_score     = Column(Float)            # protein/₹
    quality_score   = Column(Float)            # nutritional quality
    integrity_score = Column(Float)            # label integrity
    total           = Column(Float)            # weighted sum 0–10
    computed_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="scores")


class ClaimVerification(Base):
    """Stores per-claim numeric verification results from ranker.py."""
    __tablename__ = "claim_verifications"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    product_id  = Column(String, ForeignKey("products.id", ondelete="CASCADE"), index=True)
    claim_text  = Column(Text, nullable=False)
    nutrient    = Column(String)            # protein_g, sugar_g, etc.
    claimed_val = Column(Float)
    actual_val  = Column(Float)
    unit        = Column(String)
    verdict     = Column(String)            # verified | contradicted | unverifiable
    explanation = Column(Text)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ─── Async Jobs ───────────────────────────────────────────────────────────────

class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id          = Column(String, primary_key=True)   # UUID
    product_id  = Column(String, index=True)
    status      = Column(SAEnum(JobStatus), default=JobStatus.queued)
    eta_seconds = Column(Integer, default=10)
    error       = Column(Text)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))