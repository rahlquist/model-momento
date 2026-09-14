#!/usr/bin/env python3
"""model-momento API — FastAPI CRUD + search over the SQLite DB, serves the SPA."""
import sqlite3
from pathlib import Path
from typing import Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
DB = ROOT / "model_momento.db"

app = FastAPI(title="model-momento")


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def rows(c, sql, params=()):
    return [dict(r) for r in c.execute(sql, params)]


# ---------- models CRUD ----------

class ModelIn(BaseModel):
    repo_id: str
    sha: Optional[str] = None
    pipeline_tag: Optional[str] = None
    library_name: Optional[str] = None
    license: Optional[str] = None
    model_type: Optional[str] = None
    architecture: Optional[str] = None
    params_count: Optional[int] = None
    quantization: Optional[str] = None
    context_length: Optional[int] = None
    downloads: Optional[int] = None
    likes: Optional[int] = None
    hf_url: Optional[str] = None
    tags: list[str] = []


@app.get("/api/models")
def list_models(q: Optional[str] = None, tag: Optional[str] = None,
                pipeline_tag: Optional[str] = None, limit: int = 100):
    sql = "SELECT * FROM model WHERE 1=1"
    params: list[Any] = []
    if q:
        sql += " AND (repo_id LIKE ? OR architecture LIKE ? OR license LIKE ? OR pipeline_tag LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like, like]
    if tag:
        sql += " AND repo_id IN (SELECT model_id FROM model_tag WHERE tag = ?)"
        params.append(tag)
    if pipeline_tag:
        sql += " AND pipeline_tag = ?"
        params.append(pipeline_tag)
    sql += " ORDER BY repo_id LIMIT ?"
    params.append(limit)
    c = con()
    out = rows(c, sql, params)
    for m in out:
        m["tags"] = [r["tag"] for r in c.execute(
            "SELECT tag FROM model_tag WHERE model_id=?", (m["model_id"],))]
    c.close()
    return out


@app.get("/api/models/{model_id}")
def get_model(model_id: int):
    c = con()
    m = c.execute("SELECT * FROM model WHERE model_id=?", (model_id,)).fetchone()
    if not m:
        c.close()
        raise HTTPException(404, "model not found")
    out = dict(m)
    out["tags"] = [r["tag"] for r in c.execute(
        "SELECT tag FROM model_tag WHERE model_id=?", (model_id,))]
    out["languages"] = [r["lang_code"] for r in c.execute(
        "SELECT lang_code FROM model_language WHERE model_id=?", (model_id,))]
    out["datasets"] = [r["dataset_repo_id"] for r in c.execute(
        "SELECT dataset_repo_id FROM model_dataset WHERE model_id=?", (model_id,))]
    out["bases"] = rows(c, "SELECT base_repo_id, relation FROM model_base WHERE model_id=?", (model_id,))
    out["evals"] = rows(c, "SELECT benchmark_name, score, variant, source FROM model_eval WHERE model_id=?", (model_id,))
    out["note_list"] = rows(c, "SELECT note_id, note_date, author, category, note FROM model_note WHERE model_id=? ORDER BY note_date DESC", (model_id,))
    out["runs"] = rows(c, "SELECT run_id, run_date, host, backend, verdict, summary FROM test_run WHERE model_id=? ORDER BY run_date DESC", (model_id,))
    pf = c.execute("SELECT * FROM perfect_for WHERE model_id=?", (model_id,)).fetchone()
    out["perfect_for"] = dict(pf) if pf else None
    c.close()
    return out


@app.post("/api/models", status_code=201)
def create_model(m: ModelIn):
    c = con()
    try:
        with c:
            cur = c.execute(
                "INSERT INTO model (repo_id, sha, pipeline_tag, library_name, license, model_type, architecture, params_count, quantization, context_length, downloads, likes, hf_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (m.repo_id, m.sha, m.pipeline_tag, m.library_name, m.license, m.model_type, m.architecture, m.params_count, m.quantization, m.context_length, m.downloads, m.likes, m.hf_url or (f"https://huggingface.co/{m.repo_id}")),
            )
            mid = cur.lastrowid
            for t in m.tags:
                c.execute("INSERT OR IGNORE INTO model_tag (model_id, tag) VALUES (?,?)", (mid, t))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"repo_id '{m.repo_id}' already exists")
    c.close()
    return {"model_id": mid, "repo_id": m.repo_id}


