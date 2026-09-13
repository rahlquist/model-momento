# model-momento

SQLite-backed database of model info: HF metadata, your own local copies,
benchmark runs (claimed vs measured kept separate), and free-form notes.

## Layout
- `model_momento.db` — the database (10 tables, WAL, FK constraints)
- `schema.sql` — canonical schema, re-runnable into a fresh DB
- `import_hf.py` — CLI import from the Hugging Face Hub API
- `server.py` — FastAPI API + SPA host (port 8765)
- `web/index.html` — single-file web UI (no build step)
- `.venv/` — Python 3.12 venv (fastapi, uvicorn, httpx)

## Run
```bash
cd ~/model-momento
.venv/bin/python server.py        # http://127.0.0.1:8765
```

## CLI import
```bash
.venv/bin/python import_hf.py owner/model-name [owner/model-name ...]
```

## API
- `GET  /api/models?q=&tag=&pipeline_tag=&limit=` — list/filter
- `GET  /api/models/{id}` — full detail incl. tags, evals, runs, notes
- `POST /api/models` / `PUT /api/models/{id}` / `DELETE /api/models/{id}`
- `POST /api/notes` — add a note (`model_id`, `note`, optional `category`)
- `POST /api/runs` — record a benchmark run (+ metrics, + comment as note)
- `GET  /api/runs?model_id=` — list runs with metrics
- `POST /api/evals` — record a claimed benchmark score (card/leaderboard/self)
- `GET  /api/search?q=` — cross-table search (models, notes, runs, evals)
- `POST /api/import` — `{repo_ids: [...]}` import from HF

## Design notes
- `repo_id` (`owner/name`) is the exact natural key; duplicates are 409.
- `model_eval` = claimed scores; `test_metric` = your measured numbers. Never mixed.
- `updated_at` is bumped by triggers; SQLite FKs are per-connection — use
  `-cmd 'PRAGMA foreign_keys=ON'` in ad-hoc `sqlite3` sessions.
