/**
 * amazon.js — NutriLens Content Script for Amazon.in
 *
 * Extracts on every product page load:
 *   - ASIN, product name, brand, price, quantity
 *   - Nutrition facts (from DOM table)
 *   - Structured claims (each bullet as individual claim)
 *   - Ingredients text
 *   - FSSAI from seller About page
 *   - Gallery image URLs (for optional OCR later)
 *
 * Sends to background.js → background immediately POSTs to backend.
 */

(function () {
  "use strict";

  // ─── Utilities ──────────────────────────────────────────────────────────────

  function queryText(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el?.textContent.trim()) return el.textContent.trim();
    }
    return null;
  }

  function parsePrice(raw) {
    if (!raw) return null;
    const cleaned = raw.replace(/[₹,\s]/g, "").replace(/Rs\.?/g, "");
    const val = parseFloat(cleaned);
    return isNaN(val) ? null : val;
  }

  function parseQuantityToGrams(raw) {
    if (!raw) return null;
    const str = raw.toLowerCase().trim();
    const match = str.match(/([\d.]+)\s*(kg|g|l|ml|ltr|litre|liter)/);
    if (!match) return null;
    const value = parseFloat(match[1]);
    const conversions = { kg: 1000, g: 1, l: 1000, ml: 1, ltr: 1000, litre: 1000, liter: 1000 };
    return value * (conversions[match[2]] || 1);
  }

  // ─── ASIN ────────────────────────────────────────────────────────────────────

  function extractASIN() {
    // URL patterns
    const patterns = [
      /\/dp\/([A-Z0-9]{10})/,
      /\/gp\/product\/([A-Z0-9]{10})/,
    ];
    for (const p of patterns) {
      const m = window.location.pathname.match(p);
      if (m) return m[1];
    }
    // DOM fallback
    return document.querySelector("[data-asin]")?.getAttribute("data-asin")
        || document.querySelector("#ASIN")?.value
        || null;
  }

  // ─── Product identity ────────────────────────────────────────────────────────

  function extractProductName() {
    return queryText(["#productTitle", "#title span", "h1.a-size-large"])
      ?.replace(/\s+/g, " ").trim() || null;
  }

  function extractBrand() {
    // Detail table rows
    const rows = document.querySelectorAll(
      "#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr"
    );
    for (const row of rows) {
      const th = row.querySelector("th");
      const td = row.querySelector("td");
      if (th && /brand/i.test(th.textContent) && td) {
        return td.textContent.trim();
      }
    }
    return queryText(["#bylineInfo", "#brand", "a#bylineInfo"])
      ?.replace(/^(Brand:|Visit the|Store)?\s*/i, "").trim() || null;
  }

  function extractPrice() {
    const wholeEl    = document.querySelector(
      "#corePriceDisplay_desktop_feature_div .a-price-whole, " +
      "#corePrice_feature_div .a-price-whole, .a-price-whole"
    );
    const fractionEl = document.querySelector(
      "#corePriceDisplay_desktop_feature_div .a-price-fraction, " +
      "#corePrice_feature_div .a-price-fraction, .a-price-fraction"
    );
    if (wholeEl) {
      const whole    = wholeEl.textContent.replace(/[^0-9]/g, "");
      const fraction = fractionEl
        ? fractionEl.textContent.replace(/[^0-9]/g, "").substring(0, 2).padEnd(2, "0")
        : "00";
      const val = parseFloat(`${whole}.${fraction}`);
      if (!isNaN(val) && val > 0 && val < 500000) return val;
    }
    for (const sel of [
      "#corePriceDisplay_desktop_feature_div .a-offscreen",
      "#corePrice_feature_div .a-offscreen",
      "#priceblock_ourprice",
    ]) {
      const price = parsePrice(document.querySelector(sel)?.textContent);
      if (price && price > 0) return price;
    }
    return null;
  }

  function extractQuantity() {
    const detailRows = document.querySelectorAll(
      "#productDetails_techSpec_section_1 tr, " +
      "#productDetails_techSpec_section_2 tr, " +
      "#productDetails_detailBullets_sections1 tr, " +
      ".a-keyvalue tr"
    );
    const keys = /net quantity|item weight|package weight|net weight|size|volume/i;
    for (const row of detailRows) {
      const th = row.querySelector("th, .a-span3 span");
      const td = row.querySelector("td, .a-span9 span");
      if (th && keys.test(th.textContent) && td) {
        const g = parseQuantityToGrams(td.textContent);
        if (g) return g;
      }
    }
    return parseQuantityToGrams(extractProductName() || "");
  }

  // ─── Nutrition facts ─────────────────────────────────────────────────────────

  const NUTRIENT_PATTERNS = {
    energy_kcal:     /energy|calories|kcal/,
    protein_g:       /protein/,
    total_fat_g:     /total fat/,
    saturated_fat_g: /saturated fat|saturated fatty/,
    trans_fat_g:     /trans fat|trans fatty/,
    carbohydrates_g: /carbohydrate|carbs/,
    sugar_g:         /total sugar|sugars/,
    added_sugar_g:   /added sugar/,
    dietary_fiber_g: /fiber|fibre/,
    sodium_mg:       /sodium/,
    cholesterol_mg:  /cholesterol/,
  };

  function extractNutritionFacts() {
    const facts = {};

    // Strategy 1: HTML tables containing "protein" or "energy"
    for (const table of document.querySelectorAll("table")) {
      const txt = table.textContent.toLowerCase();
      if (!txt.includes("protein") && !txt.includes("energy") && !txt.includes("calor")) continue;

      for (const row of table.querySelectorAll("tr")) {
        const cells = row.querySelectorAll("td, th");
        if (cells.length < 2) continue;
        const label = cells[0].textContent.toLowerCase().trim();
        const value = cells[1].textContent.trim();
        for (const [key, pat] of Object.entries(NUTRIENT_PATTERNS)) {
          if (pat.test(label) && !(key in facts)) {
            const num = parseFloat(value.replace(/[^\d.]/g, ""));
            if (!isNaN(num)) facts[key] = num;
            break;
          }
        }
      }
      if (Object.keys(facts).length > 2) break;
    }

    // Strategy 2: feature bullets / description text
    if (Object.keys(facts).length === 0) {
      const text = queryText(["#feature-bullets", "#productDescription", "#aplus"]) || "";
      const patterns = [
        { key: "protein_g",       regex: /([\d.]+)\s*g\s*protein|protein[:\s]+([\d.]+)\s*g/i },
        { key: "energy_kcal",     regex: /([\d.]+)\s*kcal|calories[:\s]+([\d.]+)/i },
        { key: "sugar_g",         regex: /([\d.]+)\s*g\s*sugar|sugar[:\s]+([\d.]+)\s*g/i },
        { key: "total_fat_g",     regex: /([\d.]+)\s*g\s*fat|fat[:\s]+([\d.]+)\s*g/i },
        { key: "carbohydrates_g", regex: /([\d.]+)\s*g\s*carb|carbohydrate[:\s]+([\d.]+)\s*g/i },
      ];
      for (const { key, regex } of patterns) {
        const m = text.match(regex);
        if (m) {
          const v = parseFloat(m[1] || m[2]);
          if (!isNaN(v)) facts[key] = v;
        }
      }
    }

    return Object.keys(facts).length > 0 ? facts : null;
  }

  function extractServingSize() {
    for (const table of document.querySelectorAll("table")) {
      for (const row of table.querySelectorAll("tr")) {
        if (/serving size/i.test(row.textContent)) {
          const m = row.textContent.match(/([\d.]+)\s*g/i);
          if (m) return parseFloat(m[1]);
        }
      }
    }
    return null;
  }

  // ─── Structured claims ───────────────────────────────────────────────────────
  // Each bullet point / headline is stored as a separate claim.
  // The backend will classify and verify each one independently.

  // UI noise patterns — these are Amazon page chrome, not product claims
  const NOISE_PATTERNS = [
    /^sorry,?\s+there was a problem/i,
    /^save extra with/i,
    /^non-returnable/i,
    /^purchase options/i,
    /^frequently bought/i,
    /^customers who viewed/i,
    /^customers say/i,
    /^explore more/i,
    /^important information$/i,
    /^product description$/i,
    /^product information$/i,
    /^product details$/i,
    /^where did you see/i,
    /^related products/i,
    /^customer reviews$/i,
    /^reviews with images/i,
    /^top reviews from/i,
    /^about this item$/i,
    /^options available$/i,
    /^flavour name$/i,
    /^safety information:?$/i,
    /^ingredients:?$/i,
    /^directions:?$/i,
    /^feedback$/i,
    /^sponsored$/i,
    /^add to cart$/i,
    /^buy now$/i,
    /^\d+ offers?$/i,
  ];

  function isNoiseClaim(text) {
    if (text.length < 15) return true;  // too short to be a real claim
    return NOISE_PATTERNS.some(p => p.test(text.trim()));
  }

  function extractClaims() {
    const claims = [];

    // Feature bullets — store elementIndex so popup can scroll to them
    const bulletContainer = document.querySelector("#feature-bullets");
    if (bulletContainer) {
      const bulletEls = bulletContainer.querySelectorAll("li span.a-list-item");
      bulletEls.forEach((el, idx) => {
        const text = el.textContent.trim().replace(/\s+/g, " ");
        if (!isNoiseClaim(text) && text.length < 600) {
          claims.push({
            source:       "bullet",
            text,
            elementIndex: idx,          // index within #feature-bullets li span
            selector:     "#feature-bullets li span.a-list-item",
          });
        }
      });
    }

    // Product title
    const title = extractProductName();
    if (title && !isNoiseClaim(title)) {
      claims.push({
        source:   "title",
        text:     title,
        selector: "#productTitle",
      });
    }

    // A+ content headlines
    const aplusEls = document.querySelectorAll("#aplus h3, #aplus h4");
    aplusEls.forEach((el, idx) => {
      const text = el.textContent.trim().replace(/\s+/g, " ");
      if (!isNoiseClaim(text) && text.length < 300) {
        claims.push({
          source:       "aplus_headline",
          text,
          elementIndex: idx,
          selector:     "#aplus h3, #aplus h4",
        });
      }
    });

    // Deduplicate by text
    const seen = new Set();
    return claims.filter(c => {
      if (seen.has(c.text)) return false;
      seen.add(c.text);
      return true;
    });
  }

  // ─── Scroll-to-claim handler (called by background when popup claim clicked) ─
  // Listens for SCROLL_TO_CLAIM message from background
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type !== "SCROLL_TO_CLAIM") return;
    const { selector, elementIndex } = msg;

    const els = document.querySelectorAll(selector);
    const target = elementIndex != null ? els[elementIndex] : els[0];
    if (!target) return;

    // Scroll into view with highlight animation
    target.scrollIntoView({ behavior: "smooth", block: "center" });

    // Flash highlight
    const original = target.style.cssText;
    target.style.cssText += ";background:#fef08a;border-radius:4px;transition:background 1.5s;";
    setTimeout(() => {
      target.style.cssText = original;
    }, 2500);
  });

  // Full claims text blob for backend NLP
  function extractClaimsText() {
    return [
      "#productTitle",
      "#feature-bullets",
      "#aplus",
      "#productDescription",
    ].map(sel => document.querySelector(sel)?.textContent.trim() || "")
      .filter(Boolean)
      .join(" ")
      .replace(/\s+/g, " ")
      .substring(0, 5000);
  }

  function extractIngredients() {
    // Look for "Ingredients:" section in full page text
    const full = document.body.textContent;
    const m = full.match(/ingredients?\s*[:\-]\s*([^]{20,800}?)(?:\n\n|allergen|storage|directions|$)/i);
    return m ? m[1].trim().replace(/\s+/g, " ") : null;
  }

  // ─── Gallery images ──────────────────────────────────────────────────────────

  function extractGalleryImages() {
    const urls = new Set();

    // Highest res: data-a-dynamic-image
    for (const el of document.querySelectorAll("[data-a-dynamic-image]")) {
      try {
        const data = JSON.parse(el.getAttribute("data-a-dynamic-image"));
        for (const [url, dims] of Object.entries(data)) {
          if (dims[0] >= 100 && dims[1] >= 100) urls.add(url);
        }
      } catch (_) {}
    }

    // Thumbnail strip
    for (const sel of ["#altImages img", ".imageThumbnail img", "li.image.item img"]) {
      for (const img of document.querySelectorAll(sel)) {
        const src = (img.src || "")
          .replace(/_SS\d+_/, "_SL1500_")
          .replace(/_AC_US\d+_/, "_AC_SL1500_")
          .replace(/_SX\d+_/, "_SL1500_");
        if (src?.startsWith("https://")) urls.add(src);
      }
    }

    const allUrls = [...urls].filter(u => !u.endsWith(".svg"));
    return {
      all_image_urls:    allUrls,
      ocr_target_urls:   allUrls.slice(-4),  // last 4 most likely show label
      primary_image_url: allUrls[0] || null,
    };
  }

  // ─── FSSAI from seller About page ────────────────────────────────────────────

  async function extractSellerFssai() {
    try {
      // Fixed: use separate attribute selector to avoid nested quote issue
      const sellerLink =
        document.querySelector("#sellerProfileTriggerId") ||
        document.querySelector("#merchant-info a") ||
        document.querySelector('a[href*="seller="]');

      if (!sellerLink) return null;

      let href = sellerLink.getAttribute("href");
      if (!href) return null;
      if (!href.startsWith("http")) href = "https://www.amazon.in" + href;

      const url = href.includes("sp?") ? href : href + (href.includes("?") ? "&" : "?") + "ref=dp_merchant_link";

      const resp = await fetch(url, { credentials: "include" });
      if (!resp.ok) return null;

      const html = await resp.text();

      // Try explicit "FSSAI license number: XXXXXXXXXXXXXX" first
      const explicit = html.match(/FSSAI\s+[Ll]icense\s+[Nn]umber\s*[:\-]?\s*([0-9]{14})/i)
                    || html.match(/FSSAI\s*[:\-]\s*([0-9]{14})/i);
      if (explicit) {
        const num = explicit[1];
        if (parseInt(num.substring(0, 2)) >= 10) {
          console.log("[NutriLens] FSSAI from seller page:", num);
          return num;
        }
      }

      // Fallback: any 14-digit number with valid state code
      for (const m of html.matchAll(/\b([0-9]{14})\b/g)) {
        const num = m[1];
        const state = parseInt(num.substring(0, 2));
        if (state >= 10 && state <= 35) return num;
      }
    } catch (e) {
      console.warn("[NutriLens] Seller FSSAI fetch failed:", e.message);
    }
    return null;
  }

  // ─── Main extraction ─────────────────────────────────────────────────────────

  function extractProductData() {
    const asin = extractASIN();
    if (!asin) {
      console.warn("[NutriLens] No ASIN found — not a product page?");
      return null;
    }

    const price     = extractPrice();
    const quantityG = extractQuantity();
    const gallery   = extractGalleryImages();
    const facts     = extractNutritionFacts();
    const claims    = extractClaims();

    console.log(`[NutriLens] ASIN: ${asin} | Claims: ${claims.length} | Nutrition fields: ${Object.keys(facts || {}).length}`);

    return {
      // ── Identity ──────────────────────────────
      platform:     "amazon.in",
      platform_id:  asin,            // ASIN — always present
      url:          window.location.href,
      extracted_at: new Date().toISOString(),

      // ── Product info ──────────────────────────
      product_name:  extractProductName(),
      brand:         extractBrand(),

      // ── Pricing ───────────────────────────────
      price_inr:      price,
      quantity_g:     quantityG,
      price_per_100g: (price && quantityG)
        ? parseFloat(((price / quantityG) * 100).toFixed(2))
        : null,

      // ── Nutrition (DOM — may be incomplete) ───
      serving_size_g:  extractServingSize(),
      nutrition_facts: facts,

      // ── Claims (structured + raw) ─────────────
      claims:           claims,         // array of {source, text}
      claims_text:      extractClaimsText(),  // full blob for NLP
      ingredients_text: extractIngredients(),

      // ── Images ────────────────────────────────
      primary_image_url: gallery.primary_image_url,
      ocr_target_urls:   gallery.ocr_target_urls,
      total_images:      gallery.all_image_urls.length,

      // ── Data quality ──────────────────────────
      extraction_method: facts ? "dom_table" : "text_fallback",
      fssai:        null,          // filled after seller page fetch below
      fssai_status: "scanning",
    };
  }

  // ─── Entry point ─────────────────────────────────────────────────────────────

  async function init() {
    // Wait for React hydration to settle
    await new Promise(r => setTimeout(r, 1500));

    const data = extractProductData();
    if (!data) return;

    // FSSAI from seller page — runs in parallel with sending initial payload
    extractSellerFssai().then(fssai => {
      data.fssai        = fssai;
      data.fssai_status = fssai ? "found" : "not_found";
      console.log("[NutriLens] FSSAI:", fssai || "not found");

      // Send final payload once FSSAI is resolved
      chrome.runtime.sendMessage({ type: "PRODUCT_EXTRACTED", payload: data });
    });

    // Also send immediately (without FSSAI) so popup shows fast
    chrome.runtime.sendMessage({ type: "PRODUCT_EXTRACTED", payload: { ...data } });
  }

  init();
})();