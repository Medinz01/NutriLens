/**
 * CompareTable.jsx — NutriLens Comparison View
 * Uses nutrition + nutriscore data from snippet OCR pipeline.
 */

const GRADE_COLORS = {
  A: { bg: "#00843b", text: "#fff" },
  B: { bg: "#85bb2f", text: "#fff" },
  C: { bg: "#fecb02", text: "#000" },
  D: { bg: "#ee8100", text: "#fff" },
  E: { bg: "#e63312", text: "#fff" },
};

function GradeBadge({ grade }) {
  if (!grade) return <span style={{ color: "#9ca3af" }}>—</span>;
  const { bg, text } = GRADE_COLORS[grade] || GRADE_COLORS.E;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 28, height: 28, borderRadius: "50%",
      background: bg, color: text,
      fontWeight: 700, fontSize: 13,
    }}>{grade}</span>
  );
}

function val(nutrition, key, decimals = 1) {
  const v = nutrition?.[key];
  return v != null ? Number(v).toFixed(decimals) : "—";
}

function proteinPer100(product) {
  const p = product.nutrition?.protein_g;
  const q = product.quantity_g;
  if (!p || !q) return null;
  // protein per 100g of product
  const serving = product.serving_size || 30;
  return ((p / serving) * 100).toFixed(1);
}

function proteinPerRupee(product) {
  // protein_g is per-100g, quantity_g is pack size
  // total protein in pack = (protein_g / 100) * quantity_g
  // protein per ₹100 = total_protein / price * 100
  const p     = product.nutrition?.protein_g;
  const price = product.price_inr;
  const qty   = product.quantity_g;
  if (!p || !price || !qty) return null;
  const totalProtein = (p / 100) * qty;
  return ((totalProtein / price) * 100).toFixed(1);
}

export default function CompareTable({ products, onSelectProduct, onRemove, onClearAll }) {
  const ready = products.filter(p => p.status === "ready");
  const pending = products.filter(p => p.status !== "ready");

  // Find best protein/rupee for highlighting
  const pprs = ready.map(p => parseFloat(proteinPerRupee(p) || 0));
  const bestPPR = Math.max(...pprs);

  return (
    <div style={{ fontFamily: "system-ui", fontSize: 12 }}>

      {/* Pending items */}
      {pending.map(p => (
        <div key={p.platform_id} style={{
          margin: "8px 10px", padding: "10px 12px",
          background: "#fafafa", border: "1px solid #e5e7eb", borderRadius: 8,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span style={{ color: "#6b7280", fontSize: 12 }}>
            {p.product_name?.slice(0, 40)}…
          </span>
          <span style={{ color: "#f59e0b", fontSize: 11, fontWeight: 600 }}>
            Scan pending
          </span>
        </div>
      ))}

      {/* Ready products */}
      {ready.map((p, i) => {
        const ppr   = proteinPerRupee(p);
        const isBest = ppr && parseFloat(ppr) === bestPPR && ready.length > 1;

        return (
          <div key={p.platform_id} style={{
            margin: "8px 10px",
            border: isBest ? "2px solid #16a34a" : "1px solid #e5e7eb",
            borderRadius: 10, background: "#fff",
            overflow: "hidden",
          }}>
            {/* Product header */}
            <div style={{
              padding: "10px 12px",
              background: isBest ? "#f0fdf4" : "#f9fafb",
              display: "flex", justifyContent: "space-between", alignItems: "flex-start",
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: "#111",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {isBest && <span style={{ color: "#16a34a" }}>★ </span>}
                  {p.product_name || "Product"}
                </div>
                <div style={{ color: "#6b7280", fontSize: 11, marginTop: 2 }}>
                  {p.brand && `${p.brand} · `}
                  {p.quantity_g && `${p.quantity_g}g · `}
                  {p.price_inr && `₹${p.price_inr}`}
                </div>
                {p.scores?.total != null && (
                  <div style={{ fontSize: 11, marginTop: 3 }}>
                    <span style={{ color: "#7c3aed", fontWeight: 700 }}>{p.scores.total}/10</span>
                    <span style={{ color: "#9ca3af" }}> accountability · </span>
                    <span style={{ color: "#6b7280" }}>NutriScore {p.nutriscore?.grade || "—"}</span>
                  </div>
                )}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <GradeBadge grade={p.nutriscore?.grade} />
                <button onClick={() => onRemove(p.platform_id)} style={{
                  background: "none", border: "none", color: "#9ca3af",
                  cursor: "pointer", fontSize: 16, lineHeight: 1, padding: 0,
                }}>×</button>
              </div>
            </div>

            {/* Metrics grid — all values per 100g */}
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
              padding: "10px 12px", gap: 8,
            }}>
              <div style={{ gridColumn: "1/-1", fontSize: 10, color: "#9ca3af", marginBottom: 2 }}>
                Per 100g
              </div>
              <Metric label="Protein" value={val(p.nutrition, "protein_g")} unit="g" />
              <Metric label="Energy" value={val(p.nutrition, "energy_kcal", 0)} unit="kcal" />
              <Metric label="Sugar" value={val(p.nutrition, "sugar_g")} unit="g" />
              <Metric label="Sat Fat" value={val(p.nutrition, "saturated_fat_g")} unit="g" />
              <Metric label="Sodium" value={val(p.nutrition, "sodium_mg", 0)} unit="mg" />
              <Metric
                label="Protein/₹100"
                value={ppr || "—"}
                unit={ppr ? "g" : ""}
                highlight={isBest}
              />
            </div>

            {/* FSSAI + per-100g protein row */}
            <div style={{
              padding: "6px 12px 10px",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <span style={{
                fontSize: 11,
                color: p.fssai ? "#15803d" : "#92400e",
                background: p.fssai ? "#dcfce7" : "#fef3c7",
                borderRadius: 4, padding: "2px 6px",
              }}>
                {p.fssai ? `✓ FSSAI ${p.fssai}` : "⚠ FSSAI not found"}
              </span>
              <button
                onClick={() => onSelectProduct(p)}
                style={{ fontSize: 11, color: "#2563eb", background: "none",
                  border: "none", cursor: "pointer", padding: 0 }}
              >
                Full details →
              </button>
            </div>
          </div>
        );
      })}

      {/* Footer */}
      {products.length > 0 && (
        <div style={{
          padding: "8px 12px", textAlign: "center",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span style={{ fontSize: 11, color: "#9ca3af" }}>
            Scores based on FSSAI guidelines. Not medical advice.
          </span>
          <button onClick={onClearAll} style={{
            fontSize: 11, color: "#dc2626", background: "none",
            border: "none", cursor: "pointer",
          }}>Clear all</button>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, unit, highlight }) {
  return (
    <div style={{
      background: highlight ? "#f0fdf4" : "#f9fafb",
      borderRadius: 6, padding: "6px 8px", textAlign: "center",
    }}>
      <div style={{ fontSize: 10, color: "#6b7280", marginBottom: 2 }}>{label}</div>
      <div style={{
        fontWeight: 700, fontSize: 13,
        color: highlight ? "#15803d" : "#111",
      }}>
        {value}<span style={{ fontSize: 10, fontWeight: 400, color: "#6b7280" }}> {unit}</span>
      </div>
    </div>
  );
}