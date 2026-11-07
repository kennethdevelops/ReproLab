"""Operator CLI: export committed files of a repository subdirectory as a local snapshot.

    python -m reprolab.indexing.local_snapshot export --repo .. --subdir demo-target \
        --name demo-target --out data/snapshots

Reads blobs with ``git show <sha>:<path>`` (committed content only; the working tree, untracked
files and uncommitted edits are never exported). Paths are filtered by ``indexing.paths`` before
writing, so answer keys (``fixtures/``, ``benchmarks/ground-truth``) never reach the snapshot.
Nothing from the repository is executed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from reprolab.indexing.paths import refusal_reason
from reprolab.indexing.sources import MANIFEST, NAME_RE, SHA_RE


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(  # noqa: S603 - fixed git argv, operator-only tool
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
    ).stdout


def export_snapshot(
    repo: Path, subdir: str, name: str, out_dir: Path, ref: str = "HEAD", max_bytes: int = 200_000
) -> tuple[str, list[str], dict[str, int]]:
    if not NAME_RE.match(name):
        raise ValueError("invalid snapshot name")
    sha = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    if not SHA_RE.match(sha):
        raise ValueError(f"could not resolve {ref} to a commit")
    prefix = subdir.strip("/") + "/"
    listing = _git(repo, "ls-tree", "-r", "-l", "-z", sha, "--", prefix).decode()
    target = out_dir / name / sha
    files_dir = target / "files"
    written: list[str] = []
    excluded: dict[str, int] = {}
    for entry in filter(None, listing.split("\0")):
        meta, path = entry.split("\t", 1)
        mode, kind, _obj, size = meta.split()
        rel = path[len(prefix) :]
        reason = "not_a_file" if kind != "blob" or mode == "120000" else None
        reason = reason or refusal_reason(rel, int(size), max_bytes)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        dest = files_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_git(repo, "show", f"{sha}:{path}"))
        written.append(rel)
    manifest = {"commit_sha": sha, "ref": ref, "subdir": subdir, "files": sorted(written),
                "excluded": excluded}  # fmt: skip
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / name / "CURRENT").write_text(sha, encoding="utf-8")
    return sha, written, excluded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--repo", type=Path, default=Path(".."))
    exp.add_argument("--subdir", default="demo-target")
    exp.add_argument("--name", default="demo-target")
    exp.add_argument("--out", type=Path, default=Path("data/snapshots"))
    exp.add_argument("--ref", default="HEAD")
    args = parser.parse_args()
    sha, written, excluded = export_snapshot(args.repo, args.subdir, args.name, args.out, args.ref)
    print(f"exported {len(written)} files at {sha} (excluded: {excluded})")


if __name__ == "__main__":
    main()
