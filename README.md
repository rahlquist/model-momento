# model-momento

SQLite-backed database of model info: HF metadata, benchmark runs, notes.

Includes an installable Hermes skill (`model-momento/SKILL.md`) — say
"memento <huggingface-url>" to a Hermes agent with this skill and it will
import the model and open the notes UI.

## Install the skill

```bash
hermes skills install https://raw.githubusercontent.com/rahlquist/model-momento/main/model-momento/SKILL.md --yes
```

## Server setup

```bash
git clone https://github.com/rahlquist/model-momento
cd model-momento
python3 -m venv .venv
.venv/bin/pip install fastapi 'uvicorn[standard]'
.venv/bin/python -c "import sqlite3; c=sqlite3.connect('model_momento.db'); c.executescript(open('schema.sql').read())"
.venv/bin/python server.py        # http://127.0.0.1:8765
```

Then open http://127.0.0.1:8765 — search, import from HF, create/edit
records, enter notes and benchmark runs.
