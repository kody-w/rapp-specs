#!/usr/bin/env python3
"""The estate layer of the specs brain: census + canon + the update queue.

Live repo listing from the GitHub API (the freshness truth) joined with rapp-map's
crawled estate-map.json (the depth truth: canonical files and their carriers). The
output is three markdown pages under estate/ — and the point of the whole exercise is
UPDATE-QUEUE.md: consult the brain, know exactly what needs updating today.
"""
import json, subprocess, pathlib, datetime, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
EST = ROOT / "estate"
MAP_URL = "https://raw.githubusercontent.com/kody-w/rapp-map/main/estate-map.json"

def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

def gh_list(owner):
    r = subprocess.run(["gh", "repo", "list", owner, "--limit", "1000",
                        "--visibility", "public",
                        "--json", "name,pushedAt,description,isArchived,isTemplate"],
                       capture_output=True, text=True, timeout=180)
    return json.loads(r.stdout) if r.returncode == 0 else []

def family(name):
    n = name.lower()
    for key, fam in [("dogg", "dogg network"), ("rapp-brain", "brains"),
                     ("rapp-specs", "brains"), ("rboxhub", "templates"),
                     ("rapp-fps", "games"), ("rapp-", "rapp core"),
                     ("brainstem", "brainstem"), ("rappter", "rappter"),
                     ("rar", "registry"), ("rapterbox", "rapterbox")]:
        if key in n:
            return fam
    return "other"

def main():
    EST.mkdir(exist_ok=True)
    kw = gh_list("kody-w")
    rb = gh_list("rbox-rappters-2026")
    live = [dict(r, owner="kody-w") for r in kw] + [dict(r, owner="rbox-rappters-2026") for r in rb]
    with urllib.request.urlopen(urllib.request.Request(MAP_URL,
            headers={"User-Agent": "rapp-specs-estate"}), timeout=30) as r:
        emap = json.loads(r.read().decode())
    mapped = {m["repo"] for m in emap["members"]}

    # census
    fams = {}
    for r in live:
        if r["isArchived"]:
            continue
        fams.setdefault(family(r["name"]), []).append(r)
    lines = [f"# Estate census — {utc()}",
             f"\n{len(live)} public repos ({sum(1 for r in live if r['isArchived'])} archived) "
             f"across kody-w + rbox-rappters-2026. Map ({emap['built_at'][:10]}) knows "
             f"{len(emap['members'])} members.\n"]
    for fam in sorted(fams, key=lambda f: -len(fams[f])):
        rs = sorted(fams[fam], key=lambda r: r["pushedAt"], reverse=True)
        lines.append(f"\n## {fam} ({len(rs)})")
        for r in rs[:200]:
            lines.append(f"- `{r['owner']}/{r['name']}` · pushed {r['pushedAt'][:10]}"
                         + (" · template" if r["isTemplate"] else ""))
    (EST / "census.md").write_text("\n".join(lines) + "\n")

    # canon
    carriers = [m for m in emap["members"] if m.get("canon")]
    by_file = {}
    for m in carriers:
        for f, sha in m["canon"].items():
            by_file.setdefault(f, []).append((m["repo"], sha))
    lines = [f"# Canonical files across the estate — {utc()}",
             f"\n{len(by_file)} canonical file(s) carried by {len(carriers)} repo(s) "
             f"(source: rapp-map estate-map.json, built {emap['built_at'][:10]}).\n"]
    for f in sorted(by_file):
        rows = by_file[f]
        shas = {s for _, s in rows}
        mark = "ONE sha (aligned)" if len(shas) == 1 else f"{len(shas)} DIFFERENT shas — DRIFT"
        lines.append(f"\n## `{f}` — {len(rows)} carrier(s), {mark}")
        for repo, sha in sorted(rows):
            lines.append(f"- `{repo}` @ {sha[:12]}")
    (EST / "canon.md").write_text("\n".join(lines) + "\n")

    # THE UPDATE QUEUE — consult this page, know what to update
    unmapped = sorted(f"{r['owner']}/{r['name']}" for r in live
                      if not r["isArchived"] and f"{r['owner']}/{r['name']}" not in mapped
                      and r["owner"] == "kody-w")
    drifted = sorted(f for f, rows in by_file.items() if len({s for _, s in rows}) > 1)
    lines = [f"# UPDATE QUEUE — {utc()}",
             "\nConsult this page; it says exactly what needs updating today.\n",
             f"\n## 1 · Repos the map has never crawled ({len(unmapped)})",
             "The map's next crawl (rapp-map spine tooling) must cover these:"]
    lines += [f"- `{r}`" for r in unmapped]
    lines += [f"\n## 2 · Canonical files with drifted mirrors ({len(drifted)})",
              "Carriers disagree — reconcile these mirrors to their canon:"]
    lines += [f"- `{f}` (see canon.md for carriers)" for f in drifted] or ["- none — aligned"]
    lines += ["\n## 3 · Spec texts changed in the last sync",
              "(see the sync commit for which specs/ files moved — their consumers refresh)"]
    (EST / "UPDATE-QUEUE.md").write_text("\n".join(lines) + "\n")
    print(f"estate: census {sum(len(v) for v in fams.values())} live · "
          f"canon {len(by_file)} files/{len(carriers)} carriers · "
          f"queue: {len(unmapped)} unmapped, {len(drifted)} drifted")

if __name__ == "__main__":
    main()
