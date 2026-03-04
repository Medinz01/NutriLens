/**
 * background.js — NutriLens Service Worker
 *
 * Flow:
 *   1. Content script sends PRODUCT_EXTRACTED (DOM data + image URLs)
 *   2. Background calls OCR /extract/url to find FSSAI from gallery images
 *   3. Popup shows product + FSSAI status + "Scan Label" CTA
 *   4. User takes snippet → SNIP_CAPTURE → OCR /extract/image
 *   5. Background combines FSSAI + nutrition, calculates nutriscore
 *   6. Popup shows full analysis, Compare becomes available
 */

import { submitProduct } from "./utils/api.js";

const OCR_SERVICE   = "http://localhost:8001";
const MAX_COMPARE   = 5;

// ─── Storage helpers ──────────────────────────────────────────────────────────

async function sessionGet(key)        { return (await chrome.storage.session.get(key))[key] || null; }
async function sessionSet(key, val)   { await chrome.storage.session.set({ [key]: val }); }
async function localGet(key)          { return (await chrome.storage.local.get(key))[key] || null; }
async function localSet(key, val)     { await chrome.storage.local.set({ [key]: val }); }

async function getCompareSet()        { return (await localGet("compare_set")) || []; }
async function saveCompareSet(set)    { await localSet("compare_set", set); }

function broadcast(msg) {
  chrome.runtime.sendMessage(msg).catch(() => {});
}

// ─── Message router ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  switch (msg.type) {

    case "PRODUCT_EXTRACTED":
      handleProductExtracted(msg.payload).then(reply);
      return true;

    case "SNIP_CAPTURE":
      handleSnipCapture(msg, sender).then(reply);
      return true;

    case "GET_PAGE_PRODUCT":
      getPageProduct().then(reply);
      return true;

    case "SCROLL_TO_CLAIM":
      // Forward to content script on the active tab
      chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
        if (tab?.id) {
          chrome.tabs.sendMessage(tab.id, {
            type:         "SCROLL_TO_CLAIM",
            selector:     msg.selector,
            elementIndex: msg.elementIndex,
          });
        }
      });
      return false;

    case "ADD_TO_COMPARE":
      handleAddToCompare(msg.platform_id).then(reply);
      return true;

    case "GET_COMPARE_SET":
      getCompareSet().then(set => reply({ set }));
      return true;

    case "REMOVE_FROM_COMPARE":
      getCompareSet().then(set => {
        const updated = set.filter(p => p.platform_id !== msg.platform_id);
        saveCompareSet(updated).then(() => reply({ set: updated }));
      });
      return true;

    case "CLEAR_COMPARE":
      saveCompareSet([]).then(() => reply({ ok: true }));
      return true;
  }
});

// ─── Step 1: Product detected on page ────────────────────────────────────────

async function handleProductExtracted(payload) {
  const { platform_id } = payload;

  const fssai        = payload.fssai        || null;
  const fssai_status = payload.fssai_status || "not_found";

  // Merge — amazon.js sends twice: once immediately, once after FSSAI resolves
  const existing = (await sessionGet(`product:${platform_id}`)) || {};
  const merged = {
    ...existing,
    ...payload,
    fssai:        fssai || existing.fssai || null,
    fssai_status: fssai ? "found" : (existing.fssai ? "found" : fssai_status),
    nutrition:    existing.nutrition  || null,
    nutriscore:   existing.nutriscore || null,
    confidence:   existing.confidence || "low",
    status:       existing.status     || "awaiting_scan",
  };

  await sessionSet(`product:${platform_id}`, merged);

  // Notify popup
  broadcast({ type: "PAGE_PRODUCT_AVAILABLE", platform_id, preview: {
    platform_id,
    product_name:   payload.product_name,
    brand:          payload.brand,
    price_inr:      payload.price_inr,
    quantity_g:     payload.quantity_g,
    fssai:          merged.fssai,
    fssai_status:   merged.fssai_status,
    claims:         payload.claims || [],
    status:         merged.status,
  }});

  // POST to backend — fire and forget
  // Saves product + all claims to Postgres immediately, regardless of compare
  postToBackend(payload).catch(e =>
    console.warn("[NutriLens] Backend POST failed (is backend running?):", e.message)
  );

  return { ok: true };
}

const BACKEND = "http://localhost:8000/api/v1";

async function postToBackend(payload) {
  const resp = await fetch(`${BACKEND}/products/submit`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      platform:          payload.platform,
      platform_id:       payload.platform_id,
      url:               payload.url,
      product_name:      payload.product_name,
      brand:             payload.brand,
      price_inr:         payload.price_inr,
      quantity_g:        payload.quantity_g,
      price_per_100g:    payload.price_per_100g,
      serving_size_g:    payload.serving_size_g,
      nutrition_facts:   payload.nutrition_facts,
      claims:            payload.claims || [],
      claims_text:       payload.claims_text,
      ingredients_text:  payload.ingredients_text,
      fssai:             payload.fssai,
      primary_image_url: payload.primary_image_url,
      ocr_target_urls:   payload.ocr_target_urls,
      extraction_method: payload.extraction_method,
    }),
  });

  if (!resp.ok) {
    console.warn("[NutriLens] Backend rejected product:", payload.platform_id, await resp.text());
    return;
  }

  const result = await resp.json();
  console.log("[NutriLens] Saved to backend:", payload.platform_id, `(${(payload.claims||[]).length} claims)`);

  // If cached result returned immediately, merge scores now
  if (result.cached && result.data) {
    await mergeBackendScores(payload.platform_id, result.data);
    return;
  }

  // Otherwise poll job until complete
  if (result.job_id) {
    pollJob(result.job_id, payload.platform_id);
  }
}

