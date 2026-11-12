"""Validate the app, its actual source archive, and optionally its store listing.

Python3.11+ uses only its standard library. Python3.10 can install tomli.
This tool performs no publication or PBX/hardware actions.
"""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {"Badge", "Music", "Media", "Apps", "Games", "Background", "Pattern"}
MAX_RUNTIME_BYTES = 100_000
MAX_DOWNLOAD_BYTES = 2_000_000
STORE = "https://apps.badge.emfcamp.org"


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip()) and not any(ord(c) < 32 for c in value)


def validate_data(data):
    require(isinstance(data, dict), "Manifest must be an object")
    app, metadata = data.get("app"), data.get("metadata")
    require(isinstance(app, dict) and isinstance(metadata, dict), "Manifest needs app and metadata objects")
    require(set(app) == {"name", "category"}, "Only app.name and app.category survive the current registry schema")
    require(text(app.get("name")), "App name is missing or invalid")
    categories = app.get("category")
    categories = categories if isinstance(categories, list) else [categories]
    require(bool(categories) and all(isinstance(v, str) and v in CATEGORIES for v in categories), "Unknown or missing category")
    for key in ("author", "license", "url", "description", "version"):
        require(text(metadata.get(key)), "Missing or invalid metadata." + key)
    require(len(metadata["author"]) <= 32, "Keep author within the published32-character guidance")
    require(len(metadata["description"]) <= 140, "Keep description within the published140-character guidance")
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", metadata["version"])), "Use a semantic version string")
    url = urlsplit(metadata["url"])
    parts = url.path.strip("/").split("/")
    require(url.scheme == "https" and url.hostname == "github.com" and len(parts) == 2
            and all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts)
            and not url.query and not url.fragment and not url.username and not url.port,
            "Source URL must identify the actual HTTPS GitHub owner/repository")
    for association in metadata.get("capabilities", []):
        require(isinstance(association, dict) and isinstance(association.get("required"), bool)
                and isinstance(association.get("feature"), dict), "Invalid capability association")
        feature = association["feature"]
        kind = feature.get("type")
        valid = kind in ("2024 Frontboard", "2026 Frontboard")
        valid = valid or kind == "Capability" and text(feature.get("identifier"))
        valid = valid or kind == "TildagonOSMinimumVersion" and text(feature.get("version"))
        valid = valid or text(feature.get("vid")) and text(feature.get("pid"))
        require(valid, "Unsupported capability feature")
    return {"owner": parts[0], "repository": parts[1], "name": app["name"],
            "version": metadata["version"], "categories": categories}


def load_manifest(root):
    choices = [p for p in (root / "tildagon.toml", root / "tildagon.json") if p.is_file()]
    require(len(choices) == 1, "Keep exactly one root tildagon.toml OR tildagon.json")
    path = choices[0]
    if path.suffix == ".toml":
        require(tomllib is not None, "Use Python3.11+ or install tomli to parse TOML")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    return path.name, data, validate_data(data)


def runtime_files(root, manifest):
    files = {p.name: p for p in root.glob("*.py")}
    for name in ("app.py", "__init__.py", "LICENSE"):
        require((root / name).is_file(), "Missing runtime/package file: " + name)
    files.update({manifest: root / manifest, "LICENSE": root / "LICENSE"})
    require(all(not p.is_symlink() for p in files.values()), "Runtime files must not be symbolic links")
    total = sum(p.stat().st_size for p in files.values())
    require(total <= MAX_RUNTIME_BYTES, "Runtime payload exceeds100000bytes")
    exported = None
    for name, path in files.items():
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=name)
        if name == "app.py":
            classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__app_export__" for t in node.targets):
                    if isinstance(node.value, ast.Name) and node.value.id in classes:
                        exported = node.value.id
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                require(node.level == 1, "Runtime relative import escapes its package: " + name)
                modules = [node.module.split(".")[0]] if node.module else [a.name for a in node.names]
                for module in modules:
                    require(module + ".py" in files, "Missing relative runtime module: " + module)
    require(exported == "EventHorizon", "app.py must define and export the EventHorizon class")
    return files, total


def app_code(owner, repository):
    digest = hashlib.md5(("github" + owner + repository).encode("utf-8")).digest()
    return "".join(str(value % 5) for value in digest[:8])


