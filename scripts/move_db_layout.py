"""Move local + mysql/dameng under integrations/db."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "sql_agent" / "integrations"
DB = ROOT / "db"

# Clear stale pycache under db but keep metadata if any
for pyc in DB.rglob("__pycache__"):
    shutil.rmtree(pyc, ignore_errors=True)

# Move local/*.py into db/
local = ROOT / "local"
if local.exists():
    for f in local.iterdir():
        if f.name == "__pycache__":
            continue
        dest = DB / f.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(f), str(dest))
        print(f"moved local/{f.name} -> db/{f.name}")
    shutil.rmtree(local, ignore_errors=True)
    print("removed local/")

# Move mysql/ and dameng/ under db/
for name in ("mysql", "dameng"):
    src = ROOT / name
    if not src.exists():
        print(f"skip missing: {name}")
        continue
    dest = DB / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(src), str(dest))
    print(f"moved {name}/ -> db/{name}/")

# Rewrite imports across sql_agent + main
pkg = ROOT.parent
files = list(pkg.rglob("*.py")) + [pkg.parent.parent / "main.py"]
replacements = [
    ("sql_agent.integrations.local.", "sql_agent.integrations.db."),
    ("from sql_agent.integrations.local import", "from sql_agent.integrations.db import"),
    ("sql_agent.integrations.mysql.", "sql_agent.integrations.db.mysql."),
    ("from sql_agent.integrations.mysql import", "from sql_agent.integrations.db.mysql import"),
    ("sql_agent.integrations.dameng.", "sql_agent.integrations.db.dameng."),
    ("from sql_agent.integrations.dameng import", "from sql_agent.integrations.db.dameng import"),
]

for py in files:
    if not py.exists() or "__pycache__" in str(py):
        continue
    text = py.read_text(encoding="utf-8")
    new = text
    for old, rep in replacements:
        new = new.replace(old, rep)
    if new != text:
        py.write_text(new, encoding="utf-8")
        print(f"updated: {py}")

print("done")
