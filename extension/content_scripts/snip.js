/**
 * snip.js — Snippet capture overlay.
 *
 * Injected by background.js when user clicks "Scan Label".
 * Draws a full-screen overlay, user drags a selection box,
 * on mouseup → captures that region and sends to background.
 */

(function () {
  // Don't inject twice
  if (document.getElementById("nutrilens-snip-overlay")) return;

  // ─── State ───────────────────────────────────────────────────────────────
  let startX, startY, isDragging = false;

  // ─── DOM ─────────────────────────────────────────────────────────────────
  const overlay = document.createElement("div");
  overlay.id = "nutrilens-snip-overlay";
  Object.assign(overlay.style, {
    position:   "fixed",
    inset:      "0",
    zIndex:     "2147483647",
    cursor:     "crosshair",
    background: "rgba(0,0,0,0.35)",
  });

  const selection = document.createElement("div");
  Object.assign(selection.style, {
    position:   "absolute",
    border:     "2px solid #22c55e",
    background: "rgba(34,197,94,0.08)",
    display:    "none",
    boxSizing:  "border-box",
  });

  const hint = document.createElement("div");
  hint.textContent = "Drag to select the nutrition table — release to scan";
  Object.assign(hint.style, {
    position:    "fixed",
    top:         "16px",
    left:        "50%",
    transform:   "translateX(-50%)",
    background:  "#1a1a1a",
    color:       "#f0f0f0",
    padding:     "8px 18px",
    borderRadius:"8px",
    fontSize:    "14px",
    fontFamily:  "system-ui, sans-serif",
    pointerEvents:"none",
    zIndex:      "2147483647",
    whiteSpace:  "nowrap",
  });

  const cancelBtn = document.createElement("button");
  cancelBtn.textContent = "✕  Cancel";
  Object.assign(cancelBtn.style, {
    position:    "fixed",
    top:         "16px",
    right:       "20px",
    background:  "#ef4444",
    color:       "#fff",
    border:      "none",
    borderRadius:"6px",
    padding:     "7px 14px",
    fontSize:    "13px",
    fontFamily:  "system-ui, sans-serif",
    cursor:      "pointer",
    zIndex:      "2147483647",
  });

  overlay.appendChild(selection);
  document.body.appendChild(overlay);
  document.body.appendChild(hint);
  document.body.appendChild(cancelBtn);

  // ─── Cancel ──────────────────────────────────────────────────────────────
  function cleanup() {
    overlay.remove();
    hint.remove();
    cancelBtn.remove();
  }

  cancelBtn.addEventListener("click", cleanup);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") cleanup();
  }, { once: true });

  // ─── Drag ────────────────────────────────────────────────────────────────
  overlay.addEventListener("mousedown", (e) => {
    e.preventDefault();
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    Object.assign(selection.style, {
      left:    startX + "px",
      top:     startY + "px",
      width:   "0px",
      height:  "0px",
      display: "block",
    });
  });

  overlay.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const x = Math.min(e.clientX, startX);
    const y = Math.min(e.clientY, startY);
    const w = Math.abs(e.clientX - startX);
    const h = Math.abs(e.clientY - startY);
    Object.assign(selection.style, {
      left: x + "px", top: y + "px",
      width: w + "px", height: h + "px",
    });
  });

  overlay.addEventListener("mouseup", async (e) => {
    if (!isDragging) return;
    isDragging = false;

    const rect = {
      x: Math.min(e.clientX, startX),
      y: Math.min(e.clientY, startY),
      w: Math.abs(e.clientX - startX),
      h: Math.abs(e.clientY - startY),
    };

    if (rect.w < 20 || rect.h < 20) {
      cleanup();
      return;
    }

    // Show scanning state
    hint.textContent = "Scanning…";
    selection.style.borderColor = "#facc15";

    // Ask background to capture + OCR
    chrome.runtime.sendMessage({
      type: "SNIP_CAPTURE",
      rect,
      devicePixelRatio: window.devicePixelRatio || 1,
    }, (response) => {
      cleanup();
      if (response?.error) {
        alert("NutriLens: " + response.error);
      }
    });
  });
})();