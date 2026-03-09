# Contributing to NutriLens

Thanks for taking the time to contribute. NutriLens is an accountability tool for Indian consumers — the more people who contribute data, rules, and platform support, the more useful it becomes.

## Table of Contents

- [Getting Started](#getting-started)
- [Ways to Contribute](#ways-to-contribute)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Submitting a PR](#submitting-a-pr)
- [Adding a Platform](#adding-a-platform)

---

## Getting Started

1. Fork the repo and clone your fork
2. Follow the [Quick Start](README.md#-quick-start) to get a local backend running
3. Pick an issue tagged `good first issue` or `help wanted`
4. Open a PR — we review within a few days

For larger changes (new platform, new scoring dimension), open an issue first to discuss the approach.

---

## Ways to Contribute

### 🐛 Bug reports
Open an issue with the product URL, what you expected, and what NutriLens returned. Screenshots of the popup help.

### 🔌 New platform content scripts
BigBasket and Flipkart are the next priority. See [Adding a Platform](#adding-a-platform) below.

### 🔢 Scoring improvements
The scoring benchmarks (`BENCHMARKS` dict in `backend/engines/ranker.py`) need per-category data. If you have FSSAI compliance data or published nutritional benchmarks for Indian products, open a PR.

### 🧪 Tests
The OCR parser and scoring engine have no automated tests. The test harness in `ocr-service/test_extraction.py` is a good starting point.

### 🧹 Noise filter improvements
`amazon.js` has a `NOISE_PATTERNS` array that filters UI text from marketing claims. If you find bullets that should be filtered (or shouldn't be), a one-line PR is welcome.

### 🌐 Translations / localisation
The popup is English-only. Hindi and Tamil translations would significantly increase the user base.

---

## Development Setup

### Backend

```bash
cp .env.example .env
docker compose up
```

After changing any Python file in `backend/` or `ocr-service/`:
```bash
docker compose restart api worker   # or: ocr
```

Check logs:
```bash
docker compose logs api --tail=50
docker compose logs worker --tail=50
```

Database access (psql):
```bash
docker compose exec db psql -U nutrilens -d nutrilens
```

### Extension

```bash
cd extension
npm install
npm run dev     # Vite dev mode — rebuilds on save
```

After `npm run build`, reload the extension at `chrome://extensions`.

### OCR service

The first run downloads PaddleOCR models (~200MB). They are cached in a Docker volume so subsequent starts are fast. Test OCR extraction directly:

```bash
docker compose exec ocr python test_extraction.py path/to/label.jpg
```

---

## Code Style

### Python
- Follow PEP 8
- Type hints on all function signatures
- Docstring on every module (single paragraph, present tense)
- No `print()` — use `logging`

### JavaScript / JSX
- ESLint default config (from `package.json`)
- No default exports except React components
- Content script functions must be pure — no module state that survives page navigation

### Commits
```
type(scope): short description

Types: feat, fix, refactor, test, docs, chore
Scope: extension, backend, ocr, docker, ci

Examples:
  feat(extension): add BigBasket content script
  fix(backend): correct per-100g double-multiplication in normalizer
  docs: update OCR architecture diagram
```

---

## Submitting a PR

1. Branch from `main`: `git checkout -b feat/your-feature`
2. Write or update tests if touching scoring or parsing logic
3. Run the backend and manually test the end-to-end flow on at least one Amazon.in product
4. Check the `/admin` dashboard to confirm your changes produce correct DB rows
5. Open a PR against `main` — fill in the template

PRs that only touch one concern (one platform, one bug, one feature) are much easier to review and merge quickly.

---

## Adding a Platform

1. Create `extension/content_scripts/{platform}.js` — model it on `amazon.js`
2. Export the same shape: `{ platform, platform_id, product_name, brand, price_inr, quantity_g, claims[], nutrition_facts{}, serving_size_g }`
3. Register the content script in `manifest.json` under `content_scripts` with the platform's URL match pattern
4. Test on at least 10 product pages across different categories
5. Note any structural differences from Amazon (e.g. BigBasket shows nutrition per serving only) in a comment at the top of the file

The backend is platform-agnostic — as long as the payload matches `ProductSubmitRequest` in `backend/models/schemas.py`, no backend changes are needed.

---

## Questions?

Open a discussion in the GitHub Discussions tab. For security issues, see [SECURITY.md](SECURITY.md).
