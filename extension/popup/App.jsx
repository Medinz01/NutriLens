/**
 * App.jsx — NutriLens Popup
 *
 * Home view shows full product analysis:
 *   - Product identity + FSSAI
 *   - Claims extracted from DOM (with source badge)
 *   - NutriScore + nutrition table (after OCR scan)
 *   - Compare button
 */

import { useState, useEffect } from "react";
import CompareTable from "./CompareTable.jsx";

// ─── Design tokens ────────────────────────────────────────────────────────────

const GRADE_COLORS = {
  A: { bg: "#00843b", text: "#fff" },
  B: { bg: "#85bb2f", text: "#fff" },
  C: { bg: "#fecb02", text: "#000" },
  D: { bg: "#ee8100", text: "#fff" },
  E: { bg: "#e63312", text: "#fff" },
};

// ─── Small components ─────────────────────────────────────────────────────────

function GradeBadge({ grade, size = 36 }) {
  if (!grade) return null;
  const { bg, text } = GRADE_COLORS[grade] || GRADE_COLORS.E;
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%",
      background: bg, color: text, flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontWeight: 700, fontSize: size * 0.45,
    }}>{grade}</div>
  );
}

function Pill({ bg, color, children }) {
  return (
    <span style={{
      background: bg, color, borderRadius: 4,
      padding: "2px 7px", fontSize: 11, fontWeight: 500,
      fontFamily: "system-ui", display: "inline-block",
    }}>{children}</span>
  );
}

function Section({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 8, marginTop: 8 }}>
      <button onClick={() => setOpen(o => !o)} style={{
        width: "100%", display: "flex", justifyContent: "space-between",
        alignItems: "center", background: "none", border: "none",
        cursor: "pointer", padding: 0, marginBottom: open ? 6 : 0,
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>{title}</span>
        <span style={{ fontSize: 12, color: "#9ca3af" }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && children}
    </div>
  );
}

// ─── FSSAI badge ──────────────────────────────────────────────────────────────

function FssaiBadge({ status, fssai }) {
  if (status === "scanning") return <Pill bg="#e0f2fe" color="#0369a1">🔍 Checking FSSAI…</Pill>;
  if (fssai)                 return <Pill bg="#dcfce7" color="#15803d">✓ FSSAI {fssai}</Pill>;
  return                            <Pill bg="#fef9c3" color="#854d0e">⚠ FSSAI not found</Pill>;
}

// ─── Claims section ───────────────────────────────────────────────────────────

const SOURCE_LABELS = {
  bullet:          { label: "Bullet",   bg: "#eff6ff", color: "#1d4ed8" },
  title:           { label: "Title",    bg: "#f0fdf4", color: "#15803d" },
  aplus_headline:  { label: "A+",       bg: "#fdf4ff", color: "#7e22ce" },
};

// Certification bodies with their verification URLs
const CERT_LINKS = {
  "labdoor":          { name: "Labdoor",          url: "https://labdoor.com/rankings/protein" },
  "informed choice":  { name: "Informed Choice",  url: "https://www.informedchoice.online/product-search/" },
  "informed sport":   { name: "Informed Sport",   url: "https://www.informed.sport/product-search" },
  "trustified":       { name: "Trustified",       url: "https://trustified.in/" },
  "fssai":            { name: "FSSAI",            url: "https://foscos.fssai.gov.in/" },
  "nsf":              { name: "NSF",              url: "https://www.nsfsport.com/certified-products/" },
};

// Classify what kind of claim this is
function classifyClaim(text) {
  const t = text.toLowerCase();

  // Numeric claims checkable against label
  if (/\d+\s*g\s*(protein|carb|fat|sugar|fiber|fibre)|(protein|carb|fat|sugar)\s*\d+\s*g|\d+\s*kcal|\d+\s*calories/i.test(text)) {
    return "numeric";
  }
  // Certification claims — have a verifiable source
  for (const key of Object.keys(CERT_LINKS)) {
    if (t.includes(key)) return "certified";
  }
  // Efficacy / comparative — requires clinical evidence
  if (/\d+%\s*(higher|better|faster|more|less)|clinically (proven|tested)|patent|world.s only|first in/i.test(text)) {
    return "efficacy";
  }
  return "general";
}

