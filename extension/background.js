/**
 * background.js — NutriLens Service Worker (Manifest V3)
 *
 * Responsibilities:
 * 1. Receive PRODUCT_EXTRACTED messages from content scripts
 * 2. Submit product to backend API (or queue if offline)
 * 3. Poll for job completion with exponential backoff
 * 4. Persist comparison set to chrome.storage.local
 * 5. Notify popup when data is ready
 */

import { submitProduct, pollJobStatus } from "./utils/api.js";

// ─── Constants ───────────────────────────────────────────────────────────────

const POLL_INTERVALS_MS = [2000, 4000, 8000, 12000, 15000, 15000, 15000, 15000, 15000, 15000];
const MAX_COMPARISON_ITEMS = 5;

// ─── Storage Helpers ─────────────────────────────────────────────────────────

async function getComparisonSet() {
  const result = await chrome.storage.local.get(["comparison_set"]);
  return result.comparison_set || [];
}

async function saveComparisonSet(set) {
  await chrome.storage.local.set({ comparison_set: set });
}

async function addToComparisonSet(product) {
  const current = await getComparisonSet();

  // Deduplicate by platform_id
  const exists = current.find(p => p.platform_id === product.platform_id);
  if (exists) {
    console.log("[NutriLens] Product already in comparison set:", product.platform_id);
    return { added: false, reason: "duplicate" };
  }

  if (current.length >= MAX_COMPARISON_ITEMS) {
    return { added: false, reason: "limit_reached", limit: MAX_COMPARISON_ITEMS };
  }

  const updated = [...current, product];
  await saveComparisonSet(updated);
  return { added: true, count: updated.length };
}

async function removeFromComparisonSet(platformId) {
  const current = await getComparisonSet();
  const updated = current.filter(p => p.platform_id !== platformId);
  await saveComparisonSet(updated);
  return updated;
}

async function clearComparisonSet() {
  await saveComparisonSet([]);
}

// ─── Job State ───────────────────────────────────────────────────────────────
// In-memory only — jobs don't need to survive service worker restarts.
// If SW restarts mid-poll, the popup will re-trigger via PRODUCT_EXTRACTED.

const activeJobs = new Map(); // platformId → { jobId, status, result }

// ─── Polling Logic ───────────────────────────────────────────────────────────

async function startPolling(platformId, jobId) {
  console.log(`[NutriLens] Starting poll for job ${jobId}`);

  for (let attempt = 0; attempt < POLL_INTERVALS_MS.length; attempt++) {
    const delay = POLL_INTERVALS_MS[attempt];
    await sleep(delay);

    try {
      const result = await pollJobStatus(jobId);
      console.log(`[NutriLens] Poll attempt ${attempt + 1}:`, result.status);

      if (result.status === "complete") {
        activeJobs.set(platformId, { jobId, status: "complete", result: result.data });

        // Update the stored product with enriched data
        await updateProductInSet(platformId, result.data);

        // Notify any open popups
        chrome.runtime.sendMessage({
          type: "PRODUCT_READY",
          platform_id: platformId,
          data: result.data
        }).catch(() => {}); // Popup may not be open — ignore

        return;
      }

      if (result.status === "failed") {
        activeJobs.set(platformId, { jobId, status: "failed", error: result.error });
        chrome.runtime.sendMessage({
          type: "PRODUCT_FAILED",
          platform_id: platformId,
          error: result.error
        }).catch(() => {});
        return;
      }

      // Still queued/processing — continue polling

    } catch (err) {
      console.error(`[NutriLens] Poll error attempt ${attempt + 1}:`, err);
    }
  }

  // Exhausted all attempts
  activeJobs.set(platformId, { jobId, status: "timeout" });
  chrome.runtime.sendMessage({
    type: "PRODUCT_FAILED",
    platform_id: platformId,
    error: "Analysis timed out. Try again."
  }).catch(() => {});
}

async function updateProductInSet(platformId, enrichedData) {
  const current = await getComparisonSet();
  const updated = current.map(p =>
    p.platform_id === platformId
      ? { ...p, ...enrichedData, status: "ready" }
      : p
  );
  await saveComparisonSet(updated);
}

