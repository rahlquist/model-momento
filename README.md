# model-momento

SQLite-backed database of model info: HF metadata, benchmark runs, notes.

Includes an installable Hermes skill (`model-momento/SKILL.md`) — say
"memento <huggingface-url>" to a Hermes agent with this skill and it will
import the model and open the notes UI.

## Install the skill

```bash
hermes skills install https://raw.githubusercontent.com/rahlquist/model-momento/main/model-momento/SKILL.md --yes
```

### If the install is blocked

The `hermes skills install` scanner (`skills-guard-v1`) can hard-block installs
on false positives — it pattern-matches things like `subprocess`, `os.environ`,
`base64`, or `curl | python`, and `--force` does **not** override a block. A
block is not proof the skill is malicious; this skill is pure prose (markdown
with example curl commands) and contains no executable code.

Workaround — install manually as a local skill:

```bash
git clone https://github.com/rahlquist/model-momento /tmp/mm-skill
mkdir -p ~/.hermes/skills/model-momento
cp /tmp/mm-skill/model-momento/SKILL.md ~/.hermes/skills/model-momento/SKILL.md
rm -rf /tmp/mm-skill
```

The directory name must equal the skill's `name` frontmatter
(`model-momento`) — the loader picks it up as a local enabled skill on the
next session. Verify with `hermes skills list` or by asking the agent to run
`skills_list`.


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
