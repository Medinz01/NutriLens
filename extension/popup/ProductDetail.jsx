/**
 * ProductDetail.jsx — NutriLens Single Product Audit View
 *
 * Shows full nutritional breakdown, claim-by-claim analysis,
 * contradiction details, and score breakdown.
 */

export default function ProductDetail({ product }) {
  const { analysis, scores, nutrition_per_100g: n100, nutrition_per_rs100: nr } = product;

  return (
    <div style={styles.container}>

      {/* Product header */}
      <div style={styles.productHeader}>
        <p style={styles.productName}>{product.product_name}</p>
        <p style={styles.brandName}>{product.brand}</p>
        <div style={styles.headerMeta}>
          {product.price_inr && (
            <span>₹{product.price_inr.toLocaleString("en-IN")}</span>
          )}
          {product.quantity_g && <span> · {product.quantity_g}g</span>}
        </div>
      </div>

      {/* Overall Score */}
      {scores && (
        <Section title="NutriScore">
          <div style={styles.scoreRow}>
            <ScoreBar label="Value (protein/₹)"   value={scores.value_score}   max={10} color="#16a34a" />
            <ScoreBar label="Nutritional quality"  value={scores.quality_score} max={10} color="#3b82f6" />
            <ScoreBar label="Label integrity"      value={scores.integrity_score} max={10} color="#8b5cf6" />
          </div>
          <div style={styles.totalScore}>
            Total: <strong>{scores.total?.toFixed(1)} / 10</strong>
          </div>
        </Section>
      )}

      {/* Nutritional Facts per 100g */}
      {n100 && (
        <Section title="Nutrition per 100g">
          <div style={styles.nutriGrid}>
            {Object.entries(n100).map(([key, value]) => (
              <NutrientRow key={key} label={formatKey(key)} value={value} unit={getUnit(key)} />
            ))}
          </div>
          {nr?.protein_g && (
            <div style={styles.valueMetric}>
              <span style={styles.valueLabel}>Protein per ₹100 spent</span>
              <span style={styles.valueNumber}>{nr.protein_g.toFixed(1)}g</span>
            </div>
          )}
        </Section>
      )}

      {/* Claim Analysis */}
      {analysis && (
        <Section title="Claim Analysis">

          {/* Contradictions */}
          {analysis.contradictions?.length > 0 && (
            <div style={styles.claimGroup}>
              <p style={styles.claimGroupTitle}>
                <span style={styles.dotRed} /> Contradictions ({analysis.contradictions.length})
              </p>
              {analysis.contradictions.map((c, i) => (
                <div key={i} style={styles.contradictionCard}>
                  <p style={styles.contradictionClaim}>"{c.claim}"</p>
                  <p style={styles.contradictionExplanation}>{c.explanation}</p>
                  {c.citation && (
                    <a
                      href={c.citation}
                      target="_blank"
                      rel="noreferrer"
                      style={styles.citation}
                    >
                      FSSAI rule →
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Vague claims */}
          {analysis.vague_claims?.length > 0 && (
            <div style={styles.claimGroup}>
              <p style={styles.claimGroupTitle}>
                <span style={styles.dotYellow} /> Vague / Unverifiable ({analysis.vague_claims.length})
              </p>
              {analysis.vague_claims.map((c, i) => (
                <div key={i} style={styles.vagueCard}>
                  <span style={styles.vagueClaim}>"{c.claim}"</span>
                  <span style={styles.vagueReason}>{c.reason}</span>
                </div>
              ))}
            </div>
          )}

          {/* Clean claims */}
          {analysis.factual_claims?.length > 0 && (
            <div style={styles.claimGroup}>
              <p style={styles.claimGroupTitle}>
                <span style={styles.dotGreen} /> Verified claims ({analysis.factual_claims.length})
              </p>
              {analysis.factual_claims.map((c, i) => (
                <div key={i} style={styles.factualCard}>
                  <span style={styles.factualClaim}>✓ "{c.claim}"</span>
                </div>
              ))}
            </div>
          )}

          {analysis.contradictions?.length === 0 &&
           analysis.vague_claims?.length === 0 && (
            <div style={styles.cleanLabel}>
              ✓ No contradictions or misleading claims detected.
            </div>
          )}
        </Section>
      )}

      {/* Data quality note */}
      <div style={styles.dataNote}>
        <p>
          Data extracted from product page · Confidence:{" "}
          <strong>{product.nutrition_confidence || "unknown"}</strong>
        </p>
        {product.extraction_method === "text_fallback" && (
          <p style={{ color: "#f59e0b" }}>
            ⚠ Nutrition data extracted from text — may be less accurate than table data.
          </p>
        )}
        <p>Not medical advice. Verify important decisions with a registered dietitian.</p>
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Section({ title, children }) {
  return (
    <div style={styles.section}>
      <p style={styles.sectionTitle}>{title}</p>
      {children}
    </div>
  );
}

function ScoreBar({ label, value, max = 10, color }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div style={styles.scoreBarRow}>
      <span style={styles.scoreBarLabel}>{label}</span>
      <div style={styles.scoreBarTrack}>
        <div style={{ ...styles.scoreBarFill, width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span style={styles.scoreBarValue}>{value?.toFixed(1)}</span>
    </div>
  );
}

function NutrientRow({ label, value, unit }) {
  return (
    <div style={styles.nutriRow}>
      <span style={styles.nutriLabel}>{label}</span>
      <span style={styles.nutriValue}>{typeof value === "number" ? `${value.toFixed(1)}${unit}` : "—"}</span>
    </div>
  );
}

// ─── Formatters ───────────────────────────────────────────────────────────────

function formatKey(key) {
  const labels = {
    energy_kcal:      "Energy",
    protein_g:        "Protein",
    total_fat_g:      "Total Fat",
    saturated_fat_g:  "Saturated Fat",
    carbohydrates_g:  "Carbohydrates",
    sugar_g:          "Sugar",
    dietary_fiber_g:  "Dietary Fiber",
    sodium_mg:        "Sodium",
    cholesterol_mg:   "Cholesterol",
    calcium_mg:       "Calcium",
    iron_mg:          "Iron",
  };
  return labels[key] || key.replace(/_/g, " ");
}

function getUnit(key) {
  if (key.endsWith("_kcal")) return " kcal";
  if (key.endsWith("_mg"))   return " mg";
  return "g";
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
  },
  productHeader: {
    padding: "12px 16px",
    borderBottom: "1px solid #f0f0f0",
    backgroundColor: "#f9fafb",
  },
  productName: {
    margin: 0,
    fontWeight: 700,
    fontSize: 13,
    color: "#111827",
    lineHeight: 1.4,
  },
  brandName: {
    margin: "2px 0 0",
    fontSize: 12,
    color: "#6b7280",
  },
  headerMeta: {
    marginTop: 4,
    fontSize: 12,
    color: "#374151",
    fontWeight: 600,
  },
  section: {
    padding: "12px 16px",
    borderBottom: "1px solid #f0f0f0",
  },
  sectionTitle: {
    margin: "0 0 8px",
    fontSize: 11,
    fontWeight: 700,
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
  },
  scoreRow:  { display: "flex", flexDirection: "column", gap: 8 },
  scoreBarRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  scoreBarLabel: { fontSize: 11, color: "#374151", width: 130, flexShrink: 0 },
  scoreBarTrack: {
    flex: 1,
    height: 6,
    backgroundColor: "#e5e7eb",
    borderRadius: 3,
    overflow: "hidden",
  },
  scoreBarFill:  { height: "100%", borderRadius: 3, transition: "width 0.3s" },
  scoreBarValue: { fontSize: 11, fontWeight: 700, color: "#374151", width: 28, textAlign: "right" },
  totalScore: {
    marginTop: 10,
    fontSize: 13,
    color: "#374151",
    textAlign: "right",
  },
  nutriGrid: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  nutriRow: {
    display: "flex",
    justifyContent: "space-between",
    padding: "3px 0",
    borderBottom: "1px solid #f9fafb",
  },
  nutriLabel: { fontSize: 12, color: "#374151" },
  nutriValue: { fontSize: 12, fontWeight: 600, color: "#111827" },
  valueMetric: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 10,
    padding: "8px 10px",
    backgroundColor: "#f0fdf4",
    borderRadius: 6,
  },
  valueLabel:  { fontSize: 11, color: "#16a34a", fontWeight: 600 },
  valueNumber: { fontSize: 15, fontWeight: 700, color: "#16a34a" },
  claimGroup:  { marginBottom: 12 },
  claimGroupTitle: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    margin: "0 0 6px",
    fontSize: 11,
    fontWeight: 700,
    color: "#374151",
  },
  dotRed:    { width: 8, height: 8, borderRadius: "50%", backgroundColor: "#dc2626", display: "inline-block" },
  dotYellow: { width: 8, height: 8, borderRadius: "50%", backgroundColor: "#f59e0b", display: "inline-block" },
  dotGreen:  { width: 8, height: 8, borderRadius: "50%", backgroundColor: "#16a34a", display: "inline-block" },
  contradictionCard: {
    backgroundColor: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: 6,
    padding: "8px 10px",
    marginBottom: 6,
  },
  contradictionClaim:       { margin: "0 0 4px", fontWeight: 600, fontSize: 12, color: "#991b1b" },
  contradictionExplanation: { margin: 0, fontSize: 11, color: "#374151", lineHeight: 1.4 },
  citation: { display: "block", marginTop: 4, fontSize: 10, color: "#6b7280" },
  vagueCard: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    padding: "6px 10px",
    backgroundColor: "#fffbeb",
    border: "1px solid #fde68a",
    borderRadius: 6,
    marginBottom: 4,
  },
  vagueClaim:  { fontSize: 12, fontWeight: 600, color: "#92400e" },
  vagueReason: { fontSize: 11, color: "#6b7280" },
  factualCard: { padding: "4px 0" },
  factualClaim: { fontSize: 12, color: "#16a34a", fontWeight: 500 },
  cleanLabel: {
    padding: 10,
    backgroundColor: "#f0fdf4",
    borderRadius: 6,
    fontSize: 12,
    color: "#16a34a",
    fontWeight: 600,
  },
  dataNote: {
    padding: "10px 16px",
    fontSize: 10,
    color: "#9ca3af",
    lineHeight: 1.6,
    borderTop: "1px solid #f0f0f0",
    backgroundColor: "#f9fafb",
  },
};