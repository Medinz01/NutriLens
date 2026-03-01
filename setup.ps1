# ================================
# NutriLens Repo Scaffold Script
# Run from repo root
# ================================

Write-Host "Creating NutriLens project structure..."

# Root folder name (optional safeguard)
$root = "nutrilens"

# If you're already inside the cloned repo, comment next 2 lines
# New-Item -ItemType Directory -Name $root -Force
# Set-Location $root

# ---------- EXTENSION ----------
New-Item -ItemType Directory -Force -Path `
"extension/content_scripts", `
"extension/popup", `
"extension/utils"

New-Item -ItemType File -Force -Path `
"extension/manifest.json", `
"extension/background.js", `
"extension/content_scripts/amazon.js", `
"extension/content_scripts/bigbasket.js", `
"extension/content_scripts/flipkart.js", `
"extension/popup/App.jsx", `
"extension/popup/CompareTable.jsx", `
"extension/popup/ProductDetail.jsx", `
"extension/utils/normalizer.js", `
"extension/utils/api.js"

# ---------- BACKEND ----------
New-Item -ItemType Directory -Force -Path `
"backend/routers", `
"backend/models/claim_extractor", `
"backend/models/claim_classifier", `
"backend/engines", `
"backend/data"

New-Item -ItemType File -Force -Path `
"backend/main.py", `
"backend/routers/extract.py", `
"backend/routers/verify.py", `
"backend/routers/rank.py", `
"backend/engines/contradiction.py", `
"backend/engines/ranker.py", `
"backend/engines/ocr.py", `
"backend/data/fssai_rules.json", `
"backend/data/category_weights.json", `
"backend/data/vague_claims_lexicon.txt"

# ---------- ML ----------
New-Item -ItemType Directory -Force -Path `
"ml/data/open_food_facts", `
"ml/data/indian_products"

New-Item -ItemType File -Force -Path `
"ml/data/annotated_claims.json", `
"ml/train_ner.py", `
"ml/train_classifier.py", `
"ml/evaluate.py"

# ---------- NOTEBOOKS ----------
New-Item -ItemType Directory -Force -Path "notebooks"

New-Item -ItemType File -Force -Path `
"notebooks/01_eda_open_food_facts.ipynb", `
"notebooks/02_annotation_analysis.ipynb", `
"notebooks/03_model_benchmarks.ipynb", `
"notebooks/04_contradiction_rule_validation.ipynb"

# ---------- README ----------
New-Item -ItemType File -Force -Path "README.md"

Write-Host "Structure created successfully."