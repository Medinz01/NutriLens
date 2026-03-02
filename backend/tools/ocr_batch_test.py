import json
from pathlib import Path
import sys
from PIL import Image

# Add backend root to Python path
CURRENT_DIR = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_DIR.parents[1]
sys.path.append(str(BACKEND_ROOT))

from engines.ocr import (
    preprocess_for_ocr,
    run_tesseract,
    group_words_into_rows,
    parse_nutrition_from_rows,
    classify_image,
    parse_serving_size_from_ocr,
    parse_ingredients_from_ocr,
    extract_fssai_number,
)

TEST_DIR = Path("test_images")
OUTPUT_FILE = TEST_DIR / "ocr_results.json"


def process_single_image(image_path: Path):
    print(f"\nProcessing: {image_path.name}")

    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"Failed to open image: {e}")
        return None

    # Preprocess
    processed = preprocess_for_ocr(img)

    # Run OCR (returns data dict)
    ocr_data = run_tesseract(processed)

    # Reconstruct rows
    rows = group_words_into_rows(ocr_data)

    # Reconstruct readable text
    ocr_text = "\n".join(
        " ".join(w["text"] for w in row) for row in rows
    )

    if not ocr_text.strip():
        print("No OCR text extracted.")
        return {
            "image": image_path.name,
            "classification": "empty",
            "ocr_text_length": 0,
            "nutrition": {},
            "serving_size": None,
            "ingredients": None,
            "fssai": None,
        }

    # Classification
    classification = classify_image(ocr_text)

    # Nutrition extraction (structured)
    nutrition = {}
    if classification in ("nutrition", "fssai"):
        nutrition = parse_nutrition_from_rows(
            rows,
            image_width=processed.width
        )

    # Other extractions
    serving_size = parse_serving_size_from_ocr(ocr_text)
    ingredients = parse_ingredients_from_ocr(ocr_text)
    fssai = extract_fssai_number(ocr_text)

    print(f"Classification: {classification}")
    print(f"OCR text length: {len(ocr_text)}")
    print(f"Nutrients found: {len(nutrition)}")
    print(f"Serving size: {serving_size}")
    print(f"FSSAI: {fssai}")

    return {
        "image": image_path.name,
        "classification": classification,
        "ocr_text_length": len(ocr_text),
        "nutrition": nutrition,
        "serving_size": serving_size,
        "ingredients": ingredients,
        "fssai": fssai,
        "raw_text_preview": ocr_text[:1000],
    }


def main():
    if not TEST_DIR.exists():
        print("Test directory not found.")
        return

    image_files = [
        p for p in TEST_DIR.iterdir()
        if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
    ]

    if not image_files:
        print("No images found in test directory.")
        return

    print(f"Found {len(image_files)} images.")

    results = []

    for image_path in image_files:
        result = process_single_image(image_path)
        if result:
            results.append(result)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()