def validate_archive(content, files):
    require(len(content) <= MAX_DOWNLOAD_BYTES, "Compressed archive exceeds2MB; media may have leaked into the badge package")
    found, roots, payload, entries = {}, set(), 0, 0
    with tarfile.open(fileobj=io.BytesIO(content), mode="r|gz") as archive:
        for member in archive:
            entries += 1
            require(entries <= 100, "Too many archive entries")
            path = PurePosixPath(member.name)
            require(not path.is_absolute() and ".." not in path.parts and bool(path.parts), "Unsafe archive path")
            roots.add(path.parts[0])
            require(len(roots) == 1, "Archive needs one top-level package directory")
            if member.isdir():
                require(len(path.parts) == 1, "Archive contains a non-runtime directory")
                continue
            require(member.isfile() and len(path.parts) == 2, "Archive contains a link, special file or non-flat runtime path")
            name = path.parts[1]
            require(name in files and name not in found, "Unexpected or duplicate archived file: " + name)
            require(0 <= member.size <= MAX_RUNTIME_BYTES, "Oversized archived runtime file")
            payload += member.size
            require(payload <= MAX_RUNTIME_BYTES, "Archived payload exceeds100000bytes")
            data = archive.extractfile(member).read(member.size + 1)
            require(len(data) == member.size, "Truncated archived file")
            expected = files[name].read_bytes()
            require(data.replace(b"\r\n", b"\n") == expected.replace(b"\r\n", b"\n"), "Archive differs from current source: " + name)
            found[name] = hashlib.sha256(data).hexdigest()
    require(set(found) == set(files), "Archive is missing runtime files: " + ", ".join(sorted(set(files) - set(found))))
    return {"compressed_bytes": len(content), "runtime_bytes": payload, "files": sorted(found), "sha256": found}


def fetch(url, limit):
    parsed = urlsplit(url)
    require(parsed.scheme == "https" and parsed.hostname == "apps.badge.emfcamp.org"
            and not parsed.username and not parsed.port, "Store fetch must use the official HTTPS origin")
    request = Request(url, headers={"User-Agent": "EventHorizonValidator/1.0", "Accept": "application/json, application/gzip"})
    try:
        with urlopen(request, timeout=20) as response:
            require(urlsplit(response.url).scheme == "https", "Store redirected away from HTTPS")
            data = response.read(limit + 1)
    except HTTPError as error:
        raise ValidationError("Store HTTP " + str(error.code) + "; listing may still be refreshing") from None
    except (URLError, TimeoutError, OSError):
        raise ValidationError("Store request failed") from None
    require(len(data) <= limit, "Store response exceeds the bounded download limit")
    return data


def check_store(info, files, expected_commit=None):
    code = app_code(info["owner"], info["repository"])
    record = json.loads(fetch(STORE + "/v1/apps/" + code, 65536))
    identity = record.get("id", {})
    require(record.get("code") == code and identity.get("service") == "github"
            and identity.get("owner") == info["owner"] and identity.get("title") == info["repository"],
            "Store code resolves to a different repository")
    manifest = validate_data(record.get("manifest"))
    require(manifest["version"] == info["version"] and manifest["name"] == info["name"], "Store version/name differs from this release")
    require(expected_commit is None or identity.get("releaseHash") == expected_commit, "Store is serving a different commit")
    archive = validate_archive(fetch(record.get("tarballUrl", ""), MAX_DOWNLOAD_BYTES), files)
    return {"code": code, "url": STORE + "/apps/" + code + "/", "release_commit": identity.get("releaseHash"), "archive": archive}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    archive = parser.add_mutually_exclusive_group()
    archive.add_argument("--archive", type=Path)
    archive.add_argument("--git-ref", help="Validate the actual git archive for a commit/tag")
    parser.add_argument("--write-archive", type=Path, help="Save the validated --git-ref archive")
    parser.add_argument("--check-store", action="store_true", help="Read the official listing and validate its cached download")
    parser.add_argument("--expected-commit")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        name, data, info = load_manifest(root)
        files, total = runtime_files(root, name)
        result = dict(info, code=app_code(info["owner"], info["repository"]), runtime_bytes=total)
        if args.git_ref:
            require(bool(re.fullmatch(r"[A-Za-z0-9_./-]+", args.git_ref)) and not args.git_ref.startswith("-"), "Invalid Git ref")
            command = ["git", "-C", str(root), "archive", "--format=tar.gz", "--prefix=event-horizon/", args.git_ref]
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            require(completed.returncode == 0, "git archive failed; commit the complete package first")
            content = completed.stdout
            result["archive"] = validate_archive(content, files)
            if args.write_archive:
                args.write_archive.parent.mkdir(parents=True, exist_ok=True)
                args.write_archive.write_bytes(content)
        elif args.archive:
            require(args.archive.stat().st_size <= MAX_DOWNLOAD_BYTES, "Archive exceeds the2MB download bound")
            result["archive"] = validate_archive(args.archive.read_bytes(), files)
        else:
            require(args.write_archive is None, "--write-archive needs --git-ref")
        if args.check_store:
            result["store"] = check_store(info, files, args.expected_commit)
        print(json.dumps(result, indent=2))
        return 0
    except (ValidationError, OSError, SyntaxError, ValueError, TypeError, KeyError, tarfile.TarError) as error:
        print("Publication validation failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
