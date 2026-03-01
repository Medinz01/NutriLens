/**
 * api.js — NutriLens Backend Communication
 *
 * All fetch calls to the FastAPI backend go through here.
 * Handles: request construction, error normalization, timeout.
 */

// ─── Config ──────────────────────────────────────────────────────────────────

// In development, point to local FastAPI server.
// In production, replace with your deployed API URL.
const API_BASE = "http://localhost:8000";

const DEFAULT_TIMEOUT_MS = 10000; // 10s for synchronous calls

// ─── Core Fetch Wrapper ──────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        "X-NutriLens-Version": "0.1.0",
        ...options.headers,
      },
      signal: controller.signal,
      ...options,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({}));
      throw new APIError(res.status, errorBody.detail || "Unknown error");
    }

    return await res.json();

  } catch (err) {
    clearTimeout(timeoutId);

    if (err.name === "AbortError") {
      throw new APIError(408, "Request timed out");
    }
    if (err instanceof APIError) throw err;

    // Network failure (offline, CORS, etc.)
    throw new APIError(0, "Network error: " + err.message);
  }
}

class APIError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
    this.name = "APIError";
  }
}

// ─── API Methods ─────────────────────────────────────────────────────────────

/**
 * Submit extracted product data for ML analysis.
 *
 * Returns one of:
 *   { cached: true, data: {...} }         — Cache hit, immediate result
 *   { cached: false, job_id: "xxx" }      — Cache miss, async job started
 */
export async function submitProduct(extractedPayload) {
  return apiFetch("/api/v1/products/submit", {
    method: "POST",
    body: JSON.stringify(extractedPayload),
  });
}

/**
 * Poll for async job completion.
 *
 * Returns:
 *   { status: "queued" | "processing" | "complete" | "failed", data?, error?, eta_seconds? }
 */
export async function pollJobStatus(jobId) {
  return apiFetch(`/api/v1/jobs/${jobId}/status`);
}

/**
 * Rank a set of products (by platform_id) against each other.
 * Used by popup when user clicks "Compare".
 */
export async function rankProducts(platformIds) {
  return apiFetch("/api/v1/products/rank", {
    method: "POST",
    body: JSON.stringify({ platform_ids: platformIds }),
  });
}

/**
 * Get full enriched product data by platform + platform_id.
 * Used to re-hydrate comparison set after SW restart.
 */
export async function getProduct(platform, platformId) {
  return apiFetch(`/api/v1/products/${platform}/${platformId}`);
}

/**
 * Health check — used to detect if backend is reachable.
 */
export async function healthCheck() {
  try {
    await apiFetch("/health", { timeout: 3000 });
    return true;
  } catch {
    return false;
  }
}