/**
 * amazon.js — NutriLens Content Script for Amazon.in
 *
 * Runs on product detail pages (dp/* URLs).
 * Extracts: product name, brand, price, quantity, nutrition table,
 * ingredients, claims text, and ASIN.
 *
 * Sends structured payload to background.js via chrome.runtime.sendMessage.
 * Never sends raw DOM — only parsed, structured JSON (~2KB).
 */

(function () {
  "use strict";

  // ─── Utility Helpers ────────────────────────────────────────────────────────

  /**
   * Attempt multiple CSS selectors in order, return first match's trimmed text.
   * Returns null if none match.
   */
  function queryText(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim()) {
        return el.textContent.trim();
      }
    }
    return null;
  }

  /**
   * Parse a price string like "₹2,849.00", "Rs. 1,299", "2499" → float
   * Indian format: commas are thousand separators, period is decimal.
   */
  function parsePrice(raw) {
    if (!raw) return null;
    // Step 1: remove currency symbols and whitespace only (NOT the decimal point)
    const withoutSymbols = raw.replace(/[₹R s]/g, "").replace(/Rs/g, "");
    // Step 2: remove thousand-separator commas
    const withoutCommas = withoutSymbols.replace(/,/g, "");
    const val = parseFloat(withoutCommas);
    return isNaN(val) ? null : val;
  }

  /**
   * Parse a weight/volume string to grams.
   * Handles: "1 kg", "500g", "1.5 KG", "250 ml", "1 L"
   * Returns null if unparseable.
   */
  function parseQuantityToGrams(raw) {
    if (!raw) return null;
    const str = raw.toLowerCase().trim();

    // Match patterns like "1 kg", "500g", "1.5kg", "250 ml"
    const match = str.match(/([\d.]+)\s*(kg|g|l|ml|ltr|litre|liter)/);
    if (!match) return null;

    const value = parseFloat(match[1]);
    const unit = match[2];

    const conversions = {
      kg: 1000,
      g: 1,
      l: 1000,       // treat liquids as ml≈g (rough, good enough for scoring)
      ml: 1,
      ltr: 1000,
      litre: 1000,
      liter: 1000,
    };

    return value * (conversions[unit] || 1);
  }

  // ─── ASIN Extraction ────────────────────────────────────────────────────────

  function extractASIN() {
    // Most reliable: URL pattern /dp/XXXXXXXXXX
    const urlMatch = window.location.pathname.match(/\/dp\/([A-Z0-9]{10})/);
    if (urlMatch) return urlMatch[1];

    // Fallback: meta tag or data attribute
    const meta = document.querySelector('[data-asin]');
    if (meta) return meta.getAttribute('data-asin');

    return null;
  }

  // ─── Product Identity ────────────────────────────────────────────────────────

  function extractProductName() {
    return queryText([
      "#productTitle",
      "#title span",
      "h1.a-size-large"
    ]);
  }

  function extractBrand() {
    // Try the "Brand:" row in the product details table first
    const rows = document.querySelectorAll(
      "#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr"
    );
    for (const row of rows) {
      const header = row.querySelector("th");
      const value = row.querySelector("td");
      if (header && /brand/i.test(header.textContent) && value) {
        return value.textContent.trim();
      }
    }

    // Fallback: byline link
    return queryText([
      "#bylineInfo",
      "#brand",
      "a#bylineInfo"
    ])?.replace(/^(Brand:|Visit the|Store)?\s*/i, "").trim() || null;
  }

  function extractPrice() {
    // Strategy 1: Build from visible whole + fraction elements — most reliable
    // Avoids the offscreen span which Amazon sometimes populates with paise values
    const wholeEl    = document.querySelector(
      "#corePriceDisplay_desktop_feature_div .a-price-whole, " +
      "#corePrice_feature_div .a-price-whole, " +
      "#apex_offerDisplay_desktop .a-price-whole, " +
      ".a-price-whole"
    );
    const fractionEl = document.querySelector(
      "#corePriceDisplay_desktop_feature_div .a-price-fraction, " +
      "#corePrice_feature_div .a-price-fraction, " +
      ".a-price-fraction"
    );

    if (wholeEl) {
      const wholeVal    = wholeEl.textContent.replace(/[^0-9]/g, "");
      const fractionVal = fractionEl
        ? fractionEl.textContent.replace(/[^0-9]/g, "").substring(0, 2).padEnd(2, "0")
        : "00";
      const combined = parseFloat(`${wholeVal}.${fractionVal}`);
      if (!isNaN(combined) && combined > 0 && combined < 500000) return combined;
    }

    // Strategy 2: offscreen span (fallback)
    const offscreenSelectors = [
      "#corePriceDisplay_desktop_feature_div .a-offscreen",
      "#corePrice_feature_div .a-offscreen",
      "#priceblock_ourprice",
      "#priceblock_dealprice",
      "#priceblock_saleprice",
    ];
    for (const sel of offscreenSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        const price = parsePrice(el.textContent);
        if (price && price > 0 && price < 500000) return price;
      }
    }

    return null;
  }

  // ─── Quantity / Pack Size ───────────────────────────────────────────────────

  function extractQuantity() {
    // Try detail table rows for "Weight", "Net Quantity", "Pack of"
    const detailRows = document.querySelectorAll(
      "#productDetails_techSpec_section_1 tr, " +
      "#productDetails_techSpec_section_2 tr, " +
      "#productDetails_detailBullets_sections1 tr, " +
      ".a-keyvalue tr"
    );

    const quantityKeys = /net quantity|item weight|package weight|net weight|size|volume/i;

    for (const row of detailRows) {
      const header = row.querySelector("th, .a-span3 span, li span.a-text-bold");
      const value = row.querySelector("td, .a-span9 span");
      if (header && quantityKeys.test(header.textContent) && value) {
        const grams = parseQuantityToGrams(value.textContent);
        if (grams) return grams;
      }
    }

    // Fallback: scan product title for weight patterns
    const title = extractProductName() || "";
    return parseQuantityToGrams(title);
  }

  // ─── Nutritional Table ──────────────────────────────────────────────────────

  /**
   * Tries multiple strategies to extract nutrition facts.
   * Returns a structured object with known nutrients.
   * Values are per-serving (as listed) — normalization happens in backend.
   */
  function extractNutritionFacts() {
    const facts = {};

    // Strategy 1: HTML table in product details section
    const tables = document.querySelectorAll("table");
    for (const table of tables) {
      const tableText = table.textContent.toLowerCase();
      // Only process tables that look like nutrition tables
      if (!tableText.includes("protein") && !tableText.includes("energy") && !tableText.includes("calories")) {
        continue;
      }

      const rows = table.querySelectorAll("tr");
      for (const row of rows) {
        const cells = row.querySelectorAll("td, th");
        if (cells.length < 2) continue;

        const label = cells[0].textContent.toLowerCase().trim();
        const value = cells[1].textContent.trim();

        parseNutrientRow(label, value, facts);
      }

      if (Object.keys(facts).length > 0) break; // Found a nutrition table
    }

    // Strategy 2: Bullet points / description text (free text fallback)
    if (Object.keys(facts).length === 0) {
      const descriptionText = queryText([
        "#feature-bullets",
        "#productDescription",
        "#aplus",
        ".a-unordered-list"
      ]) || "";
      extractNutritionFromText(descriptionText, facts);
    }

    return Object.keys(facts).length > 0 ? facts : null;
  }

  const NUTRIENT_PATTERNS = {
    energy_kcal:      /energy|calories|kcal/,
    protein_g:        /protein/,
    total_fat_g:      /total fat|fat/,
    saturated_fat_g:  /saturated fat|saturated/,
    carbohydrates_g:  /carbohydrate|carbs/,
    sugar_g:          /sugar/,
    dietary_fiber_g:  /fiber|fibre/,
    sodium_mg:        /sodium/,
    cholesterol_mg:   /cholesterol/,
    calcium_mg:       /calcium/,
    iron_mg:          /iron/,
  };

  function parseNutrientRow(label, rawValue, facts) {
    for (const [key, pattern] of Object.entries(NUTRIENT_PATTERNS)) {
      if (pattern.test(label)) {
        const num = parseFloat(rawValue.replace(/[^\d.]/g, ""));
        if (!isNaN(num)) {
          facts[key] = num;
        }
        break;
      }
    }
  }

  function extractNutritionFromText(text, facts) {
    // e.g. "24g Protein", "Protein: 24g per serving", "130 kcal"
    const patterns = [
      { key: "protein_g",       regex: /([\d.]+)\s*g\s*protein|protein[:\s]+([\d.]+)\s*g/i },
      { key: "energy_kcal",     regex: /([\d.]+)\s*kcal|calories[:\s]+([\d.]+)/i },
      { key: "sugar_g",         regex: /([\d.]+)\s*g\s*sugar|sugar[:\s]+([\d.]+)\s*g/i },
      { key: "total_fat_g",     regex: /([\d.]+)\s*g\s*fat|fat[:\s]+([\d.]+)\s*g/i },
      { key: "carbohydrates_g", regex: /([\d.]+)\s*g\s*carb|carbohydrate[:\s]+([\d.]+)\s*g/i },
      { key: "sodium_mg",       regex: /([\d.]+)\s*mg\s*sodium|sodium[:\s]+([\d.]+)\s*mg/i },
    ];

    for (const { key, regex } of patterns) {
      const match = text.match(regex);
      if (match) {
        const val = parseFloat(match[1] || match[2]);
        if (!isNaN(val)) facts[key] = val;
      }
    }
  }

  // ─── Serving Size ───────────────────────────────────────────────────────────

  function extractServingSize() {
    const tables = document.querySelectorAll("table");
    for (const table of tables) {
      const rows = table.querySelectorAll("tr");
      for (const row of rows) {
        const text = row.textContent.toLowerCase();
        if (text.includes("serving size")) {
          const match = row.textContent.match(/([\d.]+)\s*g/i);
          if (match) return parseFloat(match[1]);
        }
      }
    }
    return null;
  }

  // ─── Claims & Ingredients ───────────────────────────────────────────────────

  function extractClaimsText() {
    // Gather all marketing text: title, bullets, A+ content
    const sources = [
      "#productTitle",
      "#feature-bullets",
      "#aplus",
      "#productDescription",
      ".a-carousel-card"
    ];

    return sources
      .map(sel => {
        const el = document.querySelector(sel);
        return el ? el.textContent.trim() : "";
      })
      .filter(Boolean)
      .join(" ")
      .replace(/\s+/g, " ")
      .substring(0, 3000); // Cap at 3000 chars — enough for NLP, not bloated
  }

  function extractIngredients() {
    // Look for "Ingredients:" section in description or details
    const fullText = document.body.textContent;
    const match = fullText.match(/ingredients?\s*[:\-]\s*([^.]{20,500}\.)/i);
    return match ? match[1].trim() : null;
  }

  // ─── Image URL (for OCR fallback) ──────────────────────────────────────────

  function extractImageUrl() {
    // Primary product image
    const img = document.querySelector("#landingImage, #imgBlkFront, #main-image");
    return img ? img.src : null;
  }

  // ─── Nutrition Image Detection ─────────────────────────────────────────────

  /**
   * Detect if nutrition facts appear to be in an image (OCR needed).
   * Heuristic: very little structured nutrition data found, but
   * an image with alt text mentioning nutrition exists.
   */
  function detectNutritionImageUrl() {
    const imgs = document.querySelectorAll("img");
    for (const img of imgs) {
      const alt = (img.alt || "").toLowerCase();
      const src = img.src || "";
      if (alt.includes("nutrition") || alt.includes("supplement facts")) {
        return src;
      }
    }
    return null;
  }

  // ─── Main Extraction ────────────────────────────────────────────────────────

  function extractProductData() {
    const asin = extractASIN();
    if (!asin) {
      console.warn("[NutriLens] Could not find ASIN. Not a product page?");
      return null;
    }

    const nutritionFacts = extractNutritionFacts();
    const quantityG = extractQuantity();
    const price = extractPrice();

    const payload = {
      // Identity
      platform: "amazon.in",
      platform_id: asin,
      url: window.location.href,
      extracted_at: new Date().toISOString(),

      // Product info
      product_name: extractProductName(),
      brand: extractBrand(),

      // Pricing & quantity
      price_inr: price,
      quantity_g: quantityG,
      price_per_100g: (price && quantityG) ? parseFloat(((price / quantityG) * 100).toFixed(2)) : null,

      // Nutrition (per serving, as listed on label)
      serving_size_g: extractServingSize(),
      nutrition_facts: nutritionFacts,

      // NLP inputs
      claims_text: extractClaimsText(),
      ingredients_text: extractIngredients(),

      // Media
      primary_image_url: extractImageUrl(),
      nutrition_image_url: detectNutritionImageUrl(),

      // Data quality signals
      extraction_method: nutritionFacts ? "dom_table" : "text_fallback",
      nutrition_confidence: nutritionFacts
        ? (Object.keys(nutritionFacts).length >= 4 ? "high" : "medium")
        : "low",
    };

    return payload;
  }

  // ─── Entry Point ────────────────────────────────────────────────────────────

  function init() {
    // Small delay to let dynamic content (React/hydration) settle
    setTimeout(() => {
      const data = extractProductData();

      if (!data) return;

      console.log("[NutriLens] Extracted payload:", data);

      // Notify background service worker that product data is available
      chrome.runtime.sendMessage({
        type: "PRODUCT_EXTRACTED",
        payload: data
      });
    }, 1500);
  }

  init();
})();