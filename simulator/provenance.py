"""Portable Git-text hashes plus exact captured bytes; host-only helper."""
import hashlib
from pathlib import Path

NORMALIZATION = "UTF-8 source bytes with CRLF normalized to LF"


def source_hashes(folder):
    canonical, raw = {}, {}
    for path in sorted(Path(folder).glob("*.py")):
        data = path.read_bytes()
        raw[path.name] = hashlib.sha256(data).hexdigest()
        canonical[path.name] = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    return canonical, raw
