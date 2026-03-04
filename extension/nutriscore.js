/**
 * nutriscore.js — NutriScore A–E calculator
 *
 * Based on the European NutriScore algorithm adapted for Indian serving sizes.
 * Scores per 100g, grades A (best) to E (worst).
 */

// ─── Negative points (higher = worse) ────────────────────────────────────────

function energyPoints(kcal) {
  if (kcal <= 80)   return 0;
  if (kcal <= 160)  return 1;
  if (kcal <= 240)  return 2;
  if (kcal <= 320)  return 3;
  if (kcal <= 400)  return 4;
  if (kcal <= 480)  return 5;
  if (kcal <= 560)  return 6;
  if (kcal <= 640)  return 7;
  if (kcal <= 720)  return 8;
  if (kcal <= 800)  return 9;
  return 10;
}

function satFatPoints(g) {
  if (g <= 1)   return 0;
  if (g <= 2)   return 1;
  if (g <= 3)   return 2;
  if (g <= 4)   return 3;
  if (g <= 5)   return 4;
  if (g <= 6)   return 5;
  if (g <= 7)   return 6;
  if (g <= 8)   return 7;
  if (g <= 9)   return 8;
  if (g <= 10)  return 9;
  return 10;
}

function sugarPoints(g) {
  if (g <= 4.5)  return 0;
  if (g <= 9)    return 1;
  if (g <= 13.5) return 2;
  if (g <= 18)   return 3;
  if (g <= 22.5) return 4;
  if (g <= 27)   return 5;
  if (g <= 31)   return 6;
  if (g <= 36)   return 7;
  if (g <= 40)   return 8;
  if (g <= 45)   return 9;
  return 10;
}

function sodiumPoints(mg) {
  // sodium → salt: mg * 2.5 / 1000
  const salt_g_per_100 = (mg * 2.5) / 1000;
  if (salt_g_per_100 <= 0.2)  return 0;
  if (salt_g_per_100 <= 0.4)  return 1;
  if (salt_g_per_100 <= 0.6)  return 2;
  if (salt_g_per_100 <= 0.8)  return 3;
  if (salt_g_per_100 <= 1.0)  return 4;
  if (salt_g_per_100 <= 1.2)  return 5;
  if (salt_g_per_100 <= 1.4)  return 6;
  if (salt_g_per_100 <= 1.6)  return 7;
  if (salt_g_per_100 <= 1.8)  return 8;
  if (salt_g_per_100 <= 2.0)  return 9;
  return 10;
}

// ─── Positive points (higher = better) ───────────────────────────────────────

function proteinPoints(g) {
  if (g <= 1.6)  return 0;
  if (g <= 3.2)  return 1;
  if (g <= 4.8)  return 2;
  if (g <= 6.4)  return 3;
  if (g <= 8.0)  return 4;
  return 5;
}

function fiberPoints(g) {
  if (g <= 0.9)  return 0;
  if (g <= 1.9)  return 1;
  if (g <= 2.8)  return 2;
  if (g <= 3.7)  return 3;
  if (g <= 4.7)  return 4;
  return 5;
}

// ─── Main calculation ─────────────────────────────────────────────────────────

/**
 * Calculate NutriScore from per-100g nutrition values.
 *
 * @param {object} nutrition  — keys: energy_kcal, saturated_fat_g, sugar_g,
 *                              sodium_mg, protein_g, dietary_fiber_g
 * @param {number} servingSize — serving size in grams (to normalise per-serving → per-100g)
 * @returns {{ grade: string, score: number, breakdown: object }}
 */
export function calcNutriScore(nutrition, servingSize) {
  // Normalise to per-100g if we have per-serving values
  const factor = servingSize ? (100 / servingSize) : 1;

  const energy   = (nutrition.energy_kcal      || 0) * factor;
  const satFat   = (nutrition.saturated_fat_g  || 0) * factor;
  const sugar    = (nutrition.sugar_g          || 0) * factor;
  const sodium   = (nutrition.sodium_mg        || 0) * factor;
  const protein  = (nutrition.protein_g        || 0) * factor;
  const fiber    = (nutrition.dietary_fiber_g  || 0) * factor;

  const negative =
    energyPoints(energy) +
    satFatPoints(satFat) +
    sugarPoints(sugar) +
    sodiumPoints(sodium);

  const positive = proteinPoints(protein) + fiberPoints(fiber);

  // If negative score >= 11, protein points are not counted
  const score = negative >= 11
    ? negative - fiberPoints(fiber)
    : negative - positive;

  const grade =
    score <= -1 ? "A" :
    score <=  2 ? "B" :
    score <= 10 ? "C" :
    score <= 18 ? "D" : "E";

  return {
    grade,
    score,
    breakdown: { energy, satFat, sugar, sodium, protein, fiber, negative, positive },
  };
}

// Grade colours for UI
export const GRADE_COLORS = {
  A: { bg: "#00843b", text: "#fff" },
  B: { bg: "#85bb2f", text: "#fff" },
  C: { bg: "#fecb02", text: "#000" },
  D: { bg: "#ee8100", text: "#fff" },
  E: { bg: "#e63312", text: "#fff" },
};
