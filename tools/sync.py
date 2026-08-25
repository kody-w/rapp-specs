#!/usr/bin/env python3
"""Sync the canonical spec texts into specs/ — the specs brain's raw material.

Each spec's home repo stays canonical; this brain mirrors the text so ONE clone holds
every spec, verified and versioned. Run sync, then brainify: changed specs mint new
frames; unchanged specs cost nothing.
"""
import urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANON = {
  "rapp-1.md":       "https://raw.githubusercontent.com/kody-w/rapp-1/main/SPEC.md",
  "dogg-0.md":       "https://raw.githubusercontent.com/kody-w/dogg/main/PROTOCOL.md",
  "rapp-brain-0.md": "https://raw.githubusercontent.com/kody-w/rapp-brain/main/SPEC.md",
  "cast-0.md":       "https://raw.githubusercontent.com/kody-w/doggcast/main/SPEC.md",
  "dogg-skill.md":   "https://raw.githubusercontent.com/kody-w/dogg/main/SKILL.md",
}
for name, url in CANON.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rapp-specs-sync"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode()
        p = ROOT / "specs" / name
        if not p.exists() or p.read_text() != body:
            p.write_text(body)
            print(f"updated: {name}")
        else:
            print(f"current: {name}")
    except Exception as ex:
        print(f"FAILED (kept last copy): {name} — {str(ex)[:60]}")
