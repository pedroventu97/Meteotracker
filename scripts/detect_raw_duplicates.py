"""Detects duplicate/redundant raw sessions under data/raw/ by content hash.

Two hashes per file:
  - file_sha256: exact byte-identical detection.
  - core_content_hash: sha256 over the file's own (Time, Lat, Lon) rows only
    (rounded to 6 decimal places), so a full export and a reduced-column
    re-export of the *same* trip still hash identically even though their
    column sets differ (this is how the original campaign_manifest.csv's 5
    known redundant files were distinguished: 1 byte-identical pair, 4
    reduced-column re-exports sharing the same GPS/time trace).

Read-only: never modifies data/raw/. Prints groups of files sharing a
core_content_hash (byte-identical subgroups are called out separately) so a
human can decide which is canonical before hand-editing the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def core_content_hash(path: Path) -> tuple[str, int, int]:
    df = pd.read_csv(path, usecols=lambda c: c in ("Time", "Lat", "Lon"), encoding="utf-8-sig")
    n_cols_total = len(pd.read_csv(path, nrows=0).columns)
    core = df[["Time", "Lat", "Lon"]].copy()
    core["Lat"] = pd.to_numeric(core["Lat"], errors="coerce").round(6)
    core["Lon"] = pd.to_numeric(core["Lon"], errors="coerce").round(6)
    core["Time"] = core["Time"].astype(str).str.strip()
    text = "\n".join(f"{t}|{la}|{lo}" for t, la, lo in core.itertuples(index=False))
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), n_cols_total, len(core)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Detect duplicate/redundant raw MeteoTracker sessions")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--only", nargs="*", default=None, help="Restrict to these date subdirectories (e.g. 7-22 7-30)")
    args = parser.parse_args(argv)

    raw_dir = REPO_ROOT / args.raw_dir
    files = [
        p for p in sorted(raw_dir.rglob("*.csv"))
        if "original_delivery" not in p.parts and (args.only is None or p.parent.name in args.only)
    ]
    print(f"Scanning {len(files)} raw CSV files under {raw_dir}" + (f" (restricted to {args.only})" if args.only else ""))

    rows = []
    for p in files:
        sha = file_sha256(p)
        core_hash, n_cols, n_rows = core_content_hash(p)
        rel = p.relative_to(raw_dir).as_posix()
        rows.append({"source_file": rel, "file_sha256": sha, "core_content_hash": core_hash, "n_cols": n_cols, "n_rows": n_rows})

    df = pd.DataFrame(rows)

    print("\n=== Byte-identical groups (file_sha256) ===")
    for h, g in df.groupby("file_sha256"):
        if len(g) > 1:
            print(f"  {h[:12]}...: {list(g['source_file'])}")

    print("\n=== Same-trip groups (core_content_hash: same Time/Lat/Lon trace) ===")
    any_group = False
    for h, g in df.groupby("core_content_hash"):
        if len(g) > 1:
            any_group = True
            print(f"  {h[:12]}...:")
            for _, r in g.iterrows():
                print(f"    {r['source_file']}  (n_cols={r['n_cols']}, n_rows={r['n_rows']})")
    if not any_group:
        print("  (none found)")

    return df


if __name__ == "__main__":
    main()
