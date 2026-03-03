/**
 * App.jsx — NutriLens Popup Root
 *
 * Three views:
 *   "page"    — Product detected on current page, offer to add
 *   "compare" — Comparison set table with scores
 *   "detail"  — Single product drill-down
 */

import { useState, useEffect } from "react";
import CompareTable from "./CompareTable.jsx";
import ProductDetail from "./ProductDetail.jsx";

// ─── Icons (inline SVG to avoid asset loading) ───────────────────────────────

const LeafIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10z"/>
    <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>
  </svg>
);

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView] = useState("compare"); // "compare" | "detail" | "page"
  const [comparisonSet, setComparisonSet] = useState([]);
  const [pageProduct, setPageProduct] = useState(null);   // Product detected on current tab
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addStatus, setAddStatus] = useState(null); // null | "adding" | "added" | "error" | "duplicate" | "limit"
  const [snipResult, setSnipResult] = useState(null);   // OCR result from snippet capture
  const [snipLoading, setSnipLoading] = useState(false);

  // ─── Init: load comparison set + check current tab ─────────────────────────

  useEffect(() => {
    loadComparisonSet();
    checkCurrentTab();
    listenForMessages();
  }, []);

  async function loadComparisonSet() {
    setLoading(true);
    const response = await sendMessage({ type: "GET_COMPARISON_SET" });
    setComparisonSet(response?.set || []);
    setLoading(false);
  }

  async function checkCurrentTab() {
    // Ask background for any product pending on the current tab
    const response = await sendMessage({ type: "GET_PAGE_PRODUCT" });
    if (response?.product) {
      setPageProduct(response.product);
    }
  }

  function listenForMessages() {
    chrome.runtime.onMessage.addListener((message) => {
      if (message.type === "PAGE_PRODUCT_AVAILABLE") {
        setPageProduct(message.preview);
      }
      if (message.type === "PRODUCT_READY") {
        // Update comparison set with enriched data
        setComparisonSet(prev =>
          prev.map(p =>
            p.platform_id === message.platform_id
              ? { ...p, ...message.data, status: "ready" }
              : p
          )
        );
      }
      if (message.type === "SNIP_READY") {
        setSnipResult(message.data);
        setSnipLoading(false);
      }
      if (message.type === "PRODUCT_FAILED") {
        setComparisonSet(prev =>
          prev.map(p =>
            p.platform_id === message.platform_id
              ? { ...p, status: "failed", error: message.error }
              : p
          )
        );
      }
    });
  }

  // ─── Actions ──────────────────────────────────────────────────────────────

  async function handleAddToCompare() {
    if (!pageProduct) return;
    setAddStatus("adding");

    const response = await sendMessage({
      type: "ADD_TO_COMPARE",
      platform_id: pageProduct.platform_id,
    });

    if (response?.ok) {
      setAddStatus("added");
      await loadComparisonSet();
      setTimeout(() => setAddStatus(null), 2000);
    } else if (response?.reason === "duplicate") {
      setAddStatus("duplicate");
      setTimeout(() => setAddStatus(null), 2000);
    } else if (response?.reason === "limit_reached") {
      setAddStatus("limit");
      setTimeout(() => setAddStatus(null), 2000);
    } else {
      setAddStatus("error");
      console.error("[NutriLens] Add failed:", response);
      setTimeout(() => setAddStatus(null), 3000);
    }
  }

  async function handleRemove(platformId) {
    await sendMessage({ type: "REMOVE_FROM_SET", platform_id: platformId });
    await loadComparisonSet();
  }

  async function handleClearAll() {
    await sendMessage({ type: "CLEAR_SET" });
    setComparisonSet([]);
  }

  function handleSelectProduct(product) {
    setSelectedProduct(product);
    setView("detail");
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  async function startSnip() {
    setSnipLoading(true);
    setSnipResult(null);
    // Close popup, inject snip overlay into active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files:  ["content_scripts/snip.js"],
    });
    window.close(); // close popup so user can draw selection
  }

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.logo}>
          <span style={styles.logoIcon}><LeafIcon /></span>
          <span style={styles.logoText}>NutriLens</span>
        </div>
        {comparisonSet.length > 0 && view !== "compare" && (
          <button style={styles.navBtn} onClick={() => setView("compare")}>
            Compare ({comparisonSet.length})
          </button>
        )}
        {view === "detail" && (
          <button style={styles.navBtn} onClick={() => setView("compare")}>
            ← Back
          </button>
        )}
      </div>

      {/* Scan Label button — always visible on Amazon product pages */}
      <div style={{ padding: "8px 12px 0", display: "flex", gap: "8px", alignItems: "center" }}>
        <button
          onClick={startSnip}
          disabled={snipLoading}
          style={{
            background: snipLoading ? "#6b7280" : "#16a34a",
            color: "#fff", border: "none", borderRadius: "6px",
            padding: "7px 14px", fontSize: "13px", fontFamily: "system-ui",
            cursor: snipLoading ? "default" : "pointer", flex: 1,
          }}
        >
          {snipLoading ? "⏳ Scanning…" : "📷 Scan Nutrition Label"}
        </button>
        {snipResult && (
          <button
            onClick={() => setSnipResult(null)}
            style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: "16px" }}
          >✕</button>
        )}
      </div>

      {/* Snip Result Panel */}
      {snipResult && (
        <div style={{
          margin: "8px 12px", padding: "10px 12px",
          background: "#f0fdf4", borderRadius: "8px",
          border: "1px solid #bbf7d0", fontSize: "12px", fontFamily: "system-ui",
        }}>
          <div style={{ fontWeight: 600, color: "#15803d", marginBottom: "6px" }}>
            ✓ Scanned — {Object.keys(snipResult.nutrition || {}).length} nutrients
            {snipResult.fssai && <span style={{ marginLeft: "8px", color: "#6b7280" }}>FSSAI: {snipResult.fssai}</span>}
          </div>
          {Object.entries(snipResult.nutrition || {}).map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "1px 0", color: "#374151" }}>
              <span>{k.replace(/_/g, " ").replace(/ g$| mg$| kcal$/, "")}</span>
              <span style={{ fontWeight: 500 }}>{v}{k.endsWith("_mg") ? " mg" : k.endsWith("_kcal") ? " kcal" : " g"}</span>
            </div>
          ))}
          {snipResult.serving_size && (
            <div style={{ marginTop: "4px", color: "#6b7280" }}>Serving: {snipResult.serving_size}g</div>
          )}
        </div>
      )}

      {/* Page Product Banner — shown when a product is detected on current tab */}
      {pageProduct && view !== "detail" && (
        <PageProductBanner
          product={pageProduct}
          addStatus={addStatus}
          onAdd={handleAddToCompare}
          alreadyInSet={comparisonSet.some(p => p.platform_id === pageProduct.platform_id)}
        />
      )}

      {/* Main Content */}
      <div style={styles.content}>
        {loading ? (
          <div style={styles.centered}>
            <div style={styles.spinner} />
            <p style={styles.hint}>Loading...</p>
          </div>
        ) : view === "compare" ? (
          comparisonSet.length === 0 ? (
            <EmptyState />
          ) : (
            <CompareTable
              products={comparisonSet}
              onSelectProduct={handleSelectProduct}
              onRemove={handleRemove}
              onClearAll={handleClearAll}
            />
          )
        ) : view === "detail" && selectedProduct ? (
          <ProductDetail product={selectedProduct} />
        ) : null}
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function PageProductBanner({ product, addStatus, onAdd, alreadyInSet }) {
  const statusMessages = {
    adding:    "Analyzing...",
    added:     "✓ Added!",
    duplicate: "Already in list",
    limit:     "List full (max 5)",
    error:     "Failed — retry",
  };

  return (
    <div style={styles.banner}>
      <div style={styles.bannerInfo}>
        <p style={styles.bannerName}>{truncate(product.product_name, 45)}</p>
        <p style={styles.bannerMeta}>
          {product.price_inr ? `₹${product.price_inr.toLocaleString("en-IN")}` : ""}
          {product.quantity_g ? ` · ${product.quantity_g}g` : ""}
          {product.nutrition_confidence ? ` · ${product.nutrition_confidence} confidence` : ""}
        </p>
      </div>
      <button
        style={{
          ...styles.addBtn,
          ...(alreadyInSet ? styles.addBtnDone : {}),
          ...(addStatus === "adding" ? styles.addBtnLoading : {}),
        }}
        onClick={onAdd}
        disabled={!!addStatus || alreadyInSet}
      >
        {alreadyInSet ? "✓ Added" : addStatus ? statusMessages[addStatus] : "+ Compare"}
      </button>
    </div>
  );
}

