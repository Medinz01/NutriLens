"""
routers/admin.py

Dev/transparency dashboard — phpMyAdmin-style for NutriLens.
- Full Postgres table view + truncate + row delete
- Full Redis key browser + delete + flush
- API endpoint registry
- Auto-refresh every 10s

Set ADMIN_READ_ONLY=true in .env to disable all destructive operations.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db
from cache import get_redis
from config import get_settings

router   = APIRouter()
settings = get_settings()


def _require_write():
    """Raise 403 if ADMIN_READ_ONLY is enabled."""
    if settings.admin_read_only:
        raise HTTPException(
            status_code=403,
            detail="Admin dashboard is in read-only mode. Set ADMIN_READ_ONLY=false to enable destructive operations."
        )


# ─── Postgres: read ───────────────────────────────────────────────────────────

@router.get("/admin/tables/products")
async def table_products(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT p.id, p.platform_name, p.platform_id, p.product_name, p.brand,
               p.url, p.created_at, p.last_extracted_at,
               nf.protein_g, nf.energy_kcal, nf.price_inr, nf.quantity_g,
               nf.price_per_100g, nf.serving_size_g, nf.source, nf.confidence,
               ps.total as score_total, ps.value_score, ps.quality_score,
               ps.integrity_score, ps.category,
               COUNT(DISTINCT ec.id) as claim_count,
               COUNT(DISTINCT cv.id) as verification_count
        FROM products p
        LEFT JOIN nutrition_facts nf ON nf.product_id = p.id
        LEFT JOIN product_scores ps  ON ps.product_id = p.id
        LEFT JOIN extracted_claims ec ON ec.product_id = p.id
        LEFT JOIN claim_verifications cv ON cv.product_id = p.id
        GROUP BY p.id, nf.id, ps.id
        ORDER BY p.last_extracted_at DESC
    """))
    cols = rows.keys()
    return [dict(zip(cols, r)) for r in rows.fetchall()]

@router.get("/admin/tables/claims")
async def table_claims(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT ec.id, ec.product_id, ec.raw_text, ec.classification_type,
               ec.confidence_score, ec.model_version, ec.created_at,
               p.product_name
        FROM extracted_claims ec
        JOIN products p ON p.id = ec.product_id
        ORDER BY ec.created_at DESC LIMIT 300
    """))
    cols = rows.keys()
    return [dict(zip(cols, r)) for r in rows.fetchall()]

@router.get("/admin/tables/verifications")
async def table_verifications(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT cv.id, cv.product_id, cv.claim_text, cv.nutrient,
               cv.claimed_val, cv.actual_val, cv.unit, cv.verdict,
               cv.explanation, cv.created_at, p.product_name
        FROM claim_verifications cv
        JOIN products p ON p.id = cv.product_id
        ORDER BY cv.created_at DESC LIMIT 300
    """))
    cols = rows.keys()
    return [dict(zip(cols, r)) for r in rows.fetchall()]

@router.get("/admin/tables/scores")
async def table_scores(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT ps.id, ps.product_id, ps.category,
               ps.value_score, ps.quality_score, ps.integrity_score, ps.total,
               ps.computed_at, p.product_name, p.brand
        FROM product_scores ps
        JOIN products p ON p.id = ps.product_id
        ORDER BY ps.computed_at DESC
    """))
    cols = rows.keys()
    return [dict(zip(cols, r)) for r in rows.fetchall()]

@router.get("/admin/tables/nutrition")
async def table_nutrition(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT nf.id, nf.product_id, nf.price_inr, nf.quantity_g,
               nf.serving_size_g, nf.energy_kcal, nf.protein_g,
               nf.carbohydrates_g, nf.sugar_g, nf.total_fat_g,
               nf.saturated_fat_g, nf.sodium_mg, nf.source,
               nf.confidence, p.product_name
        FROM nutrition_facts nf
        JOIN products p ON p.id = nf.product_id
        ORDER BY nf.id DESC
    """))
    cols = rows.keys()
    return [dict(zip(cols, r)) for r in rows.fetchall()]

