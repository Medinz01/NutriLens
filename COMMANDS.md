# NutriLens — Dev Commands Reference

## Paths
```
PROJECTS/
├── nutrilens-extension/
└── ocr-service/
```

---

## OCR Service

```bash
cd C:\Users\mdsma\Documents\PROJECTS\ocr-service

# Start server (keep this running)
docker compose up ocr

# Start in background
docker compose up ocr -d

# View logs (if running in background)
docker compose logs -f ocr

# Stop
docker compose down

# Rebuild (only needed after requirements change)
docker compose build ocr
docker compose up ocr

# Health check
curl http://localhost:8001/health

# Test OCR directly with a local image
curl -X POST http://localhost:8001/extract/image ^
  -H "Content-Type: application/json" ^
  -d "{\"image\": \"$(base64 -w0 test_images/t4.jpg)\"}"

# Run test harness (all 6 images)
docker compose run --rm ocr python test_layout_extraction.py

# Run test harness (single image)
docker compose run --rm ocr python test_layout_extraction.py test_images/t4.jpg
```

> **Note:** `semantic_parser.py`, `layout_engine.py`, `extractor.py` are volume-mounted.  
> Edit and save → uvicorn auto-reloads. No rebuild needed.

---

## Extension

```bash
cd C:\Users\mdsma\Documents\PROJECTS\nutrilens-extension

# Install dependencies (first time only)
npm install

# Build for Chrome
npm run build

# Watch mode — rebuilds on every file save
npm run dev
```

### Load / Reload in Chrome
```
1. chrome://extensions
2. Enable Developer mode (top right)
3. Click "Load unpacked" → select dist/ folder   ← first time only
4. After every build → click ↺ reload on NutriLens card
```

---

## Full Dev Session

Open two terminals in VS Code (`nutrilens.code-workspace`):

| Terminal 1 — OCR Service         | Terminal 2 — Extension            |
|----------------------------------|-----------------------------------|
| `cd ocr-service`                 | `cd nutrilens-extension`          |
| `docker compose up ocr`          | `npm run dev`                     |
| Runs on `http://localhost:8001`  | Rebuilds on file save             |

Then after any extension file change:
```
chrome://extensions → ↺ reload NutriLens
```

---

## Test the Snippet Flow

```
1. Go to any Amazon.in protein powder product page
2. Click the product image to open Amazon's HD zoom viewer
3. Click NutriLens extension icon
4. Click "📷 Scan Nutrition Label"
5. Popup closes — page darkens — crosshair cursor appears
6. Drag a box tightly over the nutrition table only
7. Release → scanning starts
8. Click extension icon → see extracted nutrients
```

---

## Troubleshooting

```bash
# OCR service not responding
curl http://localhost:8001/health

# Models downloading every run (volume missing)
docker volume ls | grep paddle
# Should show: ocr-service_paddle_models

# Extension changes not reflecting
# → Always rebuild + reload after any JS/JSX change
npm run build
# then chrome://extensions → ↺

# Snip overlay not appearing
# → Check browser console on the Amazon tab (F12)
# → Should see no errors in content_scripts/snip.js

# OCR returning wrong values
# → Edit semantic_parser.py directly
# → uvicorn reloads automatically (no docker restart needed)
```

---

## Ports

| Service       | Port   |
|---------------|--------|
| OCR Service   | 8001   |
| Main Backend  | 8000   |