@app.put("/api/models/{model_id}")
def update_model(model_id: int, m: ModelIn):
    c = con()
    if not c.execute("SELECT 1 FROM model WHERE model_id=?", (model_id,)).fetchone():
        c.close()
        raise HTTPException(404, "model not found")
    with c:
        c.execute(
            "UPDATE model SET repo_id=?, sha=?, pipeline_tag=?, library_name=?, license=?, model_type=?, architecture=?, params_count=?, quantization=?, context_length=?, downloads=?, likes=?, hf_url=? WHERE model_id=?",
            (m.repo_id, m.sha, m.pipeline_tag, m.library_name, m.license, m.model_type, m.architecture, m.params_count, m.quantization, m.context_length, m.downloads, m.likes, m.hf_url, model_id),
        )
        c.execute("DELETE FROM model_tag WHERE model_id=?", (model_id,))
        for t in m.tags:
            c.execute("INSERT OR IGNORE INTO model_tag (model_id, tag) VALUES (?,?)", (model_id, t))
    c.close()
    return {"ok": True}


@app.delete("/api/models/{model_id}")
def delete_model(model_id: int):
    c = con()
    with c:
        cur = c.execute("DELETE FROM model WHERE model_id=?", (model_id,))
    c.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "model not found")
    return {"ok": True, "deleted": model_id}


# ---------- notes ----------

class NoteIn(BaseModel):
    model_id: int
    author: Optional[str] = "richard"
    category: Optional[str] = None
    note: str
    run_id: Optional[int] = None  # optional link to a test run


@app.post("/api/notes", status_code=201)
def add_note(n: NoteIn):
    c = con()
    if n.run_id is not None and not c.execute("SELECT 1 FROM test_run WHERE run_id=?", (n.run_id,)).fetchone():
        c.close()
        raise HTTPException(404, "test_run not found")
    with c:
        cur = c.execute(
            "INSERT INTO model_note (model_id, note_date, author, category, note) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?)",
            (n.model_id, n.author, n.category, n.note),
        )
        note_id = cur.lastrowid
    c.close()
    return {"note_id": note_id}


# ---------- test runs ----------

class MetricIn(BaseModel):
    metric_name: str
    value: float
    unit: Optional[str] = None


class RunIn(BaseModel):
    model_id: int
    host: Optional[str] = None
    backend: Optional[str] = None
    prompt_template: Optional[str] = None
    ctx_size: Optional[int] = None
    benchmark_suite: Optional[str] = None
    verdict: Optional[str] = None
    summary: Optional[str] = None
    metrics: list[MetricIn] = []
    note: Optional[str] = None  # convenience: also create a model_note


@app.post("/api/runs", status_code=201)
def add_run(r: RunIn):
    c = con()
    if not c.execute("SELECT 1 FROM model WHERE model_id=?", (r.model_id,)).fetchone():
        c.close()
        raise HTTPException(404, "model not found")
    if r.verdict and r.verdict not in ("keep", "reject", "investigate"):
        c.close()
        raise HTTPException(422, "verdict must be keep|reject|investigate")
    with c:
        cur = c.execute(
            "INSERT INTO test_run (model_id, run_date, host, backend, prompt_template, ctx_size, benchmark_suite, verdict, summary) VALUES (?, CURRENT_TIMESTAMP, ?,?,?,?,?,?,?)",
            (r.model_id, r.host, r.backend, r.prompt_template, r.ctx_size, r.benchmark_suite, r.verdict, r.summary),
        )
        run_id = cur.lastrowid
        for m in r.metrics:
            c.execute("INSERT OR IGNORE INTO test_metric (run_id, metric_name, value, unit) VALUES (?,?,?,?)",
                      (run_id, m.metric_name, m.value, m.unit))
        if r.note:
            c.execute("INSERT INTO model_note (model_id, note_date, author, category, note) VALUES (?, CURRENT_TIMESTAMP, 'richard', 'benchmark', ?)",
                      (r.model_id, r.note))
    c.close()
    return {"run_id": run_id}


@app.get("/api/runs")
def list_runs(model_id: Optional[int] = None, limit: int = 100):
    sql = "SELECT * FROM test_run"
    params: list[Any] = []
    if model_id:
        sql += " WHERE model_id=?"
        params.append(model_id)
    sql += " ORDER BY run_date DESC LIMIT ?"
    params.append(limit)
    c = con()
    out = rows(c, sql, params)
    for r in out:
        r["metrics"] = rows(c, "SELECT metric_name, value, unit FROM test_metric WHERE run_id=?", (r["run_id"],))
    c.close()
    return out


