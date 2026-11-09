"""Bounded source acquisition. Never extracts archives or executes repository code."""

import hashlib
import io
import json
import re
import stat
import time
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlsplit, quote
import httpx

MAX_ARCHIVE = 10 * 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024
MAX_FILE = 512 * 1024
MAX_ENTRIES = 5000
EXCLUDED = {".git", "node_modules", "vendor", ".venv", "venv", "dist", "build", "__pycache__"}


class SourceError(ValueError):
    pass


def repository(value):
    value = value.strip().rstrip("/")
    if not value:
        return "", "", ""
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc not in {"github.com", "gitlab.com"} or parsed.query or parsed.fragment:
        raise SourceError(
            "Use an HTTPS repository URL on github.com or gitlab.com, without credentials. Other servers use ZIP upload."
        )
    path = parsed.path.strip("/").removesuffix(".git")
    parts = path.split("/")
    if (
        len(parts) < 2
        or (parsed.netloc == "github.com" and len(parts) != 2)
        or any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part) or part in {".", ".."} for part in parts)
    ):
        raise SourceError("Enter the repository URL, not a branch or file URL.")
    return f"https://{parsed.netloc}/{path}", parsed.netloc, path


def read_source(data, *, strip_root=False):
    if len(data) > MAX_ARCHIVE:
        raise SourceError("ZIP exceeds the 10 MiB compressed limit.")
    files, skipped, total = {}, {}, 0

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise SourceError("Archive exceeds 5,000 entries; submit a smaller source snapshot.")
            for entry in entries:
                name = entry.filename
                parts = PurePosixPath(name).parts
                if (
                    not parts
                    or name.startswith("/")
                    or "\\" in name
                    or ":" in name
                    or any(p in {".", ".."} for p in parts)
                    or any(ord(c) < 32 for c in name)
                    or len(name) > 500
                ):
                    raise SourceError("Archive contains an unsafe file path.")
                if entry.is_dir():
                    continue
                if stat.S_ISLNK(entry.external_attr >> 16):
                    skip("symlinks")
                    continue
                if entry.flag_bits & 1:
                    raise SourceError("Encrypted ZIP entries are not supported.")
                total += entry.file_size
                if total > MAX_TOTAL:
                    raise SourceError("Archive exceeds the 20 MiB uncompressed limit.")
                if strip_root:
                    parts = parts[1:]
                if not parts:
                    continue
                path = "/".join(parts)
                if any(p in EXCLUDED for p in parts):
                    skip("excluded directories")
                    continue
                if entry.file_size > MAX_FILE:
                    skip("files over 512 KiB")
                    continue
                if path in files:
                    raise SourceError("Archive contains duplicate file paths.")
                raw = archive.read(entry)
                if b"\x00" in raw:
                    skip("binary files")
                    continue
                try:
                    content = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    skip("non-UTF-8 files")
                    continue
                files[path] = content
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
        raise SourceError("Invalid or unsupported ZIP archive.") from exc
    if not files:
        raise SourceError("No supported text files found in the archive.")
    return files, {"text_files": len(files), "skipped": skipped, "uncompressed_bytes": total}


def _download(url, limit=MAX_ARCHIVE):
    # URLs are constructed exclusively from the two fixed provider origins below.
    # No credentials, proxies, redirects, git transports or repository hooks.
    deadline = time.monotonic() + 60
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        with client.stream(
            "GET", url, headers={"User-Agent": "AIDA-AppSec", "Accept": "application/vnd.github+json"}
        ) as response:
            if response.status_code != 200:
                raise SourceError(
                    f"Repository provider returned HTTP {response.status_code}. Check visibility and ref, or upload a ZIP snapshot."
                )
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > limit or time.monotonic() > deadline:
                    raise SourceError("Repository download exceeded its size or time limit.")
            return bytes(content)


def fetch_repository(url, ref):
    _, host, path = repository(url)
    if not host:
        raise SourceError("This project uses ZIP snapshots. Upload an archive to start a scan.")
    encoded_ref = quote(ref, safe="")
    if host == "github.com":
        meta_url = f"https://api.github.com/repos/{path}/commits/{encoded_ref}"
    else:
        meta_url = f"https://gitlab.com/api/v4/projects/{quote(path, safe='')}/repository/commits/{encoded_ref}"
    try:
        metadata = json.loads(_download(meta_url, 2 * 1024 * 1024))
        sha = metadata.get("sha" if host == "github.com" else "id", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise SourceError("Provider did not return a full commit SHA.")
        archive_url = (
            f"https://codeload.github.com/{path}/zip/{sha}"
            if host == "github.com"
            else f"https://gitlab.com/api/v4/projects/{quote(path, safe='')}/repository/archive.zip?sha={sha}&include_lfs_blobs=false"
        )
        data = _download(archive_url)
        return sha, data, hashlib.sha256(data).hexdigest()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise SourceError(
            "Repository provider is unavailable or returned an invalid response. Retry or upload a ZIP snapshot."
        ) from exc