function EmptyState() {
  return (
    <div style={styles.centered}>
      <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
      <p style={styles.emptyTitle}>No products yet</p>
      <p style={styles.hint}>
        Browse any protein powder, health bar, or cereal on Amazon, BigBasket, or Flipkart —
        then click <strong>+ Compare</strong> to add it.
      </p>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function truncate(str, n) {
  if (!str) return "";
  return str.length > n ? str.slice(0, n) + "…" : str;
}

function sendMessage(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, resolve);
  });
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = {
  container: {
    width: 380,
    minHeight: 200,
    maxHeight: 560,
    fontFamily: "'Inter', -apple-system, sans-serif",
    fontSize: 13,
    color: "#1a1a1a",
    backgroundColor: "#ffffff",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 16px",
    borderBottom: "1px solid #f0f0f0",
    backgroundColor: "#f9fafb",
  },
  logo: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  logoIcon: {
    color: "#16a34a",
    display: "flex",
  },
  logoText: {
    fontWeight: 700,
    fontSize: 15,
    color: "#16a34a",
    letterSpacing: "-0.3px",
  },
  navBtn: {
    fontSize: 12,
    color: "#6b7280",
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "4px 8px",
    borderRadius: 4,
  },
  banner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 16px",
    backgroundColor: "#f0fdf4",
    borderBottom: "1px solid #bbf7d0",
    gap: 12,
  },
  bannerInfo: {
    flex: 1,
    minWidth: 0,
  },
  bannerName: {
    margin: 0,
    fontWeight: 600,
    fontSize: 12,
    lineHeight: 1.3,
    color: "#111827",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  bannerMeta: {
    margin: "2px 0 0",
    fontSize: 11,
    color: "#6b7280",
  },
  addBtn: {
    flexShrink: 0,
    backgroundColor: "#16a34a",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    padding: "7px 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  addBtnDone: {
    backgroundColor: "#9ca3af",
    cursor: "default",
  },
  addBtnLoading: {
    backgroundColor: "#4ade80",
    cursor: "wait",
  },
  content: {
    flex: 1,
    overflowY: "auto",
  },
  centered: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: 32,
    textAlign: "center",
    gap: 8,
  },
  emptyTitle: {
    margin: 0,
    fontWeight: 600,
    fontSize: 14,
    color: "#374151",
  },
  hint: {
    margin: 0,
    fontSize: 12,
    color: "#9ca3af",
    lineHeight: 1.5,
  },
  spinner: {
    width: 24,
    height: 24,
    border: "3px solid #e5e7eb",
    borderTopColor: "#16a34a",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
};