function getCertLinks(text) {
  const t = text.toLowerCase();
  return Object.entries(CERT_LINKS)
    .filter(([key]) => t.includes(key))
    .map(([, val]) => val);
}

const CLAIM_TYPE_CONFIG = {
  numeric:   { badge: "🔢 Numeric",    bg: "#eff6ff", color: "#1d4ed8", hint: "Tap to scroll to claim on page" },
  certified: { badge: "🏅 Certified",  bg: "#f0fdf4", color: "#15803d", hint: "Tap to scroll · verify links below" },
  efficacy:  { badge: "⚠ Efficacy",   bg: "#fff7ed", color: "#c2410c", hint: "Requires clinical study to verify" },
  general:   { badge: "💬 General",    bg: "#f9fafb", color: "#374151", hint: "Tap to scroll to claim on page" },
};

function ClaimItem({ c, claimCheck }) {
  const [expanded, setExpanded] = useState(false);
  const type   = classifyClaim(c.text);
  const config = CLAIM_TYPE_CONFIG[type];
  const certs  = type === "certified" ? getCertLinks(c.text) : [];

  // Check if this claim was numerically verified
  const verified     = claimCheck?.verified?.find(v => v.claim === c.text?.slice(0, 120));
  const contradicted = claimCheck?.contradicted?.find(v => v.claim === c.text?.slice(0, 120));

  function scrollToOnPage() {
    chrome.runtime.sendMessage({
      type:         "SCROLL_TO_CLAIM",
      selector:     c.selector,
      elementIndex: c.elementIndex,
    });
    // Close popup so user can see the page
    window.close();
  }

  const borderColor = contradicted ? "#dc2626" : verified ? "#16a34a" : config.color;

  return (
    <div style={{
      background: "#fff", borderRadius: 7,
      border: `1px solid #e5e7eb`,
      borderLeft: `3px solid ${borderColor}`,
      marginBottom: 5, overflow: "hidden",
    }}>
      {/* Main row — clickable */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{ padding: "7px 9px", cursor: "pointer", display: "flex", gap: 7, alignItems: "flex-start" }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 4 }}>
            <span style={{
              background: config.bg, color: config.color,
              fontSize: 10, fontWeight: 600, borderRadius: 3, padding: "1px 5px",
            }}>{config.badge}</span>
            {verified && (
              <span style={{ background: "#dcfce7", color: "#15803d", fontSize: 10, fontWeight: 600, borderRadius: 3, padding: "1px 5px" }}>
                ✓ Verified {verified.claimed}g vs label {verified.actual}g
              </span>
            )}
            {contradicted && (
              <span style={{ background: "#fee2e2", color: "#dc2626", fontSize: 10, fontWeight: 600, borderRadius: 3, padding: "1px 5px" }}>
                ✗ Mismatch: claimed {contradicted.claimed}g, label shows {contradicted.actual}g
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "#374151", lineHeight: 1.4 }}>{c.text}</div>
        </div>
        <span style={{ fontSize: 12, color: "#9ca3af", flexShrink: 0 }}>{expanded ? "▲" : "▼"}</span>
      </div>

      {/* Expanded actions */}
      {expanded && (
        <div style={{ background: "#f9fafb", borderTop: "1px solid #f3f4f6", padding: "7px 9px" }}>
          <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 6 }}>{config.hint}</div>

          {/* Scroll to on page */}
          {c.selector && (
            <button onClick={scrollToOnPage} style={{
              background: "#fff", border: "1px solid #d1d5db", borderRadius: 5,
              padding: "5px 10px", fontSize: 11, cursor: "pointer",
              color: "#374151", marginRight: 5, marginBottom: 5,
            }}>
              🔍 Show on page
            </button>
          )}

          {/* Verification links for certified claims */}
          {certs.map((cert, i) => (
            <a key={i} href={cert.url} target="_blank" rel="noopener" style={{
              display: "inline-block", background: "#eff6ff",
              border: "1px solid #bfdbfe", borderRadius: 5,
              padding: "5px 10px", fontSize: 11,
              color: "#1d4ed8", textDecoration: "none",
              marginRight: 5, marginBottom: 5,
            }}>
              🔗 Verify on {cert.name}
            </a>
          ))}

          {/* Efficacy disclaimer */}
          {type === "efficacy" && (
            <div style={{
              background: "#fff7ed", borderRadius: 5, padding: "6px 8px",
              fontSize: 11, color: "#92400e",
            }}>
              ⚠ Efficacy claims require peer-reviewed evidence. Ask the brand for the study citation.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ClaimsList({ claims, claimCheck }) {
  if (!claims?.length) return (
    <p style={{ fontSize: 12, color: "#9ca3af", margin: 0 }}>No claims extracted yet.</p>
  );

  const real = claims.filter(c => c.source === "bullet" || c.source === "title");

  return (
    <div>
      {real.map((c, i) => (
        <ClaimItem key={i} c={c} claimCheck={claimCheck} />
      ))}
    </div>
  );
}

// ─── Nutrition table ──────────────────────────────────────────────────────────

const NUTRIENT_DISPLAY = [
  ["energy_kcal",     "Energy",           "kcal"],
  ["protein_g",       "Protein",          "g"],
  ["carbohydrates_g", "Carbohydrates",    "g"],
  ["sugar_g",         "  Total Sugars",   "g"],
  ["added_sugar_g",   "  Added Sugars",   "g"],
  ["total_fat_g",     "Total Fat",        "g"],
  ["saturated_fat_g", "  Saturated Fat",  "g"],
  ["trans_fat_g",     "  Trans Fat",      "g"],
  ["dietary_fiber_g", "Dietary Fiber",    "g"],
  ["sodium_mg",       "Sodium",           "mg"],
  ["cholesterol_mg",  "Cholesterol",      "mg"],
];

function NutritionTable({ nutrition, servingSize }) {
  if (!nutrition || !Object.keys(nutrition).length) return (
    <p style={{ fontSize: 12, color: "#9ca3af", margin: 0 }}>
      Scan the nutrition label to extract values.
    </p>
  );

  const rows = NUTRIENT_DISPLAY.filter(([k]) => k in nutrition);

  return (
    <div style={{ fontSize: 12, fontFamily: "system-ui" }}>
      <div style={{ color: "#6b7280", marginBottom: 6, fontSize: 11 }}>
        Per 100g{servingSize ? ` · serving size ${servingSize}g` : ""}
      </div>
      {rows.map(([key, label, unit]) => (
        <div key={key} style={{
          display: "flex", justifyContent: "space-between",
          padding: "3px 0", borderBottom: "1px solid #f3f4f6", color: "#374151",
        }}>
          <span style={{ color: label.startsWith("  ") ? "#6b7280" : "#111" }}>{label.trim()}</span>
          <span style={{ fontWeight: 500 }}>{nutrition[key]} {unit}</span>
        </div>
      ))}
    </div>
  );
}

// ─── NutriScore panel ─────────────────────────────────────────────────────────

const GRADE_DESC = {
  A: "Excellent nutritional quality",
  B: "Good nutritional quality",
  C: "Average nutritional quality",
  D: "Poor nutritional quality",
  E: "Very poor nutritional quality",
};

function ScoreBar({ label, value, color, context }) {
  if (value == null) return null;
  const pct      = (value / 10) * 100;
  const barColor = value >= 7 ? "#16a34a" : value >= 5 ? "#f59e0b" : "#dc2626";
  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 2 }}>
        <span style={{ color: "#374151", fontWeight: 500 }}>{label}</span>
        <span style={{ fontWeight: 700, color: barColor }}>{value}/10</span>
      </div>
      <div style={{ background: "#e5e7eb", borderRadius: 4, height: 5, marginBottom: context ? 3 : 0 }}>
        <div style={{ width: `${pct}%`, background: barColor, borderRadius: 4, height: 5 }} />
      </div>
      {context && (
        <div style={{ fontSize: 10, color: "#6b7280" }}>{context}</div>
      )}
    </div>
  );
}