async function pollJob(jobId, platform_id, attempts = 0) {
  const MAX_ATTEMPTS = 20;   // 20 × 2s = 40s timeout
  const INTERVAL_MS  = 2000;

  if (attempts >= MAX_ATTEMPTS) {
    console.warn("[NutriLens] Job timed out:", jobId);
    return;
  }

  await new Promise(r => setTimeout(r, INTERVAL_MS));

  try {
    const resp = await fetch(`${BACKEND}/jobs/${jobId}`);
    if (!resp.ok) return;

    const job = await resp.json();

    if (job.status === "complete" && job.data) {
      console.log("[NutriLens] Job complete — merging scores for", platform_id);
      await mergeBackendScores(platform_id, job.data);
    } else if (job.status === "failed") {
      console.warn("[NutriLens] Job failed:", jobId, job.error);
    } else {
      // Still processing — keep polling
      pollJob(jobId, platform_id, attempts + 1);
    }
  } catch (e) {
    console.warn("[NutriLens] Poll error:", e.message);
  }
}

async function mergeBackendScores(platform_id, backendData) {
  // Merge backend scores/analysis into session product
  const existing = (await sessionGet(`product:${platform_id}`)) || {};
  const merged = {
    ...existing,
    scores:       backendData.scores       || existing.scores,
    claim_check:  backendData.claim_check  || existing.claim_check,
  };
  await sessionSet(`product:${platform_id}`, merged);

  // Notify popup so it re-renders with scores
  broadcast({ type: "SCORES_READY", platform_id, scores: backendData.scores, claim_check: backendData.claim_check });
  console.log("[NutriLens] Scores merged for", platform_id, "total:", backendData.scores?.total);
}

async function extractFssai(platform_id, imageUrls) {
  if (!imageUrls.length) {
    await updateProduct(platform_id, { fssai_status: "not_found" });
    broadcast({ type: "FSSAI_RESULT", platform_id, fssai: null, fssai_status: "not_found" });
    return;
  }

  try {
    const resp = await fetch(`${OCR_SERVICE}/extract/url`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ urls: imageUrls }),
    });

    if (resp.ok) {
      const data = await resp.json();
      const fssai       = data.fssai || null;
      const fssai_status = fssai ? "found" : "not_found";

      await updateProduct(platform_id, { fssai, fssai_status });
      broadcast({ type: "FSSAI_RESULT", platform_id, fssai, fssai_status });
    } else {
      await updateProduct(platform_id, { fssai_status: "not_found" });
      broadcast({ type: "FSSAI_RESULT", platform_id, fssai: null, fssai_status: "not_found" });
    }
  } catch (e) {
    console.warn("[NutriLens] FSSAI extraction failed:", e.message);
    await updateProduct(platform_id, { fssai_status: "not_found" });
    broadcast({ type: "FSSAI_RESULT", platform_id, fssai: null, fssai_status: "not_found" });
  }
}

// ─── Step 2: User takes snippet ───────────────────────────────────────────────

async function handleSnipCapture({ rect, devicePixelRatio }, sender) {
  const tabId = sender.tab.id;

  try {
    // Screenshot visible tab
    const dataUrl = await chrome.tabs.captureVisibleTab(
      sender.tab.windowId, { format: "png" }
    );

    // Crop to selection
    const dpr    = devicePixelRatio || 1;
    const blob   = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);

    const canvas = new OffscreenCanvas(
      Math.round(rect.w * dpr), Math.round(rect.h * dpr)
    );
    const ctx = canvas.getContext("2d");
    ctx.drawImage(
      bitmap,
      Math.round(rect.x * dpr), Math.round(rect.y * dpr),
      Math.round(rect.w * dpr), Math.round(rect.h * dpr),
      0, 0,
      Math.round(rect.w * dpr), Math.round(rect.h * dpr)
    );

    // Base64 encode (chunked — avoids call stack overflow)
    const cropBlob  = await canvas.convertToBlob({ type: "image/jpeg", quality: 0.95 });
    const arrayBuf  = await cropBlob.arrayBuffer();
    const bytes     = new Uint8Array(arrayBuf);
    let binary      = "";
    const CHUNK     = 8192;
    for (let i = 0; i < bytes.length; i += CHUNK) {
      binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
    }
    const base64 = btoa(binary);

    // Send to OCR service
    const ocrResp = await fetch(`${OCR_SERVICE}/extract/image`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ image: base64, mime_type: "image/jpeg" }),
    });

    if (!ocrResp.ok) {
      const err = await ocrResp.text();
      return { error: `OCR error: ${err}` };
    }

    const ocrData = await ocrResp.json();

    // Find which product is on this tab
    const platform_id = await getPlatformIdForTab(tabId);

    if (platform_id) {
      const product = await sessionGet(`product:${platform_id}`);
      const fssai   = ocrData.fssai || product?.fssai || null;

      // Calculate nutriscore
      const nutriscore = calcNutriScore(ocrData.nutrition || {}, ocrData.serving_size);
      const confidence = calcConfidence(ocrData.nutrition || {}, ocrData.serving_size);

      const enriched = {
        nutrition:    ocrData.nutrition,
        serving_size: ocrData.serving_size,
        ingredients:  ocrData.ingredients,
        fssai,
        fssai_status: fssai ? "found" : (product?.fssai_status || "not_found"),
        nutriscore,
        confidence,
        status:       "analyzed",
      };

      await updateProduct(platform_id, enriched);

      broadcast({
        type: "SCAN_COMPLETE",
        platform_id,
        data: enriched,
      });
    }

    return { ok: true };

  } catch (err) {
    console.error("[NutriLens] Snip failed:", err);
    return { error: err.message };
  }
}

