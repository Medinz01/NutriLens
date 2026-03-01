/**
 * CompareTable.jsx — NutriLens Product Comparison Table
 *
 * Shows all products in the comparison set.
 * Primary metric: protein per ₹100 (or relevant metric per category)
 * Highlights winner, flags issues, shows processing states.
 */

import { formatPrice, formatNutrient } from "../utils/normalizer.js";

// ─── Status Badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status, error }) {
  if (status === "ready") return null;
  const map = {
    processing: { text: "Analyzing...", color: "#f59e0b", bg: "#fffbeb" },
    failed:     { text: "Failed",       color: "#dc2626", bg: "#fef2f2" },
    queued:     { text: "Queued",       color: "#6b7280", bg: "#f9fafb" },
  };
  const s = map[status] || map.queued;
  return (
    <span style={{ fontSize: 10, color: s.color, backgroundColor: s.bg,
      padding: "2px 6px", borderRadius: 10, fontWeight: 600 }}>
      {s.text}
    </span>
  );
}

// ─── Score Badge ──────────────────────────────────────────────────────────────

function ScoreBadge({ score, rank }) {
  if (!score && score !== 0) return <span style={{ color: "#9ca3af" }}>—</span>;

  const color = score >= 7.5 ? "#16a34a" : score >= 5 ? "#f59e0b" : "#dc2626";
  const bg    = score >= 7.5 ? "#f0fdf4" : score >= 5 ? "#fffbeb" : "#fef2f2";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      {rank === 1 && <span title="Best pick">★</span>}
      <span style={{
        fontWeight: 700, fontSize: 14, color,
        backgroundColor: bg, padding: "2px 8px", borderRadius: 8,
      }}>
        {score.toFixed(1)}
      </span>
    </div>
  );
}

// ─── Claim Flag Summary ───────────────────────────────────────────────────────

function ClaimFlags({ analysis }) {
  if (!analysis) return <span style={{ color: "#9ca3af" }}>—</span>;

  const { contradictions = [], vague_claims = [] } = analysis;

  if (contradictions.length === 0 && vague_claims.length === 0) {
    return <span style={{ color: "#16a34a", fontWeight: 600 }}>✓ Clean</span>;
  }

  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {contradictions.length > 0 && (
        <span style={styles.flagRed} title="Contradictions found">
          {contradictions.length} ✗
        </span>
      )}
      {vague_claims.length > 0 && (
        <span style={styles.flagYellow} title="Vague/unverifiable claims">
          {vague_claims.length} ⚠
        </span>
      )}
    </div>
  );
}

// ─── Main Table ───────────────────────────────────────────────────────────────

