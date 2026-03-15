"""
Unit tests for engines/ranker.py - Accountability Score Engine

Tests cover:
- value_score: protein per Rs100 vs category benchmark
- quality_score: nutritional composition thresholds
- integrity_score: FSSAI compliance, contradiction deductions
- total: weighted score capped 0-10
"""

import pytest
import sys
import os

# Add engines to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engines.ranker import compute_score, BENCHMARKS


class TestValueScore:
    """Tests for value_score (protein per Rs100)"""

    def test_value_score_high_protein_exceeds_median(self):
        """High protein per Rs100 should give high value score"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0},
            nutrition_per_rs100={"protein_g": 52.0},  # 2x median for protein_powder (26)
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        # 52/26 * 5 = 10 (capped)
        assert result["value_score"] == 10.0

    def test_value_score_exactly_median(self):
        """Exactly median protein should give 5.0"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0},
            nutrition_per_rs100={"protein_g": 26.0},  # exactly median
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        assert result["value_score"] == 5.0

    def test_value_score_half_median(self):
        """Half median protein should give 2.5"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0},
            nutrition_per_rs100={"protein_g": 13.0},  # half median
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        assert result["value_score"] == 2.5

    def test_value_score_no_price_data(self):
        """No price data should default to 5.0"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0},
            nutrition_per_rs100={},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        assert result["value_score"] == 5.0


class TestQualityScore:
    """Tests for quality_score (nutritional composition)"""

    def test_quality_score_high_protein(self):
        """High protein should add +2.0"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0, "sugar_g": 1.0},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        # 6.5 + 2.0 (high protein) = 8.5
        assert result["quality_score"] == 8.5

    def test_quality_score_ok_protein(self):
        """OK protein should add +1.0"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 60.0, "sugar_g": 1.0},  # between ok (55) and good (70)
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        # 6.5 + 1.0 (ok protein) = 7.5
        assert result["quality_score"] == 7.5

    def test_quality_score_high_sugar(self):
        """High sugar should deduct -2.5"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 50.0, "sugar_g": 10.0},  # > 5.0 threshold
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        # 6.5 - 2.5 (high sugar) = 4.0
        assert result["quality_score"] == 4.0

    def test_quality_score_ok_sugar(self):
        """OK sugar should deduct -1.0"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 50.0, "sugar_g": 3.0},  # between ok (2) and high (5)
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        # 6.5 - 1.0 (ok sugar) = 5.5
        assert result["quality_score"] == 5.5

    def test_quality_score_sodium_high(self):
        """Sodium >500 should deduct -1.0 (plus >300 gives additional -0.5)"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 75.0, "sugar_g": 1.0, "sodium_mg": 600},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        # 6.5 + 2.0 (high protein) - 1.0 (sodium >500) - 0.5 (sodium >300) = 7.0
        assert result["quality_score"] == 7.0

    def test_quality_score_sodium_medium(self):
        """Sodium >300 should deduct -0.5"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 50.0, "sugar_g": 1.0, "sodium_mg": 400},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
        )
        # 6.5 - 0.5 (sodium >300) = 6.0
        assert result["quality_score"] == 6.0


