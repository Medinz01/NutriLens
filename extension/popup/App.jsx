/**
 * App.jsx — NutriLens Popup
 *
 * States per product:
 *   awaiting_scan  → FSSAI scanning + "Scan Label" CTA
 *   analyzed       → full nutrition + nutriscore + Compare button
 *
 * Views:
 *   "home"    → current page product card
 *   "compare" → comparison table
 *   "detail"  → single product drill-down
 */

import { useState, useEffect } from "react";
import CompareTable from "./CompareTable.jsx";
import ProductDetail from "./ProductDetail.jsx";

// ─── Grade badge ─────────────────────────────────────────────────────────────

const GRADE_COLORS = {
  A: { bg: "#00843b", text: "#fff" },
  B: { bg: "#85bb2f", text: "#fff" },
  C: { bg: "#fecb02", text: "#000" },
  D: { bg: "#ee8100", text: "#fff" },
  E: { bg: "#e63312", text: "#fff" },
};

function GradeBadge({ grade, size = 36 }) {
  if (!grade) return null;
  const { bg, text } = GRADE_COLORS[grade] || GRADE_COLORS.E;
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%",
      background: bg, color: text,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontWeight: 700, fontSize: size * 0.45, flexShrink: 0,
    }}>{grade}</div>
  );
}

// ─── FSSAI status badge ───────────────────────────────────────────────────────

function FssaiBadge({ status, fssai }) {
  if (status === "scanning") return (
    <span style={badge("#e0f2fe", "#0369a1")}>🔍 Checking FSSAI…</span>
  );
  if (status === "found") return (
    <span style={badge("#dcfce7", "#15803d")}>✓ FSSAI {fssai}</span>
  );
  return (
    <span style={badge("#fef9c3", "#854d0e")}>⚠ FSSAI not found</span>
  );
}

function badge(bg, color) {
  return {
    background: bg, color, borderRadius: 4,
    padding: "2px 7px", fontSize: 11, fontWeight: 500,
    fontFamily: "system-ui",
  };
}

// ─── Nutrient row ─────────────────────────────────────────────────────────────

const NUTRIENT_LABELS = {
  energy_kcal:      ["Energy",           "kcal"],
  protein_g:        ["Protein",          "g"],
  carbohydrates_g:  ["Carbohydrates",    "g"],
  sugar_g:          ["  Total Sugars",   "g"],
  added_sugar_g:    ["  Added Sugars",   "g"],
  total_fat_g:      ["Total Fat",        "g"],
  saturated_fat_g:  ["  Saturated Fat",  "g"],
  trans_fat_g:      ["  Trans Fat",      "g"],
  dietary_fiber_g:  ["Dietary Fiber",    "g"],
  sodium_mg:        ["Sodium",           "mg"],
  cholesterol_mg:   ["Cholesterol",      "mg"],
};

