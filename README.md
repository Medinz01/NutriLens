<div align="center">

# 🥗 NutriLens

**Open-source nutrition accountability for Indian e-commerce**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docker.com)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Tests](https://img.shields.io/badge/tests-24%20passed-brightgreen.svg)](#)

NutriLens is a Chrome extension that sits on Amazon India product pages and tells you whether the marketing claims on a supplement actually match the nutrition label — and how good value for money the product really is.

[**Quick Start**](#-quick-start) · [**Architecture**](#-architecture) · [**Roadmap**](#-roadmap) · [**Contributing**](#-contributing) · [**Transparency Dashboard**](#-transparency-dashboard)

</div>

---

## Why NutriLens?

Supplement marketing in India is largely unregulated. Products claim "25g protein per serving" while the label shows 18g. "Clinically proven" appears on products with no published studies. Prices vary 4× for essentially the same formulation.

NutriLens extracts, stores, and cross-checks every claim against the actual nutrition label — and publishes the raw data openly so anyone can verify the results.

---

## ✨ Features

- **Automatic extraction** — visit any Amazon.in product page and NutriLens captures the product name, brand, price, quantity, and marketing claims from the DOM automatically
- **OCR nutrition scanning** — drag-select the nutrition label image and PaddleOCR extracts every nutrient per-100g
- **Claim verification** — numeric claims ("25g protein") are cross-checked against the label with a 15% tolerance; certified claims link out to Labdoor / Informed Choice / Trustified for external verification
- **Accountability score** — every product gets a score out of 10 across three dimensions:
  - **Value (35%)** — protein per ₹100 vs category average
  - **Quality (30%)** — protein %, sugar, saturated fat, sodium per 100g
  - **Integrity (35%)** — FSSAI compliance + numeric claim accuracy
- **NutriScore A–E** — standard European nutritional grade adapted for Indian FSSAI thresholds
- **Compare mode** — scan multiple products and compare scores side-by-side
- **Open transparency** — every extracted value is stored in a public Postgres database, browsable live at `/admin`

---

## 🏗 Architecture

```
Browser (Amazon.in)
  └── amazon.js  ──────────────────────────────────────────────────┐
       DOM extraction: name, brand, price, claims, FSSAI           │
       Snippet capture: drag-select → PaddleOCR → nutrition data   │
                                                                    ▼
                                                    ┌─── background.js (MV3 SW) ───┐
                                                    │  Session store               │
                                                    │  POST /api/v1/products/submit│
                                                    │  Poll /api/v1/jobs/{id}      │
                                                    └──────────────┬───────────────┘
                                                                   │
                              ┌────────────────────────────────────▼─────────────────────────────┐
                              │                        FastAPI  (port 8000)                       │
                              │   /products/submit  →  upsert DB  →  enqueue Celery job          │
                              │   /jobs/{id}        →  Redis job status poll                     │
                              │   /admin            →  live transparency dashboard (HTML)        │
                              └────────┬───────────────────────┬──────────────────────────────────┘
                                       │                       │
                              ┌────────▼──────┐      ┌────────▼────────┐
                              │  PostgreSQL   │      │  Redis          │
                              │  (permanent)  │      │  (cache + jobs) │
                              │               │      │  TTL 30 days    │
                              │  products     │      └─────────────────┘
                              │  nutrition_   │
                              │    facts      │               │
                              │  extracted_   │      ┌────────▼────────┐
                              │    claims     │      │  Celery Worker  │
                              │  claim_       │      │                 │
                              │    verific.   │◄─────│  normalize      │
                              │  product_     │      │  detect category│
                              │    scores     │      │  verify claims  │
                              └───────────────┘      │  compute score  │
                                                     └────────┬────────┘
                                                              │
                                                   ┌──────────▼──────────┐
                                                   │   OCR Microservice  │
                                                   │   (port 8001)       │
                                                   │                     │
                                                   │  Tesseract PSM11    │
                                                   │  (keyword scoring)  │
                                                   │       +             │
                                                   │  PaddleOCR 3.x      │
                                                   │  (spatial extract)  │
                                                   └─────────────────────┘
```

### Storage model

| Store | What lives there | Why |
|---|---|---|
| **PostgreSQL** | All extracted products, nutrition facts, claims, verifications, scores | Permanent source of truth; publicly queryable |
| **Redis** | Product cache keyed by `product:{platform}:{id}`, job status | Avoid re-processing recently scanned products (30-day TTL) |

---

## 🚀 Quick Start

### Prerequisites

- Docker + Docker Compose
- Node.js 18+
- Chrome (for the extension)

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/nutrilens.git
cd nutrilens
cp .env.example .env          # edit if needed — defaults work for local dev
```

### 2. Start the backend

```bash
docker compose up
```

This starts PostgreSQL, Redis, the FastAPI API, the Celery worker, and the OCR microservice. Tables are created automatically on first boot.

Wait for:
```
api_1     | INFO:     Application startup complete.
worker_1  | celery@... ready.
ocr_1     | INFO:     Application startup complete.
```

### 3. Load the extension

```bash
cd extension
npm install
npm run build
```

Open Chrome → `chrome://extensions` → Enable **Developer mode** → **Load unpacked** → select `extension/dist/`

### 4. Use it

1. Go to any Amazon.in protein supplement or health food page
2. The NutriLens icon appears in your toolbar — click it
3. Product info and marketing claims are extracted automatically
4. Click **📷 Scan Nutrition Label** → drag over the nutrition table image
5. Accountability score appears within ~10 seconds

### 5. Transparency dashboard

Open [http://localhost:8000/admin](http://localhost:8000/admin) to browse every extracted product, claim, and score in real time.

---

## 📁 Project Structure

```
nutrilens/
├── extension/                  # Chrome MV3 extension (React + Vite)
│   ├── content_scripts/
│   │   ├── amazon.js           # DOM extraction for Amazon.in
│   │   └── snip.js             # Drag-select snippet capture overlay
│   ├── popup/
│   │   ├── App.jsx             # Main popup UI
│   │   └── CompareTable.jsx    # Multi-product comparison view
│   ├── utils/
│   │   ├── api.js              # Backend communication
│   │   ├── normalizer.js       # Client-side nutrition normalisation
│   │   └── nutriscore.js       # NutriScore A–E calculation
│   ├── background.js           # MV3 service worker
│   └── manifest.json
│
├── backend/                    # FastAPI application
│   ├── routers/
│   │   ├── extract.py          # POST /products/submit, GET /jobs/{id}
│   │   ├── verify.py           # Claim verification endpoints
│   │   ├── rank.py             # Scoring endpoints
│   │   └── admin.py            # Transparency dashboard + DB/Redis browser
│   ├── engines/
│   │   ├── normalizer.py       # per-serving → per-100g, per-₹100
│   │   ├── ranker.py           # Accountability score computation
│   │   └── contradiction.py    # Claim vs label contradiction detection
│   ├── models/
│   │   ├── db_models.py        # SQLAlchemy ORM models
│   │   └── schemas.py          # Pydantic request/response schemas
│   ├── worker/
│   │   └── celery_app.py       # Async analysis pipeline
│   ├── main.py
│   ├── database.py
│   ├── cache.py                # Redis helpers
│   └── config.py
│
├── ocr-service/                # PaddleOCR microservice
│   ├── main.py                 # FastAPI wrapper
│   ├── extractor.py            # Two-pass pipeline orchestrator
│   ├── scanner.py              # Tesseract PSM11 pass
│   ├── semantic_parser.py      # PaddleOCR coordinate-based parser
│   └── parser.py               # Nutrient name normalisation
│
├── docker-compose.yml
├── .env.example
└── .gitignore
```

---

## ⚙️ Configuration

All configuration is via environment variables. Copy `.env.example` to `.env`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://nutrilens:nutrilens_dev@db:5432/nutrilens` | Async Postgres DSN |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery broker (separate DB) |
| `CACHE_TTL_SECONDS` | `2592000` | Product cache TTL (30 days) |
| `OCR_SERVICE_URL` | `http://ocr:8001` | Internal OCR microservice URL |

---

## 🔬 OCR Pipeline

The OCR microservice uses a **two-pass pipeline** to extract nutrition data from product label images:

**Pass 1 — Tesseract PSM11 (scoring)**
Runs lightweight OCR to detect nutrition-related keywords. Images that don't contain a nutrition table are rejected early.

**Pass 2 — PaddleOCR 3.x (extraction)**
Runs the full PaddleOCR model on images that passed the score threshold. Returns bounding box coordinates for every detected text block.

**Coordinate-based spatial parsing**
Rather than parsing text line-by-line, the parser uses `(x, y)` bounding box positions to spatially match nutrient names (left column) with their values (right column). This handles:
- Multi-column layouts (per serving + per 100g)
- Rotated or angled labels
- Amino acid tables (excluded via x-cap threshold)

Per-100g is used as the canonical unit throughout — Indian FSSAI standard and the only fair basis for cross-product comparison when serving sizes differ.

---

## 📊 Scoring Methodology

### Accountability Score (0–10)

| Dimension | Weight | What it measures |
|---|---|---|
| **Value** | 35% | Protein per ₹100 vs category benchmark |
| **Quality** | 30% | Protein %, sugar, saturated fat, sodium per 100g |
| **Integrity** | 35% | FSSAI licence present, numeric claims match label |

Integrity deductions:
- FSSAI not found: −3 points
- Each numeric contradiction (e.g. "25g protein" but label shows 18g): −2 points (max −4)

### NutriScore (A–E)

Computed per 100g using the standard European algorithm adapted for Indian thresholds. Negative points for energy, saturated fat, sugar, sodium. Positive points for protein, fibre. Final grade A (best) → E (worst).

### Value benchmark (protein powder)

| Benchmark | g protein / ₹100 |
|---|---|
| Category average | 26g |
| Good value | ≥ 28g |
| Poor value | ≤ 18g |

---

## 🔭 Transparency Dashboard

Every product NutriLens has ever scanned is publicly visible at `/admin`. This is intentional — accountability tools should themselves be accountable.

The dashboard shows:
- **Products** — every scanned product with price, protein content, and score
- **Claims** — every marketing bullet extracted from product pages
- **Verifications** — claim-by-claim verdict: `verified` / `contradicted` / `unverifiable`
- **Nutrition Facts** — raw per-100g values extracted from labels
- **Scores** — accountability scores with all three sub-dimensions
- **Jobs** — Celery worker queue history

Raw JSON available at every `/admin/tables/{table}` endpoint.

---

## 🗺 Roadmap

See [PHASES.md](PHASES.md) for the full build log. Current status:

- [x] Phase 1 — Chrome Extension Foundation
- [x] Phase 2 — Backend Infrastructure
- [x] Phase 3 — Extension ↔ Backend Wiring
- [x] Phase 4 — OCR Pipeline
- [x] Phase 5 — Data Quality & FSSAI
- [x] Phase 6 — Accountability Layer ← **current**
- [ ] Phase 7 — LLM Claim Intelligence (Groq / Ollama)
- [ ] Phase 8 — Multi-platform (BigBasket, Flipkart)
- [ ] Phase 9 — Product History & Discovery
- [ ] Phase 10 — Production Deploy + Chrome Web Store

---

## 🤝 Contributing

Contributions are very welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Good first issues:
- Adding a content script for BigBasket or Flipkart
- Improving the NutriScore algorithm for Indian food categories
- Writing tests for the OCR parser
- Adding more `NOISE_PATTERNS` to `amazon.js` claims extraction

---

## 📄 License

MIT — see [LICENSE](LICENSE). Data extracted and stored is publicly available for non-commercial use.

---

## ⚠️ Disclaimer

NutriLens is an independent research tool. It is not affiliated with Amazon, FSSAI, Labdoor, Informed Choice, or any brand. Scores are algorithmic — not dietary advice. Always consult a registered dietitian for health decisions.
