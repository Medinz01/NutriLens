"""
engines/ocr.py

Phase 4 OCR Pipeline.

Flow per image:
  1. Download image from Amazon CDN
  2. Preprocess (grayscale, contrast, upscale, denoise)
  3. Run Tesseract OCR (Output as Data Dict)
  4. Classify image type (nutrition / fssai / barcode / other)
  5. Parse nutrition table from reconstructed rows
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

# Tesseract config — PSM 6: assume uniform block of text
TESS_CONFIG_BLOCK  = "--psm 6 --oem 3"
# PSM 4: assume single column of text
TESS_CONFIG_COLUMN = "--psm 4 --oem 3"

FSSAI_PATTERN = re.compile(r'\b(\d{14})\b')

VALID_STATE_CODES = {
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "30", "31", "32", "33", "34", "35"
}

NUTRITION_KEYWORDS = [
    "protein", "energy", "calories", "carbohydrate", "fat", "sodium",
    "sugar", "fibre", "fiber", "calcium", "iron", "serving", "per 100",
    "nutrition", "nutritional", "supplement facts", "typical values"
]

BARCODE_KEYWORDS = ["barcode", "scan", "ean", "upc"]


# ─── Image Download ───────────────────────────────────────────────────────────

def download_image(url: str, timeout: int = 10) -> Image.Image | None:
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
    img = img.convert("L")
    w, h = img.size
    if w < 1000 or h < 1000:
        scale = max(1000 / w, 1000 / h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageOps.autocontrast(img, cutoff=2)
    return img


# ─── OCR Execution (Step 1) ───────────────────────────────────────────────────

def run_tesseract(img: Image.Image) -> dict:
    """Run Tesseract and return dict of data with bounding boxes."""
    try:
        data = pytesseract.image_to_data(img, config=TESS_CONFIG_BLOCK, lang="eng", output_type=pytesseract.Output.DICT)
        
        # Check if we got enough text, otherwise fallback to column mode
        text = " ".join(w for w in data.get("text", []) if isinstance(w, str) and w.strip())
        if len(text) < 50:
            data_col = pytesseract.image_to_data(img, config=TESS_CONFIG_COLUMN, lang="eng", output_type=pytesseract.Output.DICT)
            text_col = " ".join(w for w in data_col.get("text", []) if isinstance(w, str) and w.strip())
            if len(text_col) > len(text):
                return data_col

        return data
    except Exception as e:
        logger.error(f"[OCR] Tesseract failed: {e}")
        return {"text": [], "left": [], "top": [], "width": [], "height": [], "conf": []}


# ─── Row Reconstruction (Step 2) ──────────────────────────────────────────────

def group_words_into_rows(data: dict, y_threshold: int = 10) -> list:
    """Cluster words by Y coordinate to reconstruct horizontal rows."""
    rows = {}
    for i, word in enumerate(data.get("text", [])):
        if not isinstance(word, str) or not word.strip():
            continue
            
        # Relaxed confidence filter (35 instead of 40)
        try:
            conf = int(data.get("conf", [0])[i])
        except (ValueError, TypeError, IndexError):
            conf = 0
            
        if conf < 35:
            continue

        y = data["top"][i]
        x = data["left"][i]

        matched_row = None
        for row_y in rows:
            if abs(row_y - y) <= y_threshold:
                matched_row = row_y
                break

        if matched_row is None:
            rows[y] = []
            matched_row = y

        rows[matched_row].append({"text": word, "x": x})

    sorted_rows = []
    for row_y in sorted(rows.keys()):
        sorted_rows.append(sorted(rows[row_y], key=lambda w: w["x"]))

    return sorted_rows


# ─── Image Classification ─────────────────────────────────────────────────────

def classify_image(ocr_text: str) -> str:
    text_lower = ocr_text.lower()
    nutrition_hits = sum(1 for kw in NUTRITION_KEYWORDS if kw in text_lower)
    fssai_match = FSSAI_PATTERN.search(ocr_text)
    has_fssai   = fssai_match and fssai_match.group(1)[:2] in VALID_STATE_CODES
    has_ingredients = bool(re.search(r'ingredient', text_lower))

    digits_only = sum(1 for c in ocr_text if c.isdigit())
    total_chars = len(ocr_text.strip())
    is_barcode  = total_chars > 0 and (digits_only / total_chars) > 0.6 and total_chars < 30

    if is_barcode: return "barcode"
    if nutrition_hits >= 3: return "nutrition"
    if has_fssai and nutrition_hits < 2: return "fssai"
    if has_ingredients and nutrition_hits < 2: return "ingredients"
    if has_fssai or nutrition_hits >= 1: return "nutrition"
    return "other"


# ─── General Extractions ──────────────────────────────────────────────────────

def extract_fssai_number(ocr_text: str) -> str | None:
    cleaned = ocr_text.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    matches = FSSAI_PATTERN.findall(cleaned)
    for match in matches:
        if match[:2] in VALID_STATE_CODES:
            return match
    return None

def parse_serving_size_from_ocr(ocr_text: str) -> float | None:
    lines = ocr_text.splitlines()
    for line in lines:
        l = line.lower()
        if "serving" in l and "g" in l:
            nums = re.findall(r"\d+\.?\d*", line)
            if nums:
                try: return float(nums[0])
                except ValueError: continue
    return None

def parse_ingredients_from_ocr(ocr_text: str) -> str | None:
    match = re.search(
        r'ingredient[s]?\s*[:\-]\s*(.{20,800}?)(?:\n\n|\Z|nutrition|fssai)',
        ocr_text, re.IGNORECASE | re.DOTALL
    )
    if match:
        ingredients = match.group(1).replace("\n", " ").strip()
        return ingredients[:500] if len(ingredients) > 500 else ingredients
    return None


# ─── Nutrition Table Parser (Steps 3 & 4) ─────────────────────────────────────

def parse_nutrition_from_rows(rows: list, image_width: int) -> dict:
    """Extract nutrition data from grouped rows using column tracking."""
    facts = {}
    target_x = None
    extracted_xs = []
    locked_x = None
    
    # Dynamic tolerance: 5% of image width
    x_tolerance = image_width * 0.05

    # Strategy A: Strict Header Detection
    for row in rows:
        row_text = " ".join(w["text"].lower() for w in row)
        if "per" in row_text and ("100" in row_text or "serving" in row_text):
            for word in row:
                wt = word["text"].lower()
                if "100" in wt or "serving" in wt:
                    target_x = word["x"]
                    break
        if target_x is not None:
            break

    # Strategy B (Fallback): 1D Clustering of numeric X-coordinates
    if target_x is None:
        number_xs = [word["x"] for row in rows for word in row if re.match(r'^\d+\.?\d*$', word["text"].strip())]
        if number_xs:
            clusters = []
            for x in number_xs:
                added = False
                for cluster in clusters:
                    if abs(cluster["center"] - x) < x_tolerance:
                        cluster["xs"].append(x)
                        cluster["center"] = sum(cluster["xs"]) / len(cluster["xs"])
                        added = True
                        break
                if not added:
                    clusters.append({"center": x, "xs": [x]})
            
            if clusters:
                best_cluster = max(clusters, key=lambda c: len(c["xs"]))
                target_x = best_cluster["center"]

    # Nutrient Extraction
    for row in rows:
        row_text = " ".join(w["text"].lower() for w in row)
        
        matched_key = None
        if ("energy" in row_text or "kcal" in row_text) and "energy_kcal" not in facts: matched_key = "energy_kcal"
        elif "protein" in row_text and "protein_g" not in facts: matched_key = "protein_g"
        elif "carbohydrate" in row_text and "carbohydrates_g" not in facts: matched_key = "carbohydrates_g"
        elif "sugar" in row_text and "sugar_g" not in facts: matched_key = "sugar_g"
        elif "fat" in row_text and "saturated" not in row_text and "total_fat_g" not in facts: matched_key = "total_fat_g"
        elif "saturated" in row_text and "saturated_fat_g" not in facts: matched_key = "saturated_fat_g"
        elif "sodium" in row_text and "sodium_mg" not in facts: matched_key = "sodium_mg"
        elif ("fiber" in row_text or "fibre" in row_text) and "dietary_fiber_g" not in facts: matched_key = "dietary_fiber_g"
        elif "calcium" in row_text and "calcium_mg" not in facts: matched_key = "calcium_mg"
        elif "iron" in row_text and "iron_mg" not in facts: matched_key = "iron_mg"

        if matched_key:
            nums = []
            for word in row:
                match = re.search(r'(\d+\.?\d*)', word["text"])
                if match:
                    try: nums.append({"val": float(match.group(1)), "x": word["x"]})
                    except ValueError: continue

            if nums:
                current_target = locked_x if locked_x is not None else target_x
                
                if current_target is not None:
                    # Choose numeric value whose X is closest to the target column X
                    best_num = min(nums, key=lambda n: abs(n["x"] - current_target))
                    # Enforce dynamic window
                    if locked_x is None or abs(best_num["x"] - locked_x) < x_tolerance:
                        facts[matched_key] = best_num["val"]
                        extracted_xs.append(best_num["x"])
                else:
                    # Blind fallback
                    facts[matched_key] = nums[1]["val"] if len(nums) >= 3 else nums[0]["val"]
                    extracted_xs.append(nums[1]["x"] if len(nums) >= 3 else nums[0]["x"])

                # Dynamic Lock: Anchor to the median X after 3 successful extractions
                if locked_x is None and len(extracted_xs) >= 3:
                    sorted_xs = sorted(extracted_xs)
                    locked_x = sorted_xs[len(sorted_xs) // 2]

    return facts


# ─── Reconciliation ───────────────────────────────────────────────────────────

def reconcile_nutrition(dom_facts: dict | None, ocr_facts: dict | None) -> dict:
    merged    = {}
    conflicts = []
    all_keys = set(list(dom_facts.keys() if dom_facts else []) +
                   list(ocr_facts.keys()  if ocr_facts  else []))

    for key in all_keys:
        dom_val = (dom_facts or {}).get(key)
        ocr_val = (ocr_facts or {}).get(key)

        if ocr_val is not None and dom_val is not None:
            diff_pct = abs(ocr_val - dom_val) / max(dom_val, 0.01) * 100
            if diff_pct > 20:
                conflicts.append({
                    "nutrient":  key,
                    "dom_value": dom_val,
                    "ocr_value": ocr_val,
                    "diff_pct":  round(diff_pct, 1),
                })
            merged[key] = ocr_val
        elif ocr_val is not None: merged[key] = ocr_val
        elif dom_val is not None: merged[key] = dom_val

    return merged, conflicts

def assess_confidence(ocr_facts: dict, dom_facts: dict | None, conflicts: list) -> str:
    ocr_count = len(ocr_facts) if ocr_facts else 0
    dom_count = len(dom_facts) if dom_facts else 0
    if ocr_count >= 4 and len(conflicts) == 0: return "high"
    if ocr_count >= 2 or dom_count >= 3: return "medium"
    return "low"


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def process_product_images(
    ocr_target_urls: list[str],
    dom_nutrition:   dict | None = None,
    dom_serving_size: float | None = None,
) -> dict:
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

    if not ocr_target_urls: return results

    all_ocr_nutrition  = {}
    images_processed   = 0

    for url in ocr_target_urls[:4]:
        logger.info(f"[OCR] Processing image: {url[:80]}...")

        img = download_image(url)
        if not img: continue

        processed = preprocess_for_ocr(img)
        
        # Get data dict instead of plain string
        # Get data dict instead of plain string
        ocr_data = run_tesseract(processed)
        
        # Group rows first, then preserve line breaks for legacy regex parsers
        rows = group_words_into_rows(ocr_data)
        ocr_text = "\n".join(" ".join(w["text"] for w in row) for row in rows)

        if not ocr_text.strip():
            results["image_types"][url] = "empty"
            continue

        image_type = classify_image(ocr_text)
        results["image_types"][url] = image_type
        images_processed += 1

        logger.info(f"[OCR] Image classified as: {image_type} ({len(ocr_text)} chars)")

        # Extract from nutrition images using new row-based logic
        if image_type in ("nutrition", "fssai"):
            # Pass the PIL image width for dynamic coordinate tolerance
            nutrition = parse_nutrition_from_rows(rows, image_width=processed.width)
            all_ocr_nutrition.update(nutrition)

            if not results["ocr_serving_size"]:
                results["ocr_serving_size"] = parse_serving_size_from_ocr(ocr_text)

        if image_type in ("nutrition", "ingredients") and not results["ocr_ingredients"]:
            ingredients = parse_ingredients_from_ocr(ocr_text)
            if ingredients: results["ocr_ingredients"] = ingredients

        if not results["fssai_number"]:
            fssai = extract_fssai_number(ocr_text)
            if fssai:
                results["fssai_number"] = fssai
                logger.info(f"[OCR] FSSAI number found: {fssai}")

    if all_ocr_nutrition:
        merged, conflicts = reconcile_nutrition(dom_nutrition, all_ocr_nutrition)
        results["ocr_nutrition"]    = all_ocr_nutrition
        results["merged_nutrition"] = merged
        results["conflicts"]        = conflicts
        results["ocr_success"]      = True
    else:
        results["merged_nutrition"] = dom_nutrition or {}

    results["images_processed"] = images_processed
    results["confidence"]       = assess_confidence(all_ocr_nutrition, dom_nutrition, results["conflicts"])

    logger.info(
        f"[OCR] Done. {images_processed} images, "
        f"{len(all_ocr_nutrition)} nutrients found, "
        f"FSSAI: {results['fssai_number']}, "
        f"confidence: {results['confidence']}"
    )

    return results