class TestIntegrityScore:
    """Tests for integrity_score (FSSAI, contradictions)

    energy_kcal=320 = protein_g(80) * 4 kcal/g — consistent with macro
    calculation so the energy cross-check does not fire in these tests.
    Tests that DO want to verify the energy check are in TestEnergyCheck.
    """

    def test_integrity_score_no_fssai(self):
        """Missing FSSAI should deduct -3.0"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0, "energy_kcal": 320},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
            fssai=None,
        )
        # 10.0 - 3.0 = 7.0
        assert result["integrity_score"] == 7.0

    def test_integrity_score_with_fssai(self):
        """FSSAI present should keep full score"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0, "energy_kcal": 320},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        assert result["integrity_score"] == 10.0

    def test_integrity_score_contradiction_high(self):
        """HIGH severity contradiction should deduct -2.5"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0, "energy_kcal": 320},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[{"severity": "HIGH"}],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        # 10.0 - 2.5 = 7.5
        assert result["integrity_score"] == 7.5

    def test_integrity_score_contradiction_medium(self):
        """MEDIUM severity contradiction should deduct -1.5"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0, "energy_kcal": 320},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[{"severity": "MEDIUM"}],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        # 10.0 - 1.5 = 8.5
        assert result["integrity_score"] == 8.5

    def test_integrity_score_contradiction_low(self):
        """LOW severity contradiction should deduct -0.5"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0, "energy_kcal": 320},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[{"severity": "LOW"}],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        # 10.0 - 0.5 = 9.5
        assert result["integrity_score"] == 9.5

    def test_integrity_score_multiple_contradictions(self):
        """Multiple HIGH contradictions each deduct 2.5"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0, "energy_kcal": 320},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[{"severity": "HIGH"}, {"severity": "HIGH"}],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        # 10.0 - (2 * 2.5) = 5.0
        assert result["integrity_score"] == 5.0

    def test_integrity_score_vague_claims(self):
        """Vague claims should deduct -0.2 each"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 80.0, "energy_kcal": 320},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[{}, {}, {}, {}, {}],  # 5 vague claims
            category="protein_powder",
            fssai="11223344556677",
        )
        # 10.0 - (5 * 0.2) = 9.0
        assert result["integrity_score"] == 9.0


class TestEnergyCheck:
    """Tests for Codex s3.3.1 energy cross-verification"""

    def test_energy_check_accurate_label_no_penalty(self):
        """Accurate energy declaration should not trigger penalty"""
        result = compute_score(
            # protein=70*4=280, carbs=21.2*4=84.8, fat=3.25*9=29.25 → 394 kcal
            nutrition_per_100g={"protein_g": 70.0, "carbohydrates_g": 21.2,
                                "total_fat_g": 3.25, "energy_kcal": 394},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        assert result["integrity_score"] == 10.0
        assert not any("mismatch" in n for n in result["integrity_notes"])

    def test_energy_check_inaccurate_label_deducts_1(self):
        """Energy >10% off from macro calculation should deduct -1.0"""
        result = compute_score(
            # macros give ~394 kcal but label declares 500
            nutrition_per_100g={"protein_g": 70.0, "carbohydrates_g": 21.2,
                                "total_fat_g": 3.25, "energy_kcal": 500},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        assert result["integrity_score"] == 9.0
        assert any("mismatch" in n for n in result["integrity_notes"])

    def test_energy_check_no_declared_kcal_skipped(self):
        """Missing energy_kcal should skip the check silently"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 70.0, "carbohydrates_g": 21.2, "total_fat_g": 3.25},
            nutrition_per_rs100={"protein_g": 26.0},
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        assert result["integrity_score"] == 10.0


class TestTotalScore:
    """Tests for total score (weighted sum capped 0-10)"""

    def test_total_score_calculation(self):
        """Total should be weighted sum: value*0.35 + quality*0.30 + integrity*0.35"""
        result = compute_score(
            # energy_kcal=320 = protein(80)*4, no carbs/fat so cross-check won't fire
            nutrition_per_100g={"protein_g": 80.0, "energy_kcal": 320, "sugar_g": 1.0},
            nutrition_per_rs100={"protein_g": 26.0},  # exactly median -> 5.0 value
            contradictions=[],
            vague_claims=[],
            category="protein_powder",
            fssai="11223344556677",
        )
        # value: 5.0, quality: 8.5 (high protein), integrity: 10.0
        # total = 5.0*0.35 + 8.5*0.30 + 10.0*0.35 = 1.75 + 2.55 + 3.5 = 7.8
        assert result["total"] == 7.8

    def test_total_score_capped_at_zero(self):
        """Total should not go below 0"""
        result = compute_score(
            nutrition_per_100g={"protein_g": 1.0, "sugar_g": 50.0, "sodium_mg": 1000},
            nutrition_per_rs100={"protein_g": 0.1},
            contradictions=[{"severity": "HIGH"}, {"severity": "HIGH"}, {"severity": "HIGH"}],
            vague_claims=[],
            category="protein_powder",
            fssai=None,
        )
        assert result["total"] >= 0.0


class TestCategoryBenchmarks:
    """Tests for category-specific benchmarks"""

    def test_health_bar_benchmark(self):
        """Health bar category should have different benchmark"""
        bench = BENCHMARKS["health_bar"]
        assert bench["protein_per_rs100_median"] == 8.0

    def test_breakfast_cereal_benchmark(self):
        """Breakfast cereal category should have different benchmark"""
        bench = BENCHMARKS["breakfast_cereal"]
        assert bench["protein_per_rs100_median"] == 4.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])