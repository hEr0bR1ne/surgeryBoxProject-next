"""Parse tracked Python sources and reject embedded provider credentials."""
import ast
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
paths = subprocess.check_output(
    ["git", "ls-files", "-z", "--", "*.py"], cwd=root
).decode().split("\0")
count = 0
for name in filter(None, paths):
    text = (root / name).read_text(encoding="utf-8-sig")
    ast.parse(text, filename=name)
    if re.search(r"sk-[A-Za-z0-9_-]{20,}", text):
        raise SystemExit(f"Embedded credential-like value in {name}; value withheld")
    count += 1
print(f"Parsed {count} tracked Python files; no embedded provider-key pattern found.")