// ─── Message Handler ─────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const { type } = message;

  // ── Popup → background: get product detected on current tab
  if (type === "GET_PAGE_PRODUCT") {
    getCurrentTabProduct().then(sendResponse);
    return true;
  }

  // ── Content script → background: new product detected on page
  if (type === "PRODUCT_EXTRACTED") {
    handleProductExtracted(message.payload).then(sendResponse);
    return true; // Keep channel open for async response
  }

  // ── Popup → background: user clicked "Add to Compare"
  if (type === "ADD_TO_COMPARE") {
    handleAddToCompare(message.platform_id).then(sendResponse);
    return true;
  }

  // ── Popup → background: get current comparison set
  if (type === "GET_COMPARISON_SET") {
    getComparisonSet().then(set => sendResponse({ set }));
    return true;
  }

  // ── Popup → background: remove product from set
  if (type === "REMOVE_FROM_SET") {
    removeFromComparisonSet(message.platform_id).then(set => sendResponse({ set }));
    return true;
  }

  // ── Popup → background: clear all
  if (type === "CLEAR_SET") {
    clearComparisonSet().then(() => sendResponse({ ok: true }));
    return true;
  }

  // ── Popup → background: get status of a specific product's job
  if (type === "GET_JOB_STATUS") {
    const job = activeJobs.get(message.platform_id) || { status: "unknown" };
    sendResponse(job);
    return false;
  }
});

async function getCurrentTabProduct() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return { product: null };

  // Extract ASIN from current tab URL
  const dpMatch  = tab.url.match(/\/dp\/([A-Z0-9]{10})/);
  const gpMatch  = tab.url.match(/\/gp\/product\/([A-Z0-9]{10})/);
  const platformId = dpMatch?.[1] || gpMatch?.[1];

  if (platformId) {
    const product = await getPendingProduct(platformId);
    if (product) return { product };
  }

  // Fallback: scan all pending products for URL match
  const all = await getAllPendingProducts();
  for (const product of Object.values(all)) {
    if (product.url === tab.url) return { product };
  }

  return { product: null };
}

async function getCurrentTabPlatformId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return null;
  const match = tab.url.match(/\/dp\/([A-Z0-9]{10})/);
  return match ? match[1] : null;
}

// ─── Handlers ────────────────────────────────────────────────────────────────

// ─── Pending Products (session-persisted) ────────────────────────────────────
// MV3 service workers go to sleep and lose in-memory state.
// chrome.storage.session persists for the browser session but survives SW restarts.

async function setPendingProduct(platformId, product) {
  const key = `pending:${platformId}`;
  await chrome.storage.session.set({ [key]: product });
}

async function getPendingProduct(platformId) {
  const key = `pending:${platformId}`;
  const result = await chrome.storage.session.get(key);
  return result[key] || null;
}

async function getAllPendingProducts() {
  const all = await chrome.storage.session.get(null);
  const pending = {};
  for (const [key, val] of Object.entries(all)) {
    if (key.startsWith("pending:")) {
      const platformId = key.replace("pending:", "");
      pending[platformId] = val;
    }
  }
  return pending;
}

async function handleProductExtracted(payload) {
  const { platform_id } = payload;

  // Persist to session storage — survives service worker sleep/restart
  await setPendingProduct(platform_id, payload);

  // Signal popup that a product is available on this page
  chrome.runtime.sendMessage({
    type: "PAGE_PRODUCT_AVAILABLE",
    platform_id,
    preview: {
      platform_id,
      product_name: payload.product_name,
      brand: payload.brand,
      price_inr: payload.price_inr,
      quantity_g: payload.quantity_g,
      nutrition_confidence: payload.nutrition_confidence,
    }
  }).catch(() => {});

  return { ok: true };
}

async function handleAddToCompare(platformId) {
  const product = await getPendingProduct(platformId);
  if (!product) {
    return { ok: false, error: "No product data found. Refresh the page and try again." };
  }

  // Deduplicate check
  const current = await getComparisonSet();
  const exists = current.find(p => p.platform_id === platformId);
  if (exists) return { ok: false, reason: "duplicate" };

  if (current.length >= MAX_COMPARISON_ITEMS) {
    return { ok: false, reason: "limit_reached", limit: MAX_COMPARISON_ITEMS };
  }

  // Add to set immediately with "processing" status — respond to popup right away
  const updated = [...current, { ...product, status: "processing" }];
  await saveComparisonSet(updated);

  // Do the HTTP call AFTER responding (fire and forget from popup's perspective)
  submitToBackend(product, platformId);

  return { ok: true };
}

// Separated so it runs after sendResponse is called
async function submitToBackend(product, platformId) {
  try {
    const response = await submitProduct(product);

    if (response.cached) {
      await updateProductInSet(platformId, { ...response.data, status: "ready" });
      chrome.runtime.sendMessage({
        type: "PRODUCT_READY",
        platform_id: platformId,
        data: response.data
      }).catch(() => {});
      return;
    }

    if (response.job_id) {
      activeJobs.set(platformId, { jobId: response.job_id, status: "processing" });
      startPolling(platformId, response.job_id);
    }

  } catch (err) {
    console.error("[NutriLens] Backend unreachable:", err);
    await updateProductInSet(platformId, { status: "failed", error: "Backend unreachable" });
    chrome.runtime.sendMessage({
      type: "PRODUCT_FAILED",
      platform_id: platformId,
      error: "Backend unreachable. Is Docker running?"
    }).catch(() => {});
  }
}

// ─── Utilities ───────────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}