#!/usr/bin/env python3
"""Import a Hugging Face model's metadata into the model-momento SQLite DB.

Usage:
    python import_hf.py <repo_id> [<repo_id> ...]   # exact 'owner/name'
"""
import sqlite3
import sys
import urllib.request
import json
from pathlib import Path

DB = Path(__file__).resolve().parent / "model_momento.db"
API = "https://huggingface.co/api/models/{}"


def fetch(repo_id: str) -> dict:
    url = API.format(repo_id)
    with urllib.request.urlopen(url, timeout=30) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} for {repo_id}")
        return json.load(r)


def upsert(cur, repo_id: str, d: dict):
    card = d.get("cardData") or {}
    config = d.get("config") or {}
    siblings = d.get("siblings") or []
    has_gguf = any(s.get("rfilename", "").endswith(".gguf") for s in siblings)
    params = d.get("safetensors", {}).get("total") if d.get("safetensors") else None

    cur.execute(
        """
        INSERT INTO model (repo_id, sha, pipeline_tag, library_name, license,
                           architecture, params_count, quantization, context_length,
                           downloads, likes, hf_url, hf_created_at, last_modified,
                           card_last_updated, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(repo_id) DO UPDATE SET
            sha=excluded.sha, pipeline_tag=excluded.pipeline_tag,
            library_name=excluded.library_name, license=excluded.license,
            architecture=excluded.architecture, params_count=excluded.params_count,
            quantization=excluded.quantization, context_length=excluded.context_length,
            downloads=excluded.downloads, likes=excluded.likes, hf_url=excluded.hf_url,
            hf_created_at=excluded.hf_created_at, last_modified=excluded.last_modified,
            card_last_updated=excluded.card_last_updated, updated_at=CURRENT_TIMESTAMP
        """,
        (
            repo_id,
            d.get("sha"),
            d.get("pipeline_tag"),
            d.get("library_name"),
            d.get("cardData", {}).get("license") if isinstance(d.get("cardData", {}).get("license"), str) else ",".join(d.get("cardData", {}).get("license") or []) or d.get("license"),
            config.get("model_type"),
            params,
            "GGUF" if has_gguf else None,
            (config.get("max_position_embeddings")),
            d.get("downloads"),
            d.get("likes"),
            f"https://huggingface.co/{repo_id}",
            d.get("createdAt"),
            d.get("lastModified"),
            (d.get("cardData") or {}).get("last_updated"),
        ),
    )
    cur.execute("SELECT model_id FROM model WHERE repo_id=?", (repo_id,))
    model_id = cur.fetchone()[0]

    for tag in d.get("tags") or []:
        cur.execute(
            "INSERT OR IGNORE INTO model_tag (model_id, tag) VALUES (?,?)",
            (model_id, tag),
        )
    for lang in d.get("config", {}).get("languages") or card.get("language") or []:
        cur.execute(
            "INSERT OR IGNORE INTO model_language (model_id, lang_code) VALUES (?,?)",
            (model_id, lang),
        )
    for ds in d.get("cardData", {}).get("datasets") or []:
        cur.execute(
            "INSERT OR IGNORE INTO model_dataset (model_id, dataset_repo_id) VALUES (?,?)",
            (model_id, ds),
        )
    base = d.get("cardData", {}).get("base_model")
    if base:
        bases = base if isinstance(base, list) else [base]
        for b in bases:
            rel = "quantized" if has_gguf else "finetune"
            cur.execute(
                "INSERT OR IGNORE INTO model_base (model_id, base_repo_id, relation) VALUES (?,?,?)",
                (model_id, b, rel),
            )


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: import_hf.py <repo_id> [<repo_id> ...]")
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON")
    for repo_id in sys.argv[1:]:
        d = fetch(repo_id)
        with con:
            upsert(con.cursor(), repo_id, d)
        print(f"imported {repo_id}")
    con.close()


if __name__ == "__main__":
    main()