export default function CompareTable({ products, onSelectProduct, onRemove, onClearAll }) {
  const readyProducts = products.filter(p => p.status === "ready" && p.scores);

  // Determine best product (rank 1)
  const ranked = [...readyProducts].sort((a, b) => (b.scores?.total || 0) - (a.scores?.total || 0));
  const rankMap = new Map(ranked.map((p, i) => [p.platform_id, i + 1]));

  return (
    <div style={styles.container}>

      {/* Summary bar */}
      {readyProducts.length > 1 && (
        <div style={styles.summaryBar}>
          <span style={styles.summaryText}>
            {readyProducts.length} of {products.length} analyzed
          </span>
          {ranked[0] && (
            <span style={styles.bestPick}>
              Best: <strong>{truncate(ranked[0].product_name, 25)}</strong>
            </span>
          )}
        </div>
      )}

      {/* Product Cards */}
      <div style={styles.cardList}>
        {products.map((product) => {
          const rank = rankMap.get(product.platform_id);
          const isWinner = rank === 1 && readyProducts.length > 1;
          const per100g = product.nutrition_per_100g;
          const perRs = product.nutrition_per_rs100;

          return (
            <div
              key={product.platform_id}
              style={{
                ...styles.card,
                ...(isWinner ? styles.cardWinner : {}),
              }}
            >
              {/* Card Header */}
              <div style={styles.cardHeader}>
                <div style={styles.cardTitle}>
                  {isWinner && <span style={styles.winnerBadge}>Best Pick</span>}
                  <p style={styles.productName}>{truncate(product.product_name, 50)}</p>
                  <p style={styles.brandName}>{product.brand || "Unknown brand"}</p>
                </div>
                <button
                  style={styles.removeBtn}
                  onClick={(e) => { e.stopPropagation(); onRemove(product.platform_id); }}
                  title="Remove"
                >
                  ✕
                </button>
              </div>

              {/* Status / Processing indicator */}
              {product.status !== "ready" && (
                <div style={{ padding: "8px 0" }}>
                  <StatusBadge status={product.status} error={product.error} />
                  {product.status === "processing" && (
                    <p style={styles.processingHint}>
                      Verifying nutritional claims...
                    </p>
                  )}
                </div>
              )}

              {/* Metrics Grid — only when ready */}
              {product.status === "ready" && (
                <>
                  <div style={styles.metricsGrid}>
                    <Metric
                      label="Price"
                      value={formatPrice(product.price_inr)}
                      sub={product.quantity_g ? `${product.quantity_g}g pack` : null}
                    />
                    <Metric
                      label="Cost per 100g"
                      value={product.price_per_100g ? `₹${product.price_per_100g}` : "—"}
                    />
                    <Metric
                      label="Protein / ₹100"
                      value={perRs?.protein_g ? `${perRs.protein_g.toFixed(1)}g` : "—"}
                      highlight={isWinner}
                    />
                    <Metric
                      label="Sugar / 100g"
                      value={per100g?.sugar_g != null ? `${per100g.sugar_g.toFixed(1)}g` : "—"}
                      warn={per100g?.sugar_g > 5}
                    />
                    <Metric
                      label="Protein / 100g"
                      value={per100g?.protein_g ? `${per100g.protein_g.toFixed(1)}g` : "—"}
                    />
                    <div style={styles.metricCell}>
                      <span style={styles.metricLabel}>Claim issues</span>
                      <ClaimFlags analysis={product.analysis} />
                    </div>
                  </div>

                  {/* Score + Detail Link */}
                  <div style={styles.cardFooter}>
                    <div style={styles.scoreSection}>
                      <span style={styles.scoreLabel}>NutriScore</span>
                      <ScoreBadge score={product.scores?.total} rank={rank} />
                    </div>
                    <button style={styles.detailBtn} onClick={() => onSelectProduct(product)}>
                      View details →
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer Actions */}
      <div style={styles.footer}>
        <button style={styles.clearBtn} onClick={onClearAll}>
          Clear all
        </button>
        <p style={styles.footerNote}>
          Scores based on FSSAI guidelines. Not medical advice.
        </p>
      </div>
    </div>
  );
}

// ─── Metric Cell ─────────────────────────────────────────────────────────────

function Metric({ label, value, sub, highlight, warn }) {
  return (
    <div style={styles.metricCell}>
      <span style={styles.metricLabel}>{label}</span>
      <span style={{
        ...styles.metricValue,
        ...(highlight ? styles.metricHighlight : {}),
        ...(warn ? styles.metricWarn : {}),
      }}>
        {value}
      </span>
      {sub && <span style={styles.metricSub}>{sub}</span>}
    </div>
  );
}

function truncate(str, n) {
  if (!str) return "";
  return str.length > n ? str.slice(0, n) + "…" : str;
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
  },
  summaryBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 16px",
    backgroundColor: "#f9fafb",
    borderBottom: "1px solid #f0f0f0",
    fontSize: 11,
  },
  summaryText: { color: "#9ca3af" },
  bestPick:   { color: "#16a34a" },
  cardList:   { display: "flex", flexDirection: "column", gap: 0 },
  card: {
    padding: "12px 16px",
    borderBottom: "1px solid #f0f0f0",
    cursor: "default",
  },
  cardWinner: {
    backgroundColor: "#f0fdf4",
    borderLeft: "3px solid #16a34a",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 8,
  },
  cardTitle:    { flex: 1 },
  winnerBadge: {
    display: "inline-block",
    fontSize: 10,
    fontWeight: 700,
    color: "#16a34a",
    backgroundColor: "#dcfce7",
    padding: "1px 6px",
    borderRadius: 10,
    marginBottom: 3,
  },
  productName: {
    margin: 0,
    fontWeight: 600,
    fontSize: 12,
    lineHeight: 1.4,
    color: "#111827",
  },
  brandName: {
    margin: "2px 0 0",
    fontSize: 11,
    color: "#6b7280",
  },
  removeBtn: {
    background: "none",
    border: "none",
    color: "#d1d5db",
    cursor: "pointer",
    fontSize: 13,
    padding: "0 0 0 8px",
    lineHeight: 1,
    flexShrink: 0,
  },
  metricsGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr 1fr",
    gap: "8px 0",
    marginBottom: 10,
  },
  metricCell: {
    display: "flex",
    flexDirection: "column",
    gap: 1,
  },
  metricLabel: {
    fontSize: 10,
    color: "#9ca3af",
    textTransform: "uppercase",
    letterSpacing: "0.3px",
  },
  metricValue: {
    fontSize: 13,
    fontWeight: 600,
    color: "#111827",
  },
  metricHighlight: { color: "#16a34a" },
  metricWarn:      { color: "#dc2626" },
  metricSub:       { fontSize: 10, color: "#9ca3af" },
  processingHint:  { fontSize: 11, color: "#9ca3af", margin: "4px 0 0" },
  cardFooter: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    paddingTop: 8,
    borderTop: "1px solid #f0f0f0",
  },
  scoreSection: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  scoreLabel: {
    fontSize: 11,
    color: "#6b7280",
  },
  detailBtn: {
    fontSize: 11,
    color: "#16a34a",
    background: "none",
    border: "none",
    cursor: "pointer",
    fontWeight: 600,
    padding: 0,
  },
  footer: {
    padding: "10px 16px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderTop: "1px solid #f0f0f0",
    backgroundColor: "#f9fafb",
  },
  clearBtn: {
    fontSize: 11,
    color: "#6b7280",
    background: "none",
    border: "1px solid #e5e7eb",
    borderRadius: 4,
    padding: "4px 10px",
    cursor: "pointer",
  },
  footerNote: {
    margin: 0,
    fontSize: 10,
    color: "#d1d5db",
    maxWidth: 180,
    textAlign: "right",
    lineHeight: 1.3,
  },
  flagRed:    { fontSize: 10, color: "#dc2626", backgroundColor: "#fef2f2",
    padding: "1px 5px", borderRadius: 8, fontWeight: 700 },
  flagYellow: { fontSize: 10, color: "#d97706", backgroundColor: "#fffbeb",
    padding: "1px 5px", borderRadius: 8, fontWeight: 700 },
};