# ---------- evals (claimed scores) ----------

class EvalIn(BaseModel):
    model_id: int
    benchmark_name: str
    score: float
    variant: Optional[str] = None
    source: Optional[str] = "card"


@app.post("/api/evals", status_code=201)
def add_eval(e: EvalIn):
    c = con()
    if not c.execute("SELECT 1 FROM model WHERE model_id=?", (e.model_id,)).fetchone():
        c.close()
        raise HTTPException(404, "model not found")
    with c:
        c.execute(
            "INSERT OR REPLACE INTO model_eval (model_id, benchmark_name, score, variant, source) VALUES (?,?,?,?,?)",
            (e.model_id, e.benchmark_name, e.score, e.variant, e.source),
        )
    c.close()
    return {"ok": True}


@app.get("/api/search")
def search(q: str):
    """Cross-table quick search: models, notes, run summaries, benchmarks."""
    like = f"%{q}%"
    c = con()
    models = rows(c, "SELECT model_id, repo_id, architecture, license FROM model WHERE repo_id LIKE ? OR architecture LIKE ? LIMIT 25", (like, like))
    notes = rows(c, "SELECT n.note_id, n.model_id, m.repo_id, n.category, n.note FROM model_note n JOIN model m ON m.model_id=n.model_id WHERE n.note LIKE ? LIMIT 25", (like,))
    runs = rows(c, "SELECT r.run_id, r.model_id, m.repo_id, r.benchmark_suite, r.summary, r.verdict FROM test_run r JOIN model m ON m.model_id=r.model_id WHERE r.summary LIKE ? OR r.benchmark_suite LIKE ? LIMIT 25", (like, like))
    evals = rows(c, "SELECT e.model_id, m.repo_id, e.benchmark_name, e.score, e.variant, e.source FROM model_eval e JOIN model m ON m.model_id=e.model_id WHERE e.benchmark_name LIKE ? LIMIT 25", (like,))
    c.close()
    return {"models": models, "notes": notes, "runs": runs, "evals": evals}


# ---------- HF import via API ----------

class ImportIn(BaseModel):
    repo_ids: list[str]


@app.post("/api/import")
def import_models(payload: ImportIn):
    import urllib.request, json as _json
    out = []
    c = con()
    for repo_id in payload.repo_ids:
        try:
            url = f"https://huggingface.co/api/models/{repo_id}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                d = _json.load(resp)
            card = d.get("cardData") or {}
            lic = card.get("license")
            if isinstance(lic, list):
                lic = ",".join(lic)
            params = (d.get("safetensors") or {}).get("total")
            with c:
                c.execute(
                    """INSERT INTO model (repo_id, sha, pipeline_tag, library_name, license, architecture, params_count, quantization, context_length, downloads, likes, hf_url, hf_created_at, last_modified)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(repo_id) DO UPDATE SET sha=excluded.sha, pipeline_tag=excluded.pipeline_tag,
                         library_name=excluded.library_name, license=excluded.license, architecture=excluded.architecture,
                         params_count=excluded.params_count, downloads=excluded.downloads, likes=excluded.likes,
                         hf_url=excluded.hf_url, hf_created_at=excluded.hf_created_at, last_modified=excluded.last_modified""",
                    (repo_id, d.get("sha"), d.get("pipeline_tag"), d.get("library_name"), lic,
                     (d.get("config") or {}).get("model_type"), params,
                     "GGUF" if any(s.get("rfilename","").endswith(".gguf") for s in d.get("siblings") or []) else None,
                     (d.get("config") or {}).get("max_position_embeddings"),
                     d.get("downloads"), d.get("likes"), f"https://huggingface.co/{repo_id}",
                     d.get("createdAt"), d.get("lastModified")),
                )
                mid = c.execute("SELECT model_id FROM model WHERE repo_id=?", (repo_id,)).fetchone()[0]
                for t in d.get("tags") or []:
                    c.execute("INSERT OR IGNORE INTO model_tag (model_id, tag) VALUES (?,?)", (mid, t))
            out.append({"repo_id": repo_id, "ok": True, "model_id": mid})
        except Exception as e:
            out.append({"repo_id": repo_id, "ok": False, "error": str(e)})
    c.close()
    return out


