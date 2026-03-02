"""
engines/ocr.py

Phase 4 OCR Pipeline.

Flow per image:
  1. Download image from Amazon CDN
  2. Preprocess (grayscale, contrast, upscale, denoise)
  3. Run Tesseract OCR
  4. Classify image type (nutrition / fssai / barcode / other)
  5. Parse nutrition table from nutrition images
  6. Extract FSSAI license number from any image
  7. Return structured result

Reconciliation (run after all images processed):
  - Merge OCR nutrition with DOM nutrition
  - DOM fills gaps OCR misses, OCR overrides DOM where confident
  - Flag conflicts where values differ significantly
"""

import re
import io
import logging
import httpx
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import pytesseract

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

# Tesseract config — PSM 6: assume uniform block of text (good for label panels)
TESS_CONFIG_BLOCK  = "--psm 6 --oem 3"
# PSM 4: assume single column of text (good for narrow nutrition tables)
TESS_CONFIG_COLUMN = "--psm 4 --oem 3"

# FSSAI license number: exactly 14 digits
FSSAI_PATTERN = re.compile(r'\b(\d{14})\b')

# Valid Indian state codes for FSSAI (first 2 digits)
VALID_STATE_CODES = {
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "30", "31", "32", "33", "34", "35"
}

# Nutrition keywords for image classification
NUTRITION_KEYWORDS = [
    "protein", "energy", "calories", "carbohydrate", "fat", "sodium",
    "sugar", "fibre", "fiber", "calcium", "iron", "serving", "per 100",
    "nutrition", "nutritional", "supplement facts", "typical values"
]

BARCODE_KEYWORDS = ["barcode", "scan", "ean", "upc"]


# ─── Image Download ───────────────────────────────────────────────────────────

