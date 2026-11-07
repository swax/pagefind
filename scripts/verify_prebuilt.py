"""Verify the prebuilt resources; no asset-generation toolchain is required."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'PREBUILT-SHA256.json').read_text(encoding='utf-8'))
assets = root / 'pagefind' / 'vendor'
actual = {p.relative_to(root).as_posix() for p in assets.rglob('*') if p.is_file()}
assert actual == set(manifest['files']), 'Prebuilt asset inventory differs'
for name, expected in manifest['files'].items():
    path = root / name
    assert not path.is_symlink() and path.resolve().is_relative_to(assets.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
print(f"Verified {len(actual)} original Pagefind {manifest['pagefind_version']} assets.")
