/**
 * normalizer.js — NutriLens Data Normalization
 *
 * All scoring and comparison must happen on normalized values.
 * This module converts raw extracted values to per-100g and per-₹100 metrics.
 */

// ─── Nutrient Normalization ──────────────────────────────────────────────────

/**
 * Normalize nutrition facts from per-serving to per-100g.
 * This is the canonical unit for all comparisons.
 *
 * @param {Object} facts         - Raw nutrition facts (per serving)
 * @param {number} servingSizeG  - Serving size in grams
 * @returns {Object}             - Nutrition facts per 100g
 */
export function normalizePer100g(facts, servingSizeG) {
  if (!facts || !servingSizeG || servingSizeG <= 0) return null;

  const factor = 100 / servingSizeG;
  const normalized = {};

  for (const [key, value] of Object.entries(facts)) {
    if (typeof value === "number") {
      normalized[key] = parseFloat((value * factor).toFixed(2));
    }
  }

  return normalized;
}

/**
 * Compute nutrient values per ₹100 spent.
 * The primary value metric for comparison.
 *
 * @param {Object} facts100g     - Nutrition facts per 100g
 * @param {number} pricePer100g  - Price in INR per 100g
 * @returns {Object}             - Nutrition facts per ₹100
 */
export function normalizePer100Rupees(facts100g, pricePer100g) {
  if (!facts100g || !pricePer100g || pricePer100g <= 0) return null;

  const factor = 100 / pricePer100g;
  const normalized = {};

  for (const [key, value] of Object.entries(facts100g)) {
    if (typeof value === "number") {
      normalized[key] = parseFloat((value * factor).toFixed(2));
    }
  }

  return normalized;
}

/**
 * Compute price per 100g from total price and total quantity.
 */
export function computePricePer100g(priceInr, quantityG) {
  if (!priceInr || !quantityG || quantityG <= 0) return null;
  return parseFloat(((priceInr / quantityG) * 100).toFixed(2));
}

// ─── Product Summary ─────────────────────────────────────────────────────────

/**
 * Build a complete normalized product summary ready for comparison.
 * This is what gets stored and displayed in the popup.
 */
export function buildNormalizedProduct(raw) {
  const {
    product_name,
    brand,
    price_inr,
    quantity_g,
    serving_size_g,
    nutrition_facts,
    platform_id,
    platform,
    url,
    nutrition_confidence,
  } = raw;

  const pricePer100g = computePricePer100g(price_inr, quantity_g);
  const per100g = normalizePer100g(nutrition_facts, serving_size_g);
  const perRs100 = (per100g && pricePer100g)
    ? normalizePer100Rupees(per100g, pricePer100g)
    : null;

  return {
    platform_id,
    platform,
    url,
    product_name,
    brand,
    price_inr,
    quantity_g,
    serving_size_g,
    price_per_100g: pricePer100g,
    nutrition_per_serving: nutrition_facts,
    nutrition_per_100g: per100g,
    nutrition_per_rs100: perRs100,
    nutrition_confidence,
  };
}

// ─── Category Benchmarks ─────────────────────────────────────────────────────
// Used to contextualize scores: "top X% in category"

export const CATEGORY_BENCHMARKS = {
  protein_powder: {
    protein_per_rs100:     { p25: 20, p50: 26, p75: 32, p90: 38 },
    sugar_per_100g:        { good: 2, acceptable: 5, high: 10 },
    protein_per_100g:      { good: 70, acceptable: 60, low: 50 },
  },
  health_bar: {
    protein_per_rs100:     { p25: 5, p50: 8, p75: 12, p90: 16 },
    sugar_per_100g:        { good: 10, acceptable: 20, high: 35 },
  },
  breakfast_cereal: {
    sugar_per_100g:        { good: 5, acceptable: 15, high: 25 },
    fiber_per_100g:        { good: 6, acceptable: 3, low: 1 },
  },
};

/**
 * Determine which percentile a value falls into for a given metric/category.
 * Returns: "top" | "good" | "average" | "below_average"
 */
export function getPercentileTier(category, metric, value) {
  const benchmarks = CATEGORY_BENCHMARKS[category]?.[metric];
  if (!benchmarks) return null;

  if (benchmarks.p90 && value >= benchmarks.p90) return "top";
  if (benchmarks.p75 && value >= benchmarks.p75) return "good";
  if (benchmarks.p50 && value >= benchmarks.p50) return "average";
  return "below_average";
}

// ─── Display Formatting ──────────────────────────────────────────────────────

export function formatPrice(inr) {
  if (!inr) return "—";
  return `₹${inr.toLocaleString("en-IN")}`;
}

export function formatNutrient(value, unit = "g") {
  if (value === null || value === undefined) return "—";
  return `${parseFloat(value.toFixed(1))}${unit}`;
}