@app.get("/api/models/{model_id}/card.png")
def model_card_png(model_id: int):
    """Render a branded markdown-style card as a PNG with a QR code to the HF page."""
    import io
    import qrcode
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from urllib.request import urlopen

    c = con()
    m = c.execute("SELECT * FROM model WHERE model_id=?", (model_id,)).fetchone()
    if not m:
        c.close()
        raise HTTPException(404, "model not found")
    m = dict(m)
    m["tags"] = [r["tag"] for r in c.execute("SELECT tag FROM model_tag WHERE model_id=?", (model_id,))]
    m["evals"] = rows(c, "SELECT benchmark_name, score, variant, source FROM model_eval WHERE model_id=?", (model_id,))
    m["runs"] = rows(c, "SELECT run_date, host, backend, verdict FROM test_run WHERE model_id=?", (model_id,))
    m["note_list"] = rows(c, "SELECT note, note_date, category FROM model_note WHERE model_id=? ORDER BY note_date DESC LIMIT 5", (model_id,))
    c.close()

    url = m["hf_url"] or f"https://huggingface.co/{m['repo_id']}"
    W, PAD = 1300, 52               # 30% larger canvas than v0.2.0 (1000/40)
    # fonts/QR stay at their original pixel sizes per spec
    BG0, BG1 = (10, 16, 32), (5, 8, 15)          # navy center -> near-black corners
    FG, MUTED, ACCENT = "#e2e6ee", "#8b93a3", "#4f9dff"
    NEON = [(79, 157, 255), (155, 89, 255), (0, 230, 190), (255, 170, 60)]  # blue/violet/teal/amber

    def neon_bg():
        """Navy radial gradient + blueprint grid + neon bloom blobs, blurred."""
        import math
        base = Image.new("RGB", (W, 1800))
        px = base.load()
        cx, cy, maxd = W / 2, 900, math.hypot(W / 2, 900)
        for yy in range(1800):
            for xx in range(0, W, 2):
                d = math.hypot(xx - cx, yy - cy) / maxd
                t = max(0.0, 1 - d) ** 1.6
                r = int(BG1[0] + (BG0[0] - BG1[0]) * t)
                g = int(BG1[1] + (BG0[1] - BG1[1]) * t)
                b = int(BG1[2] + (BG0[2] - BG1[2]) * t)
                px[xx, yy] = (r, g, b)
                if xx + 1 < W:
                    px[xx + 1, yy] = (r, g, b)
        # faint blueprint grid
        gline = ImageDraw.Draw(base, "RGBA")
        step = 52
        for gx in range(0, W, step):
            gline.line([(gx, 0), (gx, 1800)], fill=(90, 140, 220, 14), width=1)
        for gy in range(0, 1800, step):
            gline.line([(0, gy), (W, gy)], fill=(90, 140, 220, 14), width=1)
        # neon bloom: soft colored blobs
        glow = Image.new("RGB", (W, 1800), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        blobs = [(0.12, 0.10, 90), (0.90, 0.28, 70), (0.15, 0.62, 80),
                 (0.88, 0.80, 75), (0.50, 0.95, 60)]
        for (fx, fy, rad), col in zip(blobs, NEON):
            gd.ellipse([W*fx - rad, 1800*fy - rad, W*fx + rad, 1800*fy + rad], fill=col)
        glow = glow.filter(ImageFilter.GaussianBlur(120))
        from PIL import ImageChops
        base = ImageChops.add(base, glow)
        return base

    img = neon_bg()
    draw = ImageDraw.Draw(img)
    y = PAD

    def font(size, bold=False):
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
                  "/usr/share/fonts/TTF/DejaVuSans%s.ttf" % ("-Bold" if bold else "")):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
        return ImageFont.load_default(size)

    def wrap(text, f, maxw):
        lines = []
        for para in text.split("\n"):
            line = ""
            for w in para.split():
                t = (line + " " + w).strip()
                if draw.textlength(t, font=f) <= maxw:
                    line = t
                else:
                    if line: lines.append(line)
                    line = w
            lines.append(line)
        return lines

    def text(s, size, color=FG, bold=False, dy=0):
        nonlocal y
        f = font(size, bold)
        for ln in wrap(s, f, W - 2*PAD - 320):
            draw.text((PAD, y), ln, font=f, fill=color)
            y += size + 8
        y += dy

    f_title = font(44, True)
    TITLE_MAX = W - 2*PAD - 320      # keep clear of the QR block
    size = 44
    while size > 18 and draw.textlength(m["repo_id"], font=font(size, True)) > TITLE_MAX:
        size -= 2
    draw.text((PAD, y), m["repo_id"], font=font(size, True), fill=ACCENT)
    y += size + 14

    def fmt_params(n):
        if not n: return "?"
        return f"{n/1e9:.1f}B" if n >= 1e9 else f"{n/1e6:.0f}M"

    meta = [
        ("Pipeline", m["pipeline_tag"]), ("Library", m["library_name"]),
        ("License", m["license"]), ("Architecture", m["architecture"]),
        ("Params", fmt_params(m["params_count"])), ("Quantization", m["quantization"]),
        ("Context", m["context_length"]), ("Downloads", m["downloads"]),
    ]
    f_lbl, f_val = font(22, True), font(22)
    for k, v in meta:
        if v in (None, ""): continue
        draw.text((PAD, y), f"{k}:", font=f_lbl, fill=MUTED)
        draw.text((PAD + 170, y), str(v), font=f_val, fill=FG)
        y += 32
    if m["tags"]:
        y += 8
        for ln in wrap("Tags: " + ", ".join(m["tags"][:8]), f_val, W - 2*PAD - 320):
            draw.text((PAD, y), ln, font=f_val, fill=MUTED)
            y += 30
    y += 14

    if m["evals"]:
        text("Claimed evals", 26, ACCENT, True)
        for e in m["evals"][:6]:
            text(f"• {e['benchmark_name']}" + (f" ({e['variant']})" if e["variant"] else "") + f": {e['score']}", 22, FG)
        y += 8
    if m["runs"]:
        text("Test runs", 26, ACCENT, True)
        for r in m["runs"][:4]:
            text(f"• {str(r['run_date'])[:16]} {r['host'] or ''} — {r['verdict'] or '—'}", 22, FG)
        y += 8
    if m["note_list"]:
        text("Notes", 26, ACCENT, True)
        for n in m["note_list"]:
            for ln in wrap(f"• {n['note']}", f_val, W - 2*PAD - 320):
                draw.text((PAD, y), ln, font=f_val, fill=FG)
                y += 30
            y += 4

    # QR code, top-right — SAME pixel size as v0.2.0 (260), same corner anchor
    qr = qrcode.QRCode(box_size=6, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="#ffffff", back_color="#0a1020").convert("RGB")
    QS = 260
    qimg = qimg.resize((QS, QS), Image.NEAREST)
    img.paste(qimg, (W - PAD - QS, PAD + 10))
    f_qr = font(16)
    for i, ln in enumerate(wrap("Scan to open", f_qr, QS)):
        draw.text((W - PAD - QS, PAD + QS + 18 + i*20), ln, font=f_qr, fill=MUTED)

    # courtesy line, bottom-left, small
    f_c = font(16)
    y = max(y + 24, 70)          # ensure room below content
    draw.text((PAD, y), "card courtesy of @sovthpaw creator of TurboFit", font=f_c, fill=MUTED)
    y += 30

    out = img.crop((0, 0, W, min(img.height, y)))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