@router.get("/admin/tables/jobs")
async def table_jobs(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT id, product_id, status, eta_seconds, error, created_at, updated_at
        FROM analysis_jobs
        ORDER BY created_at DESC LIMIT 100
    """))
    cols = rows.keys()
    return [dict(zip(cols, r)) for r in rows.fetchall()]

@router.get("/admin/stats")
async def admin_stats(db: AsyncSession = Depends(get_db)):
    stats = {}
    for table in ["products","extracted_claims","claim_verifications",
                  "nutrition_facts","product_scores","analysis_jobs"]:
        r = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
        stats[table] = r.scalar()
    return stats

# ─── Postgres: destructive ────────────────────────────────────────────────────

TRUNCATABLE = {
    "products", "extracted_claims", "claim_verifications",
    "nutrition_facts", "product_scores", "analysis_jobs"
}

@router.delete("/admin/tables/{table}")
async def truncate_table(table: str, db: AsyncSession = Depends(get_db)):
    _require_write()
    if table not in TRUNCATABLE:
        return JSONResponse({"error": "unknown table"}, status_code=400)
    await db.execute(text(f"TRUNCATE {table} CASCADE"))
    await db.commit()
    return {"ok": True, "truncated": table}

@router.delete("/admin/tables/{table}/row/{row_id}")
async def delete_row(table: str, row_id: str, db: AsyncSession = Depends(get_db)):
    _require_write()
    if table not in TRUNCATABLE:
        return JSONResponse({"error": "unknown table"}, status_code=400)
    pk   = "id"
    cast = "" if table == "products" else "::integer"
    await db.execute(text(f"DELETE FROM {table} WHERE {pk} = :id{cast}"),
                     {"id": row_id})
    await db.commit()
    return {"ok": True, "deleted": row_id}

# ─── Redis: read ──────────────────────────────────────────────────────────────

@router.get("/admin/redis")
async def redis_all():
    r    = await get_redis()
    keys = await r.keys("*")
    keys.sort()

    result = []
    for key in keys:
        ktype = await r.type(key)
        ttl   = await r.ttl(key)

        if ktype == "string":
            raw = await r.get(key)
            try:
                import json
                val = json.loads(raw)
                if isinstance(val, dict) and len(str(val)) > 400:
                    preview = {k: v for k, v in list(val.items())[:6]}
                    preview["…"] = f"({len(val)} keys total)"
                else:
                    preview = val
            except Exception:
                preview = raw[:200] if raw else ""
        else:
            preview = f"[{ktype}]"

        result.append({"key": key, "type": ktype, "ttl": ttl, "preview": preview})
    return result

@router.get("/admin/redis/key")
async def redis_get_key(key: str):
    r   = await get_redis()
    raw = await r.get(key)
    if raw is None:
        return JSONResponse({"error": "key not found"}, status_code=404)
    try:
        import json
        return json.loads(raw)
    except Exception:
        return {"raw": raw}

@router.delete("/admin/redis/key")
async def redis_delete_key(key: str):
    _require_write()
    r = await get_redis()
    await r.delete(key)
    return {"ok": True, "deleted": key}

@router.delete("/admin/redis/flush")
async def redis_flush():
    _require_write()
    r = await get_redis()
    await r.flushdb()
    return {"ok": True, "message": "Redis flushed"}

@router.delete("/admin/redis/flush/products")
async def redis_flush_products():
    _require_write()
    r    = await get_redis()
    keys = await r.keys("product:*")
    if keys:
        await r.delete(*keys)
    return {"ok": True, "deleted": len(keys), "keys": keys}

# ─── Endpoint registry ────────────────────────────────────────────────────────

ENDPOINTS = [
    {"method":"POST","path":"/api/v1/products/submit","description":"Submit product from extension. Saves to Postgres + enqueues Celery job.","body":"platform, platform_id, url, claims[], nutrition_facts, fssai, price_inr, quantity_g","response":"{ cached, job_id?, data? }"},
    {"method":"GET", "path":"/api/v1/jobs/{job_id}","description":"Poll Celery job status until complete.","response":"{ status, data?, error? }"},
    {"method":"GET", "path":"/admin","description":"This dashboard.","response":"HTML"},
    {"method":"GET", "path":"/admin/stats","description":"Row counts for all Postgres tables.","response":"{ products: N, extracted_claims: N, … }"},
    {"method":"GET", "path":"/admin/tables/products","description":"All products with joined nutrition + scores.","response":"Array"},
    {"method":"GET", "path":"/admin/tables/claims","description":"All extracted marketing claims.","response":"Array"},
    {"method":"GET", "path":"/admin/tables/verifications","description":"Per-claim numeric verification results.","response":"Array"},
    {"method":"GET", "path":"/admin/tables/scores","description":"Accountability scores per product.","response":"Array"},
    {"method":"GET", "path":"/admin/tables/nutrition","description":"Nutrition facts per product.","response":"Array"},
    {"method":"GET", "path":"/admin/tables/jobs","description":"Celery job queue history.","response":"Array"},
    {"method":"DELETE","path":"/admin/tables/{table}","description":"TRUNCATE a Postgres table (CASCADE). Blocked in ADMIN_READ_ONLY mode.","body":"table name in path","response":"{ ok, truncated }"},
    {"method":"DELETE","path":"/admin/tables/{table}/row/{id}","description":"Delete a single row by ID. Blocked in ADMIN_READ_ONLY mode.","response":"{ ok, deleted }"},
    {"method":"GET", "path":"/admin/redis","description":"All Redis keys with type, TTL, and value preview.","response":"Array"},
    {"method":"GET", "path":"/admin/redis/key?key=X","description":"Full value of a single Redis key.","response":"Parsed JSON or raw string"},
    {"method":"DELETE","path":"/admin/redis/key?key=X","description":"Delete a single Redis key. Blocked in ADMIN_READ_ONLY mode.","response":"{ ok, deleted }"},
    {"method":"DELETE","path":"/admin/redis/flush","description":"Flush entire Redis DB. Blocked in ADMIN_READ_ONLY mode.","response":"{ ok }"},
    {"method":"DELETE","path":"/admin/redis/flush/products","description":"Delete only product: cache keys. Blocked in ADMIN_READ_ONLY mode.","response":"{ ok, deleted: N }"},
    {"method":"GET", "path":"/health","description":"Health check.","response":"{ status, version }"},
]

@router.get("/admin/endpoints")
async def list_endpoints():
    return ENDPOINTS

# ─── Read-only mode indicator ─────────────────────────────────────────────────

@router.get("/admin/mode")
async def admin_mode():
    return {"read_only": settings.admin_read_only}

# ─── Dashboard HTML ───────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NutriLens — Dev Console</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:#0d0f12; --surface:#141720; --surface2:#1a1f2e; --border:#1e2330;
  --green:#00d084; --green-dim:#00d08420; --amber:#f5a623; --red:#ff4757;
  --blue:#3d8bff; --purple:#a78bfa;
  --text:#e2e8f0; --muted:#4a5568;
  --mono:'IBM Plex Mono',monospace; --sans:'IBM Plex Sans',sans-serif;
}
body { background:var(--bg); color:var(--text); font-family:var(--sans); font-size:13px; }
header {
  border-bottom:1px solid var(--border); padding:14px 28px;
  display:flex; align-items:center; justify-content:space-between;
  position:sticky; top:0; background:var(--bg); z-index:100;
}
.logo { font-family:var(--mono); font-size:15px; font-weight:600; color:var(--green);
  display:flex; align-items:center; gap:10px; }
.dot { width:7px; height:7px; border-radius:50%; background:var(--green);
  box-shadow:0 0 8px var(--green); animation:pulse 2s infinite; }
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.header-right { display:flex; align-items:center; gap:14px; }
.live-pill { font-family:var(--mono); font-size:10px; color:var(--green);
  border:1px solid var(--green); border-radius:3px; padding:2px 8px; letter-spacing:.1em; }
.ro-pill { font-family:var(--mono); font-size:10px; color:var(--amber);
  border:1px solid var(--amber); border-radius:3px; padding:2px 8px; letter-spacing:.1em;
  display:none; }
#tick { font-family:var(--mono); font-size:11px; color:var(--muted); }
.layout { display:grid; grid-template-columns:210px 1fr; min-height:calc(100vh - 53px); }
aside {
  border-right:1px solid var(--border); padding:20px 0;
  position:sticky; top:53px; height:calc(100vh - 53px); overflow-y:auto;
}
.sb-section { padding:0 14px; margin-bottom:20px; }
.sb-label { font-family:var(--mono); font-size:10px; letter-spacing:.12em;
  color:var(--muted); text-transform:uppercase; margin-bottom:8px; padding:0 4px; }
.nav { display:flex; align-items:center; justify-content:space-between;
  padding:6px 10px; border-radius:6px; cursor:pointer; font-size:12px;
  color:var(--text); margin-bottom:2px; border:1px solid transparent; transition:all .12s; }
.nav:hover { background:var(--surface); border-color:var(--border); }
.nav.active { background:var(--green-dim); border-color:var(--green); color:var(--green); }
.nav.redis-nav.active { background:#3d8bff18; border-color:var(--blue); color:var(--blue); }
.cnt { font-family:var(--mono); font-size:10px; background:var(--surface);
  border-radius:3px; padding:1px 5px; color:var(--muted); }
main { padding:24px 28px; overflow:hidden; }
.stats { display:grid; grid-template-columns:repeat(auto-fill,minmax(110px,1fr)); gap:10px; margin-bottom:24px; }
.stat { background:var(--surface); border:1px solid var(--border); border-radius:7px; padding:12px 14px; }
.stat-l { font-size:10px; color:var(--muted); margin-bottom:3px; }
.stat-v { font-family:var(--mono); font-size:20px; font-weight:600; color:var(--green); }
.sh { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }
.sh-title { font-family:var(--mono); font-size:12px; font-weight:600; color:var(--green); letter-spacing:.06em; }
.sh-sub { font-size:11px; color:var(--muted); margin-top:2px; }
.sh-actions { display:flex; gap:8px; align-items:center; }
.btn { font-family:var(--mono); font-size:11px; border-radius:5px; padding:5px 12px;
  border:1px solid; cursor:pointer; transition:all .12s; }
.btn-danger { border-color:var(--red); color:var(--red); background:none; }
.btn-danger:hover { background:#ff475718; }
.btn-muted { border-color:var(--border); color:var(--muted); background:none; }
.btn-muted:hover { background:var(--surface); color:var(--text); }
.btn-green { border-color:var(--green); color:var(--green); background:none; }
.btn-green:hover { background:var(--green-dim); }
.btn[disabled] { opacity:0.3; cursor:not-allowed; pointer-events:none; }
.ro-banner { background:#f5a62318; border:1px solid #f5a62340; border-radius:7px;
  padding:10px 16px; margin-bottom:16px; font-size:12px; color:var(--amber);
  font-family:var(--mono); display:none; }
.table-wrap { overflow-x:auto; border:1px solid var(--border); border-radius:8px; }
table { width:100%; border-collapse:collapse; font-size:11px; }
thead { background:var(--surface); }
th { font-family:var(--mono); font-size:9px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--muted); padding:9px 12px; text-align:left; border-bottom:1px solid var(--border); white-space:nowrap; }
td { padding:8px 12px; border-bottom:1px solid var(--border); max-width:260px;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:var(--surface); }
.mono { font-family:var(--mono); font-size:10px; color:var(--muted); }
.col-green { color:var(--green); font-family:var(--mono); font-weight:600; }
.col-red   { color:var(--red);   font-family:var(--mono); }
.col-amber { color:var(--amber); font-family:var(--mono); }
.col-blue  { color:var(--blue);  font-family:var(--mono); }
.badge { display:inline-block; border-radius:3px; padding:2px 6px;
  font-size:9px; font-family:var(--mono); font-weight:600; letter-spacing:.04em; }
.b-green  { background:#00d08418; color:var(--green); border:1px solid #00d08440; }
.b-red    { background:#ff475718; color:var(--red);   border:1px solid #ff475740; }
.b-amber  { background:#f5a62318; color:var(--amber); border:1px solid #f5a62340; }
.b-blue   { background:#3d8bff18; color:var(--blue);  border:1px solid #3d8bff40; }
.b-purple { background:#a78bfa18; color:var(--purple);border:1px solid #a78bfa40; }
.b-muted  { background:#4a556818; color:var(--muted); border:1px solid #4a556840; }
.sbar { display:flex; align-items:center; gap:6px; }
.sbar-track { flex:1; height:3px; background:var(--border); border-radius:2px; min-width:50px; }
.sbar-fill  { height:3px; border-radius:2px; }
.redis-grid { display:flex; flex-direction:column; gap:8px; }
.redis-card { background:var(--surface); border:1px solid var(--border); border-radius:7px;
  padding:10px 14px; cursor:pointer; transition:border-color .12s; }
.redis-card:hover { border-color:var(--blue); }
.redis-top { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.redis-key { font-family:var(--mono); font-size:12px; color:var(--blue); flex:1;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.redis-ttl { font-family:var(--mono); font-size:10px; color:var(--muted); white-space:nowrap; }
.redis-preview { font-family:var(--mono); font-size:10px; color:var(--muted);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.redis-expanded { margin-top:10px; border-top:1px solid var(--border); padding-top:10px; }
pre { font-family:var(--mono); font-size:10px; color:var(--text);
  background:var(--bg); border-radius:5px; padding:10px; overflow-x:auto;
  max-height:300px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; }
.ep-grid { display:flex; flex-direction:column; gap:8px; }
.ep-card { background:var(--surface); border:1px solid var(--border); border-radius:7px; padding:12px 16px; }
.ep-top { display:flex; align-items:center; gap:10px; margin-bottom:5px; }
.method { font-family:var(--mono); font-size:10px; font-weight:600;
  padding:2px 7px; border-radius:3px; letter-spacing:.05em; }
.GET    { background:#00d08418; color:var(--green); }
.POST   { background:#3d8bff18; color:var(--blue);  }
.DELETE { background:#ff475718; color:var(--red);   }
.ep-path { font-family:var(--mono); font-size:12px; }
.ep-desc { font-size:11px; color:var(--muted); margin-bottom:4px; }
.ep-detail { font-family:var(--mono); font-size:10px; color:var(--muted); }
.ep-detail span { color:var(--amber); }
.modal-bg { position:fixed; inset:0; background:#0009; z-index:200;
  display:flex; align-items:center; justify-content:center; }
.modal { background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:24px; width:440px; max-width:90vw; }
.modal h3 { font-family:var(--mono); color:var(--red); margin-bottom:12px; font-size:14px; }
.modal p { color:var(--muted); font-size:12px; margin-bottom:18px; }
.modal-btns { display:flex; gap:10px; justify-content:flex-end; }
.empty { text-align:center; padding:40px; color:var(--muted); font-size:12px; }
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>

<header>
  <div class="logo"><div class="dot"></div>NutriLens / dev console</div>
  <div class="header-right">
    <span class="ro-pill" id="ro-pill">READ ONLY</span>
    <span class="live-pill">LIVE</span>
    <span id="tick">refresh in 10s</span>
  </div>
</header>

<div class="layout">
<aside>
  <div class="sb-section">
    <div class="sb-label">Overview</div>
    <div class="nav active" id="nav-endpoints" onclick="show('endpoints',this)">API Endpoints</div>
  </div>
  <div class="sb-section">
    <div class="sb-label">PostgreSQL</div>
    <div class="nav" id="nav-products"      onclick="show('products',this)">Products       <span class="cnt" id="c-products">—</span></div>
    <div class="nav" id="nav-claims"        onclick="show('claims',this)">Claims          <span class="cnt" id="c-claims">—</span></div>
    <div class="nav" id="nav-verifications" onclick="show('verifications',this)">Verifications  <span class="cnt" id="c-verifications">—</span></div>
    <div class="nav" id="nav-nutrition"     onclick="show('nutrition',this)">Nutrition Facts <span class="cnt" id="c-nutrition">—</span></div>
    <div class="nav" id="nav-scores"        onclick="show('scores',this)">Scores          <span class="cnt" id="c-scores">—</span></div>
    <div class="nav" id="nav-jobs"          onclick="show('jobs',this)">Jobs             <span class="cnt" id="c-jobs">—</span></div>
  </div>
  <div class="sb-section">
    <div class="sb-label">Redis Cache</div>
    <div class="nav redis-nav" id="nav-redis" onclick="show('redis',this)">All Keys <span class="cnt" id="c-redis">—</span></div>
  </div>
</aside>

<main id="main"><div class="empty">Loading…</div></main>
</div>

<div class="modal-bg" id="modal" style="display:none" onclick="closeModal()">
  <div class="modal" onclick="event.stopPropagation()">
    <h3 id="modal-title">Confirm</h3>
    <p id="modal-body"></p>
    <div class="modal-btns">
      <button class="btn btn-muted" onclick="closeModal()">Cancel</button>
      <button class="btn btn-danger" id="modal-confirm">Confirm</button>
    </div>
  </div>
</div>

<script>
let currentView = 'endpoints';
let stats = {};
let countdown = 10;
let READ_ONLY = false;

// ── Read-only mode ────────────────────────────────────────────────────────────
async function loadMode() {
  try {
    const m = await api('/admin/mode');
    READ_ONLY = m.read_only;
    if (READ_ONLY) {
      document.getElementById('ro-pill').style.display = 'inline-block';
      document.querySelectorAll('.ro-banner').forEach(b => b.style.display = 'block');
    }
  } catch(e) {}
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function confirm(title, body, fn) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').textContent  = body;
  document.getElementById('modal-confirm').onclick   = () => { closeModal(); fn(); };
  document.getElementById('modal').style.display     = 'flex';
}
function closeModal() { document.getElementById('modal').style.display = 'none'; }

// ── Nav ───────────────────────────────────────────────────────────────────────
function show(view, el) {
  currentView = view;
  document.querySelectorAll('.nav').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  render();
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const s = await api('/admin/stats');
    stats = s;
    document.getElementById('c-products').textContent      = s.products || 0;
    document.getElementById('c-claims').textContent        = s.extracted_claims || 0;
    document.getElementById('c-verifications').textContent = s.claim_verifications || 0;
    document.getElementById('c-nutrition').textContent     = s.nutrition_facts || 0;
    document.getElementById('c-scores').textContent        = s.product_scores || 0;
    document.getElementById('c-jobs').textContent          = s.analysis_jobs || 0;
  } catch(e) {}
  try {
    const rk = await api('/admin/redis');
    document.getElementById('c-redis').textContent = rk.length;
  } catch(e) {}
}

function statsBar() {
  const items = [
    ['Products',stats.products],['Claims',stats.extracted_claims],
    ['Verifications',stats.claim_verifications],['Nutrition Facts',stats.nutrition_facts],
    ['Scores',stats.product_scores],['Jobs',stats.analysis_jobs],
  ];
  return `<div class="stats">${items.map(([l,v])=>`
    <div class="stat"><div class="stat-l">${l}</div><div class="stat-v">${v??'—'}</div></div>
  `).join('')}</div>`;
}

function roBanner() {
  return READ_ONLY
    ? `<div class="ro-banner" style="display:block">⚠ Read-only mode — destructive operations are disabled. Set ADMIN_READ_ONLY=false in .env to enable.</div>`
    : '';
}

async function api(url, method='GET') {
  const r = await fetch(url, { method });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function render() {
  const main = document.getElementById('main');
  main.innerHTML = '<div class="empty">Loading…</div>';
  try {
    if (currentView === 'endpoints') await renderEndpoints();
    else if (currentView === 'redis') await renderRedis();
    else                              await renderTable(currentView);
  } catch(e) {
    main.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
  }
}

async function renderEndpoints() {
  const data   = await api('/admin/endpoints');
  const colors = { GET:'green', POST:'blue', DELETE:'red' };
  document.getElementById('main').innerHTML = statsBar() + roBanner() + `
    <div class="sh"><div><div class="sh-title">API ENDPOINTS</div>
      <div class="sh-sub">All endpoints are public. Raw JSON at each GET path.</div></div></div>
    <div class="ep-grid">${data.map(ep=>`
      <div class="ep-card">
        <div class="ep-top">
          <span class="method ${ep.method}">${ep.method}</span>
          <span class="ep-path">${ep.path}</span>
          ${ep.method==='GET'?`<a href="${ep.path.replace('{job_id}','example').replace('{table}','products').replace('{id}','1')}" target="_blank" style="margin-left:auto;font-size:10px;color:var(--muted);text-decoration:none">↗</a>`:''}
        </div>
        <div class="ep-desc">${ep.description}</div>
        ${ep.body?`<div class="ep-detail">body: <span>${ep.body}</span></div>`:''}
        <div class="ep-detail">returns: <span>${ep.response}</span></div>
      </div>`).join('')}
    </div>`;
}

const T = {
  products: {
    title:'PRODUCTS', sub:'Every product page visited.',
    cols:['platform_id','product_name','brand','price_inr','quantity_g','protein_g','score_total','claim_count','verification_count','source','last_extracted_at'],
    cell(r,c){
      if(c==='platform_id') return `<td class="mono"><a href="${r.url}" target="_blank" style="color:var(--blue)">${r[c]}</a></td>`;
      if(c==='score_total') return scoreCell(r[c]);
      if(c==='protein_g')   return `<td class="col-green">${r[c]!=null?r[c]+'g':'—'}</td>`;
      if(c==='price_inr')   return `<td>₹${r[c]??'—'}</td>`;
      if(c==='source')      return badge(r[c],{extension_dom:'muted',ocr_verified:'green',manual_verified:'amber'});
      if(c==='last_extracted_at') return `<td class="mono">${ago(r[c])}</td>`;
      return `<td title="${r[c]??''}">${cut(r[c],38)}</td>`;
    },
    deleteBtn:true, truncateBtn:true,
  },
  claims: {
    title:'EXTRACTED CLAIMS', sub:'Marketing bullets from product pages.',
    cols:['id','product_id','product_name','raw_text','classification_type','model_version','created_at'],
    cell(r,c){
      if(c==='raw_text') return `<td title="${r[c]}">${cut(r[c],70)}</td>`;
      if(c==='classification_type') return badge(r[c],{FACTUAL:'green',CERTIFIED:'blue',VAGUE:'amber',MISLEADING:'red'});
      if(c==='created_at') return `<td class="mono">${ago(r[c])}</td>`;
      return `<td class="mono">${cut(r[c],28)}</td>`;
    },
    deleteBtn:true, truncateBtn:true,
  },
  verifications: {
    title:'CLAIM VERIFICATIONS', sub:'Numeric claims cross-checked against label data.',
    cols:['id','product_id','product_name','claim_text','nutrient','claimed_val','actual_val','unit','verdict','explanation'],
    cell(r,c){
      if(c==='verdict') return badge(r[c],{verified:'green',contradicted:'red',unverifiable:'amber'});
      if(c==='claim_text'||c==='explanation') return `<td title="${r[c]??''}">${cut(r[c],55)}</td>`;
      if(c==='claimed_val'||c==='actual_val') return `<td class="mono">${r[c]??'—'}</td>`;
      return `<td>${cut(r[c],28)}</td>`;
    },
    deleteBtn:true, truncateBtn:true,
  },
  nutrition: {
    title:'NUTRITION FACTS', sub:'Per-100g values extracted from DOM or OCR.',
    cols:['id','product_id','product_name','energy_kcal','protein_g','carbohydrates_g','sugar_g','total_fat_g','sodium_mg','serving_size_g','source','confidence'],
    cell(r,c){
      if(c==='protein_g')   return `<td class="col-green">${r[c]??'—'}</td>`;
      if(c==='energy_kcal') return `<td class="col-amber">${r[c]??'—'}</td>`;
      if(c==='source')      return badge(r[c],{extension_dom:'muted',ocr_verified:'green'});
      return `<td class="mono">${r[c]??'—'}</td>`;
    },
    deleteBtn:true, truncateBtn:true,
  },
  scores: {
    title:'ACCOUNTABILITY SCORES', sub:'value (35%) + quality (30%) + integrity (35%)',
    cols:['id','product_id','product_name','brand','category','value_score','quality_score','integrity_score','total','computed_at'],
    cell(r,c){
      if(c==='total') return scoreCell(r[c]);
      if(['value_score','quality_score','integrity_score'].includes(c)) return miniScore(r[c]);
      if(c==='computed_at') return `<td class="mono">${ago(r[c])}</td>`;
      return `<td>${cut(r[c],28)}</td>`;
    },
    deleteBtn:true, truncateBtn:true,
  },
  jobs: {
    title:'ANALYSIS JOBS', sub:'Celery background task queue.',
    cols:['id','product_id','status','eta_seconds','error','created_at'],
    cell(r,c){
      if(c==='status') return badge(r[c],{queued:'muted',processing:'amber',complete:'green',failed:'red'});
      if(c==='id') return `<td class="mono">${r[c]?.slice(0,8)}…</td>`;
      if(c==='created_at') return `<td class="mono">${ago(r[c])}</td>`;
      if(c==='error') return `<td class="col-red">${cut(r[c],38)}</td>`;
      return `<td class="mono">${r[c]??'—'}</td>`;
    },
    deleteBtn:false, truncateBtn:true,
  },
};

async function renderTable(name) {
  const cfg  = T[name];
  const data = await api(`/admin/tables/${name}`);
  const main = document.getElementById('main');

  const actions = `
    <div class="sh-actions">
      <a href="/admin/tables/${name}" target="_blank" class="btn btn-muted">↗ JSON</a>
      ${cfg.truncateBtn ? `<button class="btn btn-danger" ${READ_ONLY?'disabled':''} onclick="truncateTable('${name}')">🗑 Truncate</button>` : ''}
    </div>`;

  if (!data.length) {
    main.innerHTML = statsBar() + roBanner() + `<div class="sh"><div>
      <div class="sh-title">${cfg.title}</div><div class="sh-sub">${cfg.sub}</div>
    </div>${actions}</div><div class="empty">No rows yet.</div>`;
    return;
  }

  main.innerHTML = statsBar() + roBanner() + `
    <div class="sh"><div>
      <div class="sh-title">${cfg.title}</div>
      <div class="sh-sub">${cfg.sub} — ${data.length} rows</div>
    </div>${actions}</div>
    <div class="table-wrap"><table>
      <thead><tr>
        ${cfg.cols.map(c=>`<th>${c.replace(/_/g,' ')}</th>`).join('')}
        ${cfg.deleteBtn ? '<th>del</th>' : ''}
      </tr></thead>
      <tbody>${data.map(r=>`<tr>
        ${cfg.cols.map(c=>cfg.cell(r,c)).join('')}
        ${cfg.deleteBtn ? `<td><button class="btn btn-danger" style="padding:2px 7px" ${READ_ONLY?'disabled':''} onclick="deleteRow('${name}','${r.id}')">×</button></td>` : ''}
      </tr>`).join('')}</tbody>
    </table></div>`;
}

async function renderRedis() {
  const data = await api('/admin/redis');
  const main = document.getElementById('main');

  const header = `
    <div class="sh">
      <div><div class="sh-title" style="color:var(--blue)">REDIS CACHE</div>
      <div class="sh-sub">${data.length} keys — click to expand full value</div></div>
      <div class="sh-actions">
        <button class="btn btn-muted" ${READ_ONLY?'disabled':''} onclick="flushRedisProducts()">🗑 Flush product: keys</button>
        <button class="btn btn-danger" ${READ_ONLY?'disabled':''} onclick="flushRedis()">⚠ Flush all Redis</button>
      </div>
    </div>`;

  if (!data.length) {
    main.innerHTML = statsBar() + roBanner() + header + '<div class="empty">Redis is empty.</div>';
    return;
  }
  main.innerHTML = statsBar() + roBanner() + header + `<div class="redis-grid">
    ${data.map((item,i) => redisCard(item, i)).join('')}
  </div>`;
}

function redisCard(item, i) {
  const ttlLabel = item.ttl === -1 ? 'no TTL' : item.ttl < 0 ? 'expired' : `TTL ${item.ttl}s`;
  const typeColor = item.type==='string' ? 'b-blue' : 'b-muted';
  const preview = typeof item.preview === 'object'
    ? JSON.stringify(item.preview, null, 2).slice(0, 200)
    : String(item.preview || '').slice(0, 200);
  return `<div class="redis-card" id="rc-${i}">
    <div class="redis-top">
      <span class="badge ${typeColor}">${item.type}</span>
      <span class="redis-key">${item.key}</span>
      <span class="redis-ttl">${ttlLabel}</span>
      <button class="btn btn-muted" style="padding:2px 8px;font-size:10px" onclick="event.stopPropagation();expandRedis('${item.key}','rc-${i}')">expand</button>
      <button class="btn btn-danger" style="padding:2px 8px;font-size:10px" ${READ_ONLY?'disabled':''} onclick="event.stopPropagation();deleteRedisKey('${escHtml(item.key)}')">×</button>
    </div>
    <div class="redis-preview">${escHtml(preview)}</div>
    <div class="redis-expanded" id="re-${i}" style="display:none"></div>
  </div>`;
}

async function expandRedis(key, cardId) {
  const idx = cardId.replace('rc-','');
  const el  = document.getElementById(`re-${idx}`);
  if (el.style.display !== 'none') { el.style.display='none'; return; }
  try {
    const data = await api(`/admin/redis/key?key=${encodeURIComponent(key)}`);
    el.innerHTML = `<pre>${escHtml(JSON.stringify(data, null, 2))}</pre>`;
    el.style.display = 'block';
  } catch(e) {
    el.innerHTML = `<div style="color:var(--red);font-size:11px">${e.message}</div>`;
    el.style.display = 'block';
  }
}

async function truncateTable(name) {
  confirm(`Truncate ${name}?`,
    `This will delete ALL rows from ${name} (CASCADE). Cannot be undone.`,
    async () => { await api(`/admin/tables/${name}`, 'DELETE'); await loadStats(); render(); });
}
async function deleteRow(table, id) {
  await api(`/admin/tables/${table}/row/${id}`, 'DELETE');
  render();
}
async function deleteRedisKey(key) {
  await api(`/admin/redis/key?key=${encodeURIComponent(key)}`, 'DELETE');
  await loadStats(); render();
}
async function flushRedis() {
  confirm('Flush ALL Redis?',
    'Deletes every key in Redis — products cache AND job statuses.',
    async () => { await api('/admin/redis/flush', 'DELETE'); await loadStats(); render(); });
}
async function flushRedisProducts() {
  confirm('Flush product: cache?',
    'Deletes all product:* keys. Job keys are preserved.',
    async () => { await api('/admin/redis/flush/products', 'DELETE'); await loadStats(); render(); });
}

function cut(v,n){ if(v==null) return '<span style="color:var(--muted)">—</span>'; const s=String(v); return s.length>n?s.slice(0,n)+'…':s; }
function ago(iso){ if(!iso) return '—'; const d=Math.floor((Date.now()-new Date(iso))/1000); if(d<60) return d+'s ago'; if(d<3600) return Math.floor(d/60)+'m ago'; if(d<86400) return Math.floor(d/3600)+'h ago'; return new Date(iso).toLocaleDateString(); }
function escHtml(s){ return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function badge(v, map){ if(!v) return `<td><span class="badge b-muted">—</span></td>`; const cls='b-'+(map[v]||'muted'); return `<td><span class="badge ${cls}">${v}</span></td>`; }
function scoreCell(v){ if(v==null) return '<td class="mono">—</td>'; const c=v>=7?'var(--green)':v>=5?'var(--amber)':'var(--red)'; return `<td><span style="font-family:var(--mono);font-weight:700;font-size:12px;color:${c}">${v}/10</span></td>`; }
function miniScore(v){ if(v==null) return '<td class="mono">—</td>'; const c=v>=7?'var(--green)':v>=5?'var(--amber)':'var(--red)'; const p=(v/10)*100; return `<td><div class="sbar"><span style="font-family:var(--mono);font-size:10px;color:${c};width:22px">${v}</span><div class="sbar-track"><div class="sbar-fill" style="width:${p}%;background:${c}"></div></div></div></td>`; }

function tick(){ countdown--; document.getElementById('tick').textContent=`refresh in ${countdown}s`; if(countdown<=0){ countdown=10; loadStats(); render(); } }

loadMode(); loadStats(); render(); setInterval(tick, 1000);
</script>
</body></html>"""