def download_image(url: str, timeout: int = 10) -> Image.Image | None:
    """Download image from URL and return PIL Image. Returns None on failure."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception as e:
        logger.warning(f"[OCR] Failed to download {url}: {e}")
        return None


# ─── Preprocessing ────────────────────────────────────────────────────────────

def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """
    Preprocess image to improve Tesseract accuracy.
    Steps: convert to grayscale → upscale → enhance contrast → sharpen → binarize
    """
    # 1. Grayscale
    img = img.convert("L")

    # 2. Upscale if small — Tesseract works best at 300+ DPI equivalent
    w, h = img.size
    if w < 1000 or h < 1000:
        scale = max(1000 / w, 1000 / h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # 3. Enhance contrast
    img = ImageEnhance.Contrast(img).enhance(2.0)

    # 4. Sharpen
    img = img.filter(ImageFilter.SHARPEN)

    # 5. Auto-level (stretch histogram)
    img = ImageOps.autocontrast(img, cutoff=2)

    return img


# ─── OCR Execution ────────────────────────────────────────────────────────────

def run_tesseract(img: Image.Image) -> str:
    """Run Tesseract on preprocessed image, try both PSM configs, return best result."""
    try:
        # Try block mode first
        text_block = pytesseract.image_to_string(img, config=TESS_CONFIG_BLOCK, lang="eng")

        # If block mode returns little text, try column mode
        if len(text_block.strip()) < 50:
            text_col = pytesseract.image_to_string(img, config=TESS_CONFIG_COLUMN, lang="eng")
            return text_col if len(text_col) > len(text_block) else text_block

        return text_block
    except Exception as e:
        logger.error(f"[OCR] Tesseract failed: {e}")
        return ""


# ─── Image Classification ─────────────────────────────────────────────────────

def classify_image(ocr_text: str) -> str:
    """
    Classify image based on OCR output content.
    Returns: "nutrition" | "fssai" | "barcode" | "ingredients" | "other"
    """
    text_lower = ocr_text.lower()
    nutrition_hits = sum(1 for kw in NUTRITION_KEYWORDS if kw in text_lower)

    # Check for FSSAI number
    fssai_match = FSSAI_PATTERN.search(ocr_text)
    has_fssai   = fssai_match and fssai_match.group(1)[:2] in VALID_STATE_CODES

    # Check for ingredients
    has_ingredients = bool(re.search(r'ingredient', text_lower))

    # Check for barcode (very little text, mostly numbers)
    digits_only = sum(1 for c in ocr_text if c.isdigit())
    total_chars = len(ocr_text.strip())
    is_barcode  = total_chars > 0 and (digits_only / total_chars) > 0.6 and total_chars < 30

    if is_barcode:
        return "barcode"
    if nutrition_hits >= 3:
        return "nutrition"
    if has_fssai and nutrition_hits < 2:
        return "fssai"
    if has_ingredients and nutrition_hits < 2:
        return "ingredients"
    if has_fssai or nutrition_hits >= 1:
        return "nutrition"  # Back-side image often has both
    return "other"


# ─── FSSAI Number Extraction ──────────────────────────────────────────────────

def extract_fssai_number(ocr_text: str) -> str | None:
    """
    Extract and validate FSSAI license number from OCR text.
    Format: 14 digits, first 2 digits are a valid Indian state code.
    """
    # Clean common OCR errors in digit sequences
    cleaned = ocr_text.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")

    matches = FSSAI_PATTERN.findall(cleaned)
    for match in matches:
        if match[:2] in VALID_STATE_CODES:
            return match

    return None


# ─── Nutrition Table Parser ───────────────────────────────────────────────────

# Patterns to extract nutrient values from OCR text
# Handles: "Protein 25g", "Protein: 25 g", "25g Protein", "Energy 130kcal"
NUTRIENT_PATTERNS = [
    ("protein_g",        r"protein[\s:]+(\d+\.?\d*)\s*g"),
    ("energy_kcal",      r"energy[\s:]+(\d+\.?\d*)\s*kcal"),
    ("energy_kcal",      r"calories[\s:]+(\d+\.?\d*)"),
    ("carbohydrates_g",  r"carbohydrate[s]?[\s:]+(\d+\.?\d*)\s*g"),
    ("sugar_g",          r"(?:of which\s+)?sugar[s]?[\s:]+(\d+\.?\d*)\s*g"),
    ("total_fat_g",      r"(?:total\s+)?fat[\s:]+(\d+\.?\d*)\s*g"),
    ("saturated_fat_g",  r"saturated[\s:]+(\d+\.?\d*)\s*g"),
    ("dietary_fiber_g",  r"(?:dietary\s+)?fi[b]?[e]?r[\s:]+(\d+\.?\d*)\s*g"),
    ("sodium_mg",        r"sodium[\s:]+(\d+\.?\d*)\s*mg"),
    ("calcium_mg",       r"calcium[\s:]+(\d+\.?\d*)\s*mg"),
    ("iron_mg",          r"iron[\s:]+(\d+\.?\d*)\s*mg"),
]

# Serving size patterns
SERVING_SIZE_PATTERNS = [
    r"serving\s+size[\s:]+(\d+\.?\d*)\s*g",
    r"per\s+serving[\s:]+(\d+\.?\d*)\s*g",
    r"(\d+\.?\d*)\s*g\s+per\s+serving",
]


def parse_nutrition_from_ocr(ocr_text: str) -> dict:
    """
    Parse nutrition facts from raw OCR text.
    Returns dict of nutrient → value (per serving, as found on label).
    """
    text_lower = ocr_text.lower()
    facts = {}

    for key, pattern in NUTRIENT_PATTERNS:
        if key in facts:
            continue  # Already found — don't overwrite with a weaker match
        match = re.search(pattern, text_lower)
        if match:
            try:
                val = float(match.group(1))
                if val >= 0:
                    facts[key] = val
            except (ValueError, IndexError):
                pass

    return facts


def parse_serving_size_from_ocr(ocr_text: str) -> float | None:
    """Extract serving size in grams from OCR text."""
    text_lower = ocr_text.lower()
    for pattern in SERVING_SIZE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return None


def parse_ingredients_from_ocr(ocr_text: str) -> str | None:
    """Extract ingredient list from OCR text."""
    match = re.search(
        r'ingredient[s]?\s*[:\-]\s*(.{20,800}?)(?:\n\n|\Z|nutrition|fssai)',
        ocr_text,
        re.IGNORECASE | re.DOTALL
    )
    if match:
        ingredients = match.group(1).replace("\n", " ").strip()
        return ingredients[:500] if len(ingredients) > 500 else ingredients
    return None


# ─── Reconciliation ───────────────────────────────────────────────────────────

def reconcile_nutrition(dom_facts: dict | None, ocr_facts: dict | None) -> dict:
    """
    Merge DOM-extracted and OCR-extracted nutrition facts.

    Priority:
    - OCR wins if it found a value and DOM didn't
    - OCR wins if both found values and they're close (within 20%)
    - Flag as conflict if both found values that differ by >20%
    - DOM fills in nutrients OCR missed

    Returns merged dict + list of conflicts.
    """
    merged    = {}
    conflicts = []

    all_keys = set(list(dom_facts.keys() if dom_facts else []) +
                   list(ocr_facts.keys()  if ocr_facts  else []))

    for key in all_keys:
        dom_val = (dom_facts or {}).get(key)
        ocr_val = (ocr_facts or {}).get(key)

        if ocr_val is not None and dom_val is not None:
            # Both have value — check for conflict
            diff_pct = abs(ocr_val - dom_val) / max(dom_val, 0.01) * 100
            if diff_pct > 20:
                conflicts.append({
                    "nutrient":  key,
                    "dom_value": dom_val,
                    "ocr_value": ocr_val,
                    "diff_pct":  round(diff_pct, 1),
                })
            # Use OCR value — it came from the physical label
            merged[key] = ocr_val

        elif ocr_val is not None:
            merged[key] = ocr_val

        elif dom_val is not None:
            merged[key] = dom_val

    return merged, conflicts


def assess_confidence(ocr_facts: dict, dom_facts: dict | None, conflicts: list) -> str:
    """
    Determine overall nutrition confidence level after reconciliation.
    high:   OCR succeeded, 4+ nutrients, no conflicts
    medium: OCR partial or DOM only with 3+ nutrients
    low:    Very little data or significant conflicts
    """
    ocr_count = len(ocr_facts) if ocr_facts else 0
    dom_count = len(dom_facts) if dom_facts else 0

    if ocr_count >= 4 and len(conflicts) == 0:
        return "high"
    if ocr_count >= 2 or dom_count >= 3:
        return "medium"
    return "low"


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def process_product_images(
    ocr_target_urls: list[str],
    dom_nutrition:   dict | None = None,
    dom_serving_size: float | None = None,
) -> dict:
    """
    Full OCR pipeline for a product.

    Args:
        ocr_target_urls:  Last 4 image URLs from product gallery
        dom_nutrition:    Nutrition facts already extracted from DOM
        dom_serving_size: Serving size from DOM

    Returns dict with:
        ocr_nutrition:    Raw nutrition from OCR (per serving)
        ocr_serving_size: Serving size from OCR
        ocr_ingredients:  Ingredient list from OCR
        fssai_number:     FSSAI license number if found
        merged_nutrition: Reconciled nutrition (OCR + DOM)
        conflicts:        List of value conflicts between sources
        confidence:       "high" | "medium" | "low"
        ocr_success:      bool
        images_processed: int
        image_types:      dict of url → classification
    """
    results = {
        "ocr_nutrition":    {},
        "ocr_serving_size": None,
        "ocr_ingredients":  None,
        "fssai_number":     None,
        "merged_nutrition": dom_nutrition or {},
        "conflicts":        [],
        "confidence":       "low",
        "ocr_success":      False,
        "images_processed": 0,
        "image_types":      {},
    }

    if not ocr_target_urls:
        return results

    all_ocr_nutrition  = {}
    all_ocr_text       = ""
    images_processed   = 0

    for url in ocr_target_urls[:4]:  # Max 4 images
        logger.info(f"[OCR] Processing image: {url[:80]}...")

        img = download_image(url)
        if not img:
            continue

        processed = preprocess_for_ocr(img)
        ocr_text  = run_tesseract(processed)

        if not ocr_text.strip():
            results["image_types"][url] = "empty"
            continue

        image_type = classify_image(ocr_text)
        results["image_types"][url] = image_type
        images_processed += 1
        all_ocr_text += "\n" + ocr_text

        logger.info(f"[OCR] Image classified as: {image_type} ({len(ocr_text)} chars)")

        # Extract from nutrition images
        if image_type in ("nutrition", "fssai"):
            nutrition = parse_nutrition_from_ocr(ocr_text)
            all_ocr_nutrition.update(nutrition)

            if not results["ocr_serving_size"]:
                results["ocr_serving_size"] = parse_serving_size_from_ocr(ocr_text)

        # Extract ingredients from any image that might have them
        if image_type in ("nutrition", "ingredients") and not results["ocr_ingredients"]:
            ingredients = parse_ingredients_from_ocr(ocr_text)
            if ingredients:
                results["ocr_ingredients"] = ingredients

        # Extract FSSAI from any image
        if not results["fssai_number"]:
            fssai = extract_fssai_number(ocr_text)
            if fssai:
                results["fssai_number"] = fssai
                logger.info(f"[OCR] FSSAI number found: {fssai}")

    # Reconcile OCR with DOM
    if all_ocr_nutrition:
        merged, conflicts = reconcile_nutrition(dom_nutrition, all_ocr_nutrition)
        results["ocr_nutrition"]    = all_ocr_nutrition
        results["merged_nutrition"] = merged
        results["conflicts"]        = conflicts
        results["ocr_success"]      = True
    else:
        # OCR found nothing — use DOM as-is
        results["merged_nutrition"] = dom_nutrition or {}

    results["images_processed"] = images_processed
    results["confidence"]       = assess_confidence(
        all_ocr_nutrition, dom_nutrition, results["conflicts"]
    )

    logger.info(
        f"[OCR] Done. {images_processed} images, "
        f"{len(all_ocr_nutrition)} nutrients found, "
        f"FSSAI: {results['fssai_number']}, "
        f"confidence: {results['confidence']}"
    )

    return results