# ---------- perfect_for ----------

VRAM_FIELDS = ["vram_256gb","vram_128gb","vram_64gb","vram_32gb","vram_22gb",
               "vram_20gb","vram_16gb","vram_12gb","vram_8gb","vram_4gb","everything"]


class PerfectForIn(BaseModel):
    vram_256gb: bool = False
    vram_128gb: bool = False
    vram_64gb: bool = False
    vram_32gb: bool = False
    vram_22gb: bool = False
    vram_20gb: bool = False
    vram_16gb: bool = False
    vram_12gb: bool = False
    vram_8gb: bool = False
    vram_4gb: bool = False
    everything: bool = False


@app.get("/api/models/{model_id}/perfect_for")
def get_perfect_for(model_id: int):
    c = con()
    r = c.execute("SELECT * FROM perfect_for WHERE model_id=?", (model_id,)).fetchone()
    c.close()
    return dict(r) if r else None


@app.put("/api/models/{model_id}/perfect_for")
def set_perfect_for(model_id: int, p: PerfectForIn):
    c = con()
    if not c.execute("SELECT 1 FROM model WHERE model_id=?", (model_id,)).fetchone():
        c.close()
        raise HTTPException(404, "model not found")
    vals = {f: int(getattr(p, f)) for f in VRAM_FIELDS}
    cols = ",".join(vals)
    qs = ",".join("?" for _ in vals)
    with c:
        c.execute(
            f"INSERT INTO perfect_for (model_id, {cols}) VALUES (?, {qs}) "
            f"ON CONFLICT(model_id) DO UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in vals)}",
            (model_id, *vals.values()),
        )
    c.close()
    return {"ok": True, **vals}


# ---------- SPA ----------
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