function NutritionPanel({ nutrition, servingSize }) {
  const ordered = Object.keys(NUTRIENT_LABELS).filter(k => k in nutrition);
  return (
    <div style={{ fontSize: 12, fontFamily: "system-ui" }}>
      {servingSize && (
        <div style={{ color: "#6b7280", marginBottom: 6 }}>
          Per serving ({servingSize}g)
        </div>
      )}
      {ordered.map(k => {
        const [label, unit] = NUTRIENT_LABELS[k];
        return (
          <div key={k} style={{
            display: "flex", justifyContent: "space-between",
            padding: "2px 0", borderBottom: "1px solid #f3f4f6",
            color: "#374151",
          }}>
            <span>{label}</span>
            <span style={{ fontWeight: 500 }}>{nutrition[k]} {unit}</span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Product card (home view) ─────────────────────────────────────────────────

function ProductCard({ product, onScan, onCompare, compareSet, snipLoading }) {
  const analyzed     = product.status === "analyzed";
  const alreadyAdded = compareSet.some(p => p.platform_id === product.platform_id);
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{
      margin: "10px 12px", padding: "12px",
      background: "#fff", borderRadius: 10,
      border: "1px solid #e5e7eb",
      boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
      fontFamily: "system-ui",
    }}>
      {/* Product header */}
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start", marginBottom: 8 }}>
        {analyzed && product.nutriscore && (
          <GradeBadge grade={product.nutriscore.grade} size={40} />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: "#111", lineHeight: 1.3,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {product.product_name || "Product"}
          </div>
          <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
            {product.brand && <span>{product.brand} · </span>}
            {product.quantity_g && <span>{product.quantity_g}g · </span>}
            {product.price_inr && <span>₹{product.price_inr}</span>}
          </div>
          <div style={{ marginTop: 4 }}>
            <FssaiBadge status={product.fssai_status} fssai={product.fssai} />
          </div>
        </div>
      </div>

      {/* Analyzed state — show nutriscore summary */}
      {analyzed && product.nutriscore && (
        <div style={{
          background: "#f9fafb", borderRadius: 6, padding: "8px 10px",
          marginBottom: 8, display: "flex", alignItems: "center", gap: 10,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: "#374151", fontWeight: 500 }}>
              NutriScore {product.nutriscore.grade}
            </div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>
              Confidence: {product.confidence}
              {product.nutrition && ` · ${Object.keys(product.nutrition).length} nutrients`}
            </div>
          </div>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{ fontSize: 11, color: "#2563eb", background: "none",
              border: "none", cursor: "pointer", padding: 0 }}
          >
            {expanded ? "Hide ▲" : "Details ▼"}
          </button>
        </div>
      )}

      {/* Expanded nutrition panel */}
      {expanded && product.nutrition && (
        <div style={{ marginBottom: 8 }}>
          <NutritionPanel nutrition={product.nutrition} servingSize={product.serving_size} />
        </div>
      )}

      {/* CTA buttons */}
      <div style={{ display: "flex", gap: 8 }}>
        {!analyzed ? (
          <button onClick={onScan} disabled={snipLoading} style={{
            flex: 1, background: snipLoading ? "#9ca3af" : "#16a34a",
            color: "#fff", border: "none", borderRadius: 6,
            padding: "8px 0", fontSize: 13, fontWeight: 600,
            cursor: snipLoading ? "default" : "pointer",
          }}>
            {snipLoading ? "⏳ Scanning…" : "📷 Scan Nutrition Label"}
          </button>
        ) : (
          <>
            <button onClick={onScan} style={{
              flex: 0, background: "none", border: "1px solid #d1d5db",
              borderRadius: 6, padding: "7px 10px", fontSize: 12,
              color: "#374151", cursor: "pointer",
            }}>
              🔄 Re-scan
            </button>
            <button onClick={onCompare} disabled={alreadyAdded} style={{
              flex: 1,
              background: alreadyAdded ? "#d1fae5" : "#2563eb",
              color: alreadyAdded ? "#065f46" : "#fff",
              border: "none", borderRadius: 6,
              padding: "8px 0", fontSize: 13, fontWeight: 600,
              cursor: alreadyAdded ? "default" : "pointer",
            }}>
              {alreadyAdded ? "✓ Added to Compare" : "+ Add to Compare"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView]               = useState("home");
  const [product, setProduct]         = useState(null);
  const [compareSet, setCompareSet]   = useState([]);
  const [selectedProduct, setSelected] = useState(null);
  const [loading, setLoading]         = useState(true);
  const [snipLoading, setSnipLoading] = useState(false);

  useEffect(() => {
    init();
    const listener = (msg) => {
      if (msg.type === "PAGE_PRODUCT_AVAILABLE") {
        loadPageProduct();
      }
      if (msg.type === "FSSAI_RESULT") {
        setProduct(p => p?.platform_id === msg.platform_id
          ? { ...p, fssai: msg.fssai, fssai_status: msg.fssai_status }
          : p
        );
      }
      if (msg.type === "SCAN_COMPLETE") {
        setSnipLoading(false);
        setProduct(p => p?.platform_id === msg.platform_id
          ? { ...p, ...msg.data }
          : p
        );
        loadCompareSet();
      }
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  async function init() {
    await Promise.all([loadPageProduct(), loadCompareSet()]);
    setLoading(false);
  }

  async function loadPageProduct() {
    const resp = await chrome.runtime.sendMessage({ type: "GET_PAGE_PRODUCT" });
    if (resp?.product) setProduct(resp.product);
  }

  async function loadCompareSet() {
    const resp = await chrome.runtime.sendMessage({ type: "GET_COMPARE_SET" });
    setCompareSet(resp?.set || []);
  }

  async function startSnip() {
    setSnipLoading(true);
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files:  ["content_scripts/snip.js"],
    });
    window.close();
  }

  async function handleAddToCompare() {
    if (!product) return;
    const resp = await chrome.runtime.sendMessage({
      type: "ADD_TO_COMPARE",
      platform_id: product.platform_id,
    });
    if (resp?.ok) {
      await loadCompareSet();
      setProduct(p => ({ ...p })); // trigger re-render for button state
    } else if (resp?.error) {
      alert("NutriLens: " + resp.error);
    }
  }

  async function handleRemove(platform_id) {
    const resp = await chrome.runtime.sendMessage({ type: "REMOVE_FROM_COMPARE", platform_id });
    setCompareSet(resp?.set || []);
  }

  async function handleClearAll() {
    await chrome.runtime.sendMessage({ type: "CLEAR_COMPARE" });
    setCompareSet([]);
  }

  return (
    <div style={{ width: 360, minHeight: 200, background: "#f9fafb", fontFamily: "system-ui" }}>

      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", background: "#fff",
        borderBottom: "1px solid #e5e7eb",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>🌿</span>
          <span style={{ fontWeight: 700, fontSize: 15, color: "#15803d" }}>NutriLens</span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={() => setView("home")}
            style={navBtn(view === "home")}
          >Home</button>
          <button
            onClick={() => setView("compare")}
            style={navBtn(view === "compare")}
          >
            Compare {compareSet.length > 0 && `(${compareSet.length})`}
          </button>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ padding: 24, textAlign: "center", color: "#9ca3af" }}>Loading…</div>
      ) : view === "home" ? (
        product ? (
          <ProductCard
            product={product}
            onScan={startSnip}
            onCompare={handleAddToCompare}
            compareSet={compareSet}
            snipLoading={snipLoading}
          />
        ) : (
          <div style={{ padding: 24, textAlign: "center" }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
            <div style={{ fontSize: 13, color: "#6b7280" }}>
              Open a product page on Amazon, BigBasket, or Flipkart
            </div>
          </div>
        )
      ) : view === "compare" ? (
        compareSet.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center" }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>📊</div>
            <div style={{ fontSize: 13, color: "#6b7280" }}>
              Scan products and click "+ Add to Compare" to build your comparison
            </div>
          </div>
        ) : (
          <CompareTable
            products={compareSet}
            onSelectProduct={(p) => { setSelected(p); setView("detail"); }}
            onRemove={handleRemove}
            onClearAll={handleClearAll}
          />
        )
      ) : view === "detail" && selectedProduct ? (
        <div>
          <button
            onClick={() => setView("compare")}
            style={{ margin: "10px 12px", background: "none", border: "none",
              color: "#2563eb", cursor: "pointer", fontSize: 13 }}
          >← Back</button>
          <ProductDetail product={selectedProduct} />
        </div>
      ) : null}
    </div>
  );
}

function navBtn(active) {
  return {
    background: active ? "#dcfce7" : "none",
    color: active ? "#15803d" : "#6b7280",
    border: "none", borderRadius: 6,
    padding: "4px 10px", fontSize: 12,
    fontWeight: active ? 600 : 400,
    cursor: "pointer",
  };
}