// Compute human-readable context for each score dimension
function scoreContext(scores, category) {
  const cat = category || "protein_powder";
  const MEDIANS = {
    protein_powder: 26, health_bar: 8, breakfast_cereal: 4, general: 10,
  };
  const median = MEDIANS[cat] || 26;

  return {
    value:     scores.value_score != null
      ? `Protein per ₹100 vs ${cat.replace("_"," ")} average (${median}g/₹100)`
      : null,
    quality:   "Based on protein %, sugar, saturated fat & sodium per 100g",
    integrity: "FSSAI compliance + numeric claim accuracy vs label",
  };
}

function AccountabilityScore({ scores }) {
  if (!scores?.total) return null;
  const total   = scores.total;
  const color   = total >= 7 ? "#16a34a" : total >= 5 ? "#f59e0b" : "#dc2626";
  const ctx     = scoreContext(scores, scores.category);

  return (
    <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, padding: "10px 12px", marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 13, color: "#111" }}>Accountability Score</div>
          <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 1 }}>value · quality · integrity</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <span style={{ fontWeight: 800, fontSize: 24, color }}>{total}</span>
          <span style={{ fontSize: 13, color: "#9ca3af" }}>/10</span>
        </div>
      </div>
      <ScoreBar label="Value for money"     value={scores.value_score}     context={ctx.value} />
      <ScoreBar label="Nutritional quality" value={scores.quality_score}   context={ctx.quality} />
      <ScoreBar label="Label integrity"     value={scores.integrity_score} context={ctx.integrity} />
      {scores.integrity_notes?.length > 0 && (
        <div style={{ marginTop: 8, borderTop: "1px solid #f3f4f6", paddingTop: 6 }}>
          {scores.integrity_notes.map((n, i) => (
            <div key={i} style={{ fontSize: 10, color: "#6b7280", marginBottom: 2 }}>
              {n.includes("not found") ? "⚠" : "✓"} {n}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function NutriScorePanel({ nutriscore, confidence }) {
  if (!nutriscore) return null;
  const { grade, score } = nutriscore;

  return (
    <div style={{
      display: "flex", gap: 10, alignItems: "center",
      background: "#f9fafb", borderRadius: 8, padding: "10px 12px",
    }}>
      <GradeBadge grade={grade} size={44} />
      <div>
        <div style={{ fontWeight: 700, fontSize: 14, color: "#111" }}>
          NutriScore {grade}
        </div>
        <div style={{ fontSize: 11, color: "#6b7280", marginTop: 1 }}>
          {GRADE_DESC[grade]}
        </div>
        <div style={{ fontSize: 11, color: "#6b7280", marginTop: 1 }}>
          Raw score: {score} · Confidence: {confidence || "—"}
        </div>
      </div>
    </div>
  );
}

// ─── Main product view ────────────────────────────────────────────────────────

function ProductView({ product, onScan, onCompare, compareSet, snipLoading }) {
  const analyzed     = product.status === "analyzed";
  const alreadyAdded = compareSet.some(p => p.platform_id === product.platform_id);
  const claimCount   = (product.claims || []).filter(
    c => c.source === "bullet" || c.source === "title"
  ).length;

  return (
    <div style={{ padding: "10px 12px", fontFamily: "system-ui" }}>

      {/* ── Header ── */}
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 10 }}>
        {analyzed && product.nutriscore && (
          <GradeBadge grade={product.nutriscore.grade} size={42} />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontWeight: 700, fontSize: 13, color: "#111", lineHeight: 1.35,
            overflow: "hidden", display: "-webkit-box",
            WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
          }}>
            {product.product_name || "Product"}
          </div>
          <div style={{ fontSize: 11, color: "#6b7280", marginTop: 3, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {product.brand    && <span>{product.brand}</span>}
            {product.quantity_g && <span>{product.quantity_g}g</span>}
            {product.price_inr  && <span>₹{product.price_inr.toLocaleString("en-IN")}</span>}
            {product.price_per_100g && <span>₹{product.price_per_100g}/100g</span>}
          </div>
          <div style={{ marginTop: 5, display: "flex", gap: 5, flexWrap: "wrap" }}>
            <FssaiBadge status={product.fssai_status} fssai={product.fssai} />
            {claimCount > 0 && (
              <Pill bg="#f3f4f6" color="#374151">{claimCount} claims found</Pill>
            )}
          </div>
        </div>
      </div>

      {/* ── Scan CTA (pre-scan) ── */}
      {!analyzed && (
        <button onClick={onScan} disabled={snipLoading} style={{
          width: "100%", background: snipLoading ? "#9ca3af" : "#16a34a",
          color: "#fff", border: "none", borderRadius: 7,
          padding: "10px 0", fontSize: 13, fontWeight: 600,
          cursor: snipLoading ? "default" : "pointer", marginBottom: 10,
        }}>
          {snipLoading ? "⏳ Scanning…" : "📷 Scan Nutrition Label to Verify Claims"}
        </button>
      )}

      {/* ── Accountability Score (after scan) ── */}
      {analyzed && product.scores?.total != null && (
        <AccountabilityScore scores={product.scores} />
      )}

      {/* ── NutriScore + action buttons (after scan) ── */}
      {analyzed && (
        <div style={{ display: "flex", gap: 8, alignItems: "stretch", marginBottom: 10 }}>
          {product.nutriscore && (
            <NutriScorePanel nutriscore={product.nutriscore} confidence={product.confidence} />
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginLeft: "auto" }}>
            <button onClick={onScan} style={{
              background: "none", border: "1px solid #d1d5db",
              borderRadius: 7, padding: "6px 12px", fontSize: 11,
              color: "#374151", cursor: "pointer", whiteSpace: "nowrap",
            }}>🔄 Re-scan</button>
            <button onClick={onCompare} disabled={alreadyAdded} style={{
              background: alreadyAdded ? "#d1fae5" : "#2563eb",
              color: alreadyAdded ? "#065f46" : "#fff",
              border: "none", borderRadius: 7,
              padding: "6px 12px", fontSize: 11, fontWeight: 600,
              cursor: alreadyAdded ? "default" : "pointer", whiteSpace: "nowrap",
            }}>
              {alreadyAdded ? "✓ Added" : "+ Compare"}
            </button>
          </div>
        </div>
      )}

      {/* ── Claims ── */}
      {claimCount > 0 && (
        <Section title={`Marketing Claims (${claimCount})`} defaultOpen={true}>
          <ClaimsList claims={product.claims} claimCheck={product.claim_check} />
        </Section>
      )}

      {/* ── Nutrition ── */}
      <Section
        title={analyzed ? "Nutrition Facts (per 100g)" : "Nutrition Facts"}
        defaultOpen={analyzed}
      >
        <NutritionTable nutrition={product.nutrition} servingSize={product.serving_size} />
      </Section>

      {/* ── ASIN debug line ── */}
      <div style={{ marginTop: 10, fontSize: 10, color: "#d1d5db", textAlign: "right" }}>
        ASIN: {product.platform_id}
      </div>

    </div>
  );
}

// ─── App shell ────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView]             = useState("home");
  const [product, setProduct]       = useState(null);
  const [compareSet, setCompareSet] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [snipLoading, setSnipLoading] = useState(false);

  useEffect(() => {
    init();
    const listener = (msg) => {
      if (msg.type === "PAGE_PRODUCT_AVAILABLE") loadPageProduct();
      if (msg.type === "FSSAI_RESULT") {
        setProduct(p => p?.platform_id === msg.platform_id
          ? { ...p, fssai: msg.fssai, fssai_status: msg.fssai_status } : p);
      }
      if (msg.type === "SCAN_COMPLETE") {
        setSnipLoading(false);
        setProduct(p => p?.platform_id === msg.platform_id ? { ...p, ...msg.data } : p);
        loadCompareSet();
      }
      if (msg.type === "SCORES_READY") {
        setProduct(p => p?.platform_id === msg.platform_id
          ? { ...p, scores: msg.scores, claim_check: msg.claim_check }
          : p
        );
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
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content_scripts/snip.js"] });
    window.close();
  }

  async function handleAddToCompare() {
    if (!product) return;
    const resp = await chrome.runtime.sendMessage({ type: "ADD_TO_COMPARE", platform_id: product.platform_id });
    if (resp?.ok) {
      await loadCompareSet();
      setProduct(p => ({ ...p }));
    } else if (resp?.error) {
      alert("NutriLens: " + resp.error);
    }
  }

  async function handleRemove(platform_id) {
    const resp = await chrome.runtime.sendMessage({ type: "REMOVE_FROM_COMPARE", platform_id });
    setCompareSet(resp?.set || []);
  }

  return (
    <div style={{ width: 380, minHeight: 200, background: "#f9fafb", fontFamily: "system-ui" }}>

      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", background: "#fff", borderBottom: "1px solid #e5e7eb",
        position: "sticky", top: 0, zIndex: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>🌿</span>
          <span style={{ fontWeight: 700, fontSize: 15, color: "#15803d" }}>NutriLens</span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <NavBtn active={view === "home"} onClick={() => setView("home")}>Home</NavBtn>
          <NavBtn active={view === "compare"} onClick={() => setView("compare")}>
            Compare{compareSet.length > 0 ? ` (${compareSet.length})` : ""}
          </NavBtn>
        </div>
      </div>

      {/* Content */}
      <div style={{ maxHeight: 560, overflowY: "auto" }}>
        {loading ? (
          <div style={{ padding: 24, textAlign: "center", color: "#9ca3af" }}>Loading…</div>
        ) : view === "home" ? (
          product ? (
            <ProductView
              product={product}
              onScan={startSnip}
              onCompare={handleAddToCompare}
              compareSet={compareSet}
              snipLoading={snipLoading}
            />
          ) : (
            <div style={{ padding: 32, textAlign: "center" }}>
              <div style={{ fontSize: 36, marginBottom: 8 }}>🔍</div>
              <div style={{ fontSize: 13, color: "#6b7280" }}>
                Open a food or supplement product page on Amazon.in
              </div>
            </div>
          )
        ) : (
          compareSet.length === 0 ? (
            <div style={{ padding: 32, textAlign: "center" }}>
              <div style={{ fontSize: 36, marginBottom: 8 }}>📊</div>
              <div style={{ fontSize: 13, color: "#6b7280" }}>
                Scan products and click "+ Add to Compare"
              </div>
            </div>
          ) : (
            <CompareTable
              products={compareSet}
              onRemove={handleRemove}
              onClearAll={async () => {
                await chrome.runtime.sendMessage({ type: "CLEAR_COMPARE" });
                setCompareSet([]);
              }}
            />
          )
        )}
      </div>
    </div>
  );
}

function NavBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      background: active ? "#dcfce7" : "none",
      color: active ? "#15803d" : "#6b7280",
      border: "none", borderRadius: 6,
      padding: "4px 10px", fontSize: 12,
      fontWeight: active ? 600 : 400,
      cursor: "pointer",
    }}>{children}</button>
  );
}