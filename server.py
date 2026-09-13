#!/usr/bin/env python3
"""model-momento API — FastAPI CRUD + search over the SQLite DB, serves the SPA."""
import sqlite3
from pathlib import Path
from typing import Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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


# ---------- SPA ----------
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
