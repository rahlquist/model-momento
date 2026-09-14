PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE model (
    model_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id         TEXT NOT NULL UNIQUE,          -- 'owner/name' exact
    sha             TEXT,                          -- commit hash
    pipeline_tag    TEXT,                          -- task
    library_name    TEXT,
    license         TEXT,
    model_type      TEXT,
    architecture    TEXT,
    params_count    INTEGER,
    quantization    TEXT,
    context_length  INTEGER,
    downloads       INTEGER,
    likes           INTEGER,
    hf_url          TEXT,
    hf_created_at   DATETIME,                      -- HF repo creation date
    last_modified   DATETIME,
    card_last_updated DATETIME,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE model_tag (
    model_id INTEGER NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    tag      TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model_id, tag)
);

CREATE TABLE model_language (
    model_id  INTEGER NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    lang_code TEXT NOT NULL,                        -- ISO 639-1
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model_id, lang_code)
);

CREATE TABLE model_dataset (
    model_id       INTEGER NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    dataset_repo_id TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model_id, dataset_repo_id)
);

CREATE TABLE model_base (
    model_id    INTEGER NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    base_repo_id TEXT NOT NULL,                    -- parent model repo id
    relation    TEXT CHECK (relation IN ('finetune','adapter','merge','quantized')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model_id, base_repo_id)
);

CREATE TABLE model_eval (
    model_id       INTEGER NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    benchmark_name TEXT NOT NULL,
    score          REAL,
    variant        TEXT,                           -- 5-shot, pass@1
    source         TEXT,                           -- card | leaderboard | self
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model_id, benchmark_name, variant)
);

CREATE TABLE model_local (
    model_id       INTEGER PRIMARY KEY REFERENCES model(model_id) ON DELETE CASCADE,
    local_path     TEXT,
    format         TEXT,
    file_sha256    TEXT,
    file_size_bytes INTEGER,
    serving_backend TEXT,
    host           TEXT,
    status         TEXT CHECK (status IN ('downloaded','missing','verified')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE test_run (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id     INTEGER NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    run_date     DATETIME NOT NULL,
    host         TEXT,
    backend      TEXT,
    prompt_template TEXT,
    ctx_size     INTEGER,
    benchmark_suite TEXT,
    verdict      TEXT CHECK (verdict IN ('keep','reject','investigate')),
    summary      TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE test_metric (
    run_id      INTEGER NOT NULL REFERENCES test_run(run_id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    value       REAL,
    unit        TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, metric_name)
);

CREATE TABLE model_note (
    note_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id  INTEGER NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    note_date DATETIME NOT NULL,
    author    TEXT,
    category  TEXT,      -- quality, refusal, humor, bug, ...
    note      TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE perfect_for (
    perfect_for_id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id       INTEGER NOT NULL UNIQUE REFERENCES model(model_id) ON DELETE CASCADE,
    vram_256gb     INTEGER NOT NULL DEFAULT 0 CHECK (vram_256gb IN (0,1)),
    vram_128gb     INTEGER NOT NULL DEFAULT 0 CHECK (vram_128gb IN (0,1)),
    vram_64gb      INTEGER NOT NULL DEFAULT 0 CHECK (vram_64gb IN (0,1)),
    vram_32gb      INTEGER NOT NULL DEFAULT 0 CHECK (vram_32gb IN (0,1)),
    vram_22gb      INTEGER NOT NULL DEFAULT 0 CHECK (vram_22gb IN (0,1)),
    vram_20gb      INTEGER NOT NULL DEFAULT 0 CHECK (vram_20gb IN (0,1)),
    vram_16gb      INTEGER NOT NULL DEFAULT 0 CHECK (vram_16gb IN (0,1)),
    vram_12gb      INTEGER NOT NULL DEFAULT 0 CHECK (vram_12gb IN (0,1)),
    vram_8gb       INTEGER NOT NULL DEFAULT 0 CHECK (vram_8gb IN (0,1)),
    vram_4gb       INTEGER NOT NULL DEFAULT 0 CHECK (vram_4gb IN (0,1)),
    everything     INTEGER NOT NULL DEFAULT 0 CHECK (everything IN (0,1)),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_model_pipeline ON model(pipeline_tag);
CREATE INDEX idx_model_license  ON model(license);
CREATE INDEX idx_run_model      ON test_run(model_id);
CREATE INDEX idx_note_model     ON model_note(model_id);

-- SQLite has no ON UPDATE; bump updated_at on every UPDATE via triggers.
CREATE TRIGGER trg_model_updated AFTER UPDATE ON model
BEGIN UPDATE model SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_model_tag_updated AFTER UPDATE ON model_tag
BEGIN UPDATE model_tag SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_model_language_updated AFTER UPDATE ON model_language
BEGIN UPDATE model_language SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_model_dataset_updated AFTER UPDATE ON model_dataset
BEGIN UPDATE model_dataset SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_model_base_updated AFTER UPDATE ON model_base
BEGIN UPDATE model_base SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_model_eval_updated AFTER UPDATE ON model_eval
BEGIN UPDATE model_eval SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_model_local_updated AFTER UPDATE ON model_local
BEGIN UPDATE model_local SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_test_run_updated AFTER UPDATE ON test_run
BEGIN UPDATE test_run SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_test_metric_updated AFTER UPDATE ON test_metric
BEGIN UPDATE test_metric SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_model_note_updated AFTER UPDATE ON model_note
BEGIN UPDATE model_note SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
CREATE TRIGGER trg_perfect_for_updated AFTER UPDATE ON perfect_for
BEGIN UPDATE perfect_for SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid; END;