// ─── Step 3: Add to Compare ───────────────────────────────────────────────────

async function handleAddToCompare(platform_id) {
  const product = await sessionGet(`product:${platform_id}`);
  if (!product) return { ok: false, error: "No product data found" };
  if (product.status !== "analyzed") return { ok: false, error: "Scan the nutrition label first" };

  const set = await getCompareSet();
  if (set.find(p => p.platform_id === platform_id)) return { ok: false, reason: "duplicate" };
  if (set.length >= MAX_COMPARE) return { ok: false, reason: "limit_reached" };

  const entry = {
    platform_id,
    product_name:  product.product_name,
    brand:         product.brand,
    price_inr:     product.price_inr,
    quantity_g:    product.quantity_g,
    nutrition:     product.nutrition,
    serving_size:  product.serving_size,
    ingredients:   product.ingredients,
    fssai:         product.fssai,
    fssai_status:  product.fssai_status,
    nutriscore:    product.nutriscore,
    confidence:    product.confidence,
    status:        "ready",
  };

  await saveCompareSet([...set, entry]);
  return { ok: true, count: set.length + 1 };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function getPageProduct() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return { product: null };
  const m = tab.url.match(/\/dp\/([A-Z0-9]{10})/);
  if (!m) return { product: null };
  const product = await sessionGet(`product:${m[1]}`);
  return { product };
}

async function getPlatformIdForTab(tabId) {
  const tab = await chrome.tabs.get(tabId);
  const m   = tab?.url?.match(/\/dp\/([A-Z0-9]{10})/);
  return m ? m[1] : null;
}

async function updateProduct(platform_id, patch) {
  const existing = (await sessionGet(`product:${platform_id}`)) || {};
  await sessionSet(`product:${platform_id}`, { ...existing, ...patch });
}

// ─── NutriScore ───────────────────────────────────────────────────────────────

function calcNutriScore(nutrition, servingSize) {
  // OCR parser extracts per-100g values directly — no normalisation needed.
  // NutriScore is always calculated on per-100g basis (FSSAI / EU standard).
  const energy  = nutrition.energy_kcal     || 0;
  const satFat  = nutrition.saturated_fat_g || 0;
  const sugar   = nutrition.sugar_g         || 0;
  const sodium  = nutrition.sodium_mg       || 0;
  const protein = nutrition.protein_g       || 0;
  const fiber   = nutrition.dietary_fiber_g || 0;

  const neg =
    pts(energy,  [80,160,240,320,400,480,560,640,720,800]) +
    pts(satFat,  [1,2,3,4,5,6,7,8,9,10]) +
    pts(sugar,   [4.5,9,13.5,18,22.5,27,31,36,40,45]) +
    pts((sodium * 2.5 / 1000), [0.2,0.4,0.6,0.8,1.0,1.2,1.4,1.6,1.8,2.0]);

  const pos =
    pts(protein, [1.6,3.2,4.8,6.4,8.0]) +
    pts(fiber,   [0.9,1.9,2.8,3.7,4.7]);

  const score = neg >= 11 ? neg - pts(fiber, [0.9,1.9,2.8,3.7,4.7]) : neg - pos;

  return {
    score,
    grade: score <= -1 ? "A" : score <= 2 ? "B" : score <= 10 ? "C" : score <= 18 ? "D" : "E",
  };
}

function pts(val, thresholds) {
  let p = 0;
  for (const t of thresholds) { if (val > t) p++; else break; }
  return p;
}

function calcConfidence(nutrition, servingSize) {
  const count      = Object.keys(nutrition).length;
  const hasProtein = "protein_g"    in nutrition;
  const hasEnergy  = "energy_kcal"  in nutrition;
  if (count >= 6 && hasProtein && hasEnergy && servingSize) return "high";
  if (count >= 3 || (hasProtein && hasEnergy))              return "medium";
  return "low";
}