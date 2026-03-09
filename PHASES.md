# NutriLens — Development Phases

Full build log from first commit to production. Updated as phases complete.

---

## ✅ Phase 1 — Chrome Extension Foundation
*March 2, 2026*

Chrome MV3 extension scaffold with React popup, content script, and service worker. Establish DOM extraction and build pipeline.

- Chrome MV3 extension scaffold — Vite + React
- `amazon.js` content script — DOM extraction of name, brand, price, quantity
- `background.js` service worker — session storage, message routing
- Popup UI skeleton
- Build pipeline (npm run build → chrome://extensions)

---

## ✅ Phase 2 — Backend Infrastructure
*March 3, 2026*

Stand up FastAPI with PostgreSQL, Redis, and Celery. Define full database schema.

- FastAPI app with async SQLAlchemy
- PostgreSQL schema — Products, NutritionFacts, ExtractedClaims, Contradictions, ProductScores, AnalysisJobs
- Redis for cache (30-day TTL) + Celery broker
- Docker Compose wiring all services
- CORS configured for Chrome extension origin

---

## ✅ Phase 3 — Extension ↔ Backend Wiring
*March 3, 2026*

Connect the extension to the backend end-to-end.

- Extension POSTs product payload on every page load
- Celery worker skeleton for async analysis
- Job polling — submit → job_id → poll every 2s → SCORES_READY broadcast
- MV3 service worker persistence fixes
- Price parser fixes for Indian number format

---

## ✅ Phase 4 — OCR Pipeline
*March 3–4, 2026*

Separate OCR microservice with PaddleOCR. Two-pass pipeline for accurate per-100g nutrition extraction from label images.

- Separate OCR microservice in Docker
- Two-pass pipeline — Tesseract PSM11 keyword scoring → PaddleOCR spatial extraction
- Coordinate-based spatial parser using bounding box x/y positions (outperforms line-by-line)
- Per-100g column detection, serving range sanity validation, x-cap for amino acid tables
- Snippet capture UI — drag-select overlay on Amazon's HD image viewer
- Base64 image transfer, threading lock for PaddleOCR concurrency
- Benchmark: 11/11 correct nutrients on reference label image

---

## ✅ Phase 5 — Data Quality & FSSAI
*March 4, 2026*

FSSAI licence extraction, NutriScore, and column detection improvements.

- FSSAI extraction from seller About page — DOM fetch, regex, 14-digit state code validation
- Semantic parser column detection fixes — relative x_cap threshold (0.85 × image width)
- NutriScore A–E computed per-100g per FSSAI thresholds
- CompareTable with Protein/₹100 as primary comparison dimension
- Per-100g adopted as canonical unit throughout

---

## ✅ Phase 6 — Accountability Layer ← current
*March 7, 2026*

Full claims pipeline — extract, store, classify, verify, score. Admin dashboard.

- Structured claims extraction — each bullet with DOM selector and element index
- Claims saved to PostgreSQL on every page load (deduplicated)
- Clickable claims — tap to scroll + yellow highlight on product page
- Certification links — Labdoor, Informed Choice, Informed Sport, Trustified, NSF
- Numeric claim checker — cross-validates claimed values vs label with 15% tolerance
- Accountability score — value (35%) + quality (30%) + integrity (35%)
- ClaimVerification table — verdict per claim: verified / contradicted / unverifiable
- Normalizer bug fixed — per-100g OCR values no longer double-multiplied
- Admin transparency dashboard — live Postgres + Redis browser, truncate/delete/flush

---

## 🔲 Phase 7 — LLM Claim Intelligence

Upgrade claim classification from regex rules to LLM reasoning.

- Groq free tier (llama3-8b) or Ollama (local) in the Celery worker
- Deep claim classification — efficacy, comparative, superlative, ingredient sourcing
- Integrity score upgraded to LLM-verified
- Study citation extraction for efficacy claims ("clinically proven", "50% faster absorption")
- Contradiction detection — flag when label data contradicts marketing copy

---

## 🔲 Phase 8 — Multi-Platform

Extend content scripts to BigBasket and Flipkart.

- BigBasket content script — category page + product detail
- Flipkart content script — nutrition table format differs from Amazon
- Platform-agnostic extractor interface in `background.js`

---

## 🔲 Phase 9 — Product History & Discovery

Persistent view of everything the user has scanned.

- `GET /api/v1/products/history` — paginated from PostgreSQL
- Third tab in popup — Previously Scanned with search and filter
- Category leaderboard — best accountability score per category
- Price drop alerts for tracked products

---

## 🔲 Phase 10 — Production

Harden, deploy, publish to Chrome Web Store.

- Auth on write endpoints (API key or JWT)
- Rate limiting on `/products/submit`
- Production deploy — Railway / Render / VPS
- `/admin` in read-only mode for public access (`ADMIN_READ_ONLY=true`)
- Chrome Web Store submission
