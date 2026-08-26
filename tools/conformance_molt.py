#!/usr/bin/env python3
"""conformance_molt.py — rapp-molt/0 conformance. Every claim in the spec, executed.

The two that matter most:
  C1  two independent hosts reach the SAME floor key with zero coordination, while their
      identities stay distinct — the property the predecessor bought with a name-hash,
      obtained here without one.
  C10 every chain this profile writes verifies under PLAIN rapp.py with no molt code in
      the loop — the proof that a molt is a frame and this document is deletable.
"""
from __future__ import annotations
import json, shutil, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import molt, rapp as R

FERTILE = b"class Agent:\n    def __init__(self, name=None, metadata=None):\n        self.name = name\n"
ADAPTED = b"class Agent:\n    def __init__(self, name=None, metadata=None):\n        self.name = name\n        self.v = 2\n"
STERILE = b"AGENT = {'name': 'x'}\n"          # loads fine, can never parent a generation
BROKEN  = b"class Agent:\n  def __init__(\n"  # unparseable

P, F, results = 0, 0, []
def check(name, cond, detail=""):
    global P, F
    ok = bool(cond); P, F = P + ok, F + (not ok)
    results.append(("PASS" if ok else "FAIL", name, detail))
    return ok

tmp = Path(tempfile.mkdtemp(prefix="molt-conf-"))
try:
    # C1 · floor key shared, identity distinct (§3)
    a, b = tmp / "a.jsonl", tmp / "b.jsonl"
    ga, gb = molt.genesis(a, "planner", FERTILE), molt.genesis(b, "planner", FERTILE)
    check("C1a floor key identical across independent hosts (particle)",
          molt.floor_key(a) == molt.floor_key(b), molt.floor_key(a)[:16])
    check("C1b identity distinct across those same hosts (wave)",
          ga["frame_hash"] != gb["frame_hash"])
    ida = json.loads(Path(str(a) + ".rappid.json").read_text())
    idb = json.loads(Path(str(b) + ".rappid.json").read_text())
    check("C1c identity is uuid-minted, never a name-hash (§6.2)",
          R.rappid_valid(ida["rappid"]) and ida["rappid"] != idb["rappid"])
    check("C1e the genesis payload carries NO per-host field (§5.1)",
          set(ga["payload"]) == {"locus", "source_sha256", "contract", "molt"})
    c = tmp / "c.jsonl"; molt.genesis(c, "planner", ADAPTED)
    check("C1d a different baseline is a DIFFERENT lineage (§8 I1)",
          molt.floor_key(c) != molt.floor_key(a))

    # C2 · the floor is never re-minted
    try:
        molt.genesis(a, "planner", FERTILE); check("C2 genesis re-mint refused", False)
    except ValueError:
        check("C2 genesis re-mint refused (§5.1)", True)

    # C3 · recording grants nothing
    r1 = molt.ring(a, ADAPTED, "add version marker")
    check("C3a recording a ring is always permitted (§5.2)", r1["seq"] == 1)
    check("C3b recording does NOT activate", molt.resolve(a)["at_floor"] is True)

    # C4 · activation without a verdict is refused (V5)
    va = tmp / "verdict.jsonl"
    try:
        molt.activate(a, va, 1); check("C4 activation without verdict refused", False)
    except ValueError as e:
        check("C4 activation without verdict refused (V5 fail closed)", True, str(e)[:60])

    # C5 · a host cannot issue its own verdict (V1) — structural, not policy
    host_stream = molt._stream_of(a)
    forged = tmp / "forged.jsonl"
    molt._append(forged, "molt.verdict", host_stream,
                 {"ring": r1["frame_hash"], "verdict": "pass", "checks": {}, "gate": "self"})
    try:
        molt.activate(a, forged, 1); check("C5 self-issued verdict refused", False)
    except ValueError as e:
        check("C5 self-issued verdict refused (V1 structural)", True, str(e)[:60])

    # C6 · a real gate passes a fertile ring, and activation then succeeds
    v = molt.judge(va, a, 1, ADAPTED)
    check("C6a gate passes a fertile, matching ring", v["payload"]["verdict"] == "pass",
          v["payload"]["detail"][:60])
    act = molt.activate(a, va, 1)
    check("C6b activation succeeds with a foreign passing verdict", act["kind"] == "molt.activated")
    check("C6c resolve reports the live ring, no longer at floor",
          molt.resolve(a)["live"] == r1["frame_hash"] and not molt.resolve(a)["at_floor"])

    # C7 · fertility (V3): a ring that LOADS but can never parent again is refused
    d = tmp / "d.jsonl"; molt.genesis(d, "planner", FERTILE)
    rs = molt.ring(d, STERILE, "flatten to a dict")
    vd = tmp / "vd.jsonl"
    vs = molt.judge(vd, d, 1, STERILE)
    check("C7a gate FAILS a sterile ring (V3)", vs["payload"]["verdict"] == "fail",
          vs["payload"]["checks"].get("fertility"))
    try:
        molt.activate(d, vd, 1); check("C7b sterile ring cannot be activated", False)
    except ValueError:
        check("C7b sterile ring cannot be activated", True)

    # C8 · judging different bytes than were recorded is caught
    v2 = molt.judge(vd, d, 1, FERTILE)
    check("C8 gate refuses when source != recorded ring", v2["payload"]["checks"]["content"] == "fail")

    # C9 · policy: pinned refuses activation and resolves to the floor (§5.6)
    e = tmp / "e.jsonl"; molt.genesis(e, "compliance", FERTILE)
    re_ = molt.ring(e, ADAPTED, "adapt"); ve = tmp / "ve.jsonl"; molt.judge(ve, e, 1, ADAPTED)
    molt.set_policy(e, "pinned")
    try:
        molt.activate(e, ve, 1); check("C9a pinned locus refuses activation", False)
    except ValueError:
        check("C9a pinned locus refuses activation (§5.6)", True)
    check("C9b pinned locus resolves to the floor", molt.resolve(e)["at_floor"] is True)

    # C10 · a molt chain is a FRAME chain — verified with no molt code in the loop
    plain_ok, seen = True, 0
    for path in (a, d, e, va, vd):
        head = None
        for line in path.read_text().splitlines():
            if not line.strip(): continue
            fr = json.loads(line); seen += 1
            ok, step, why = R.verify_frame(fr, head=head, stream_id_of_record=fr["stream_id"])
            if not ok: plain_ok = False
            head = fr
    check("C10 every molt frame verifies under PLAIN rapp/1 (no molt code)", plain_ok,
          f"{seen} frames")

    # C11 · R2 composition must not fail: a corrupted chain degrades to the floor
    bad = tmp / "bad.jsonl"; shutil.copy(a, bad)
    lines = bad.read_text().splitlines(); lines[1] = json.dumps({**json.loads(lines[1]), "seq": 99})
    bad.write_text("\n".join(lines) + "\n")
    res = molt.resolve(bad)
    check("C11 a broken chain degrades to the floor, never raises (R2)",
          res["at_floor"] and res.get("degraded"), res["why"][:60])

    # C12 · reversal is an append, and re-activation stays available (B2)
    before = len(molt.load(a))
    molt.revert(a, "regression in the field")
    check("C12a reversal returns to the floor", molt.resolve(a)["at_floor"] is True)
    check("C12b reversal is non-destructive (append-only)", len(molt.load(a)) == before + 1)
    molt.activate(a, va, 1)
    check("C12c a reverted ring can be re-activated (B2)", not molt.resolve(a)["at_floor"])

    # C13 · V5: unreadable is never pass
    vb = tmp / "vb.jsonl"; f = tmp / "f.jsonl"; molt.genesis(f, "x", FERTILE)
    molt.ring(f, BROKEN, "typo")
    vbad = molt.judge(vb, f, 1, BROKEN)
    check("C13 unparseable source is FAIL, never silence (V5)",
          vbad["payload"]["verdict"] == "fail")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

for status, name, detail in results:
    print(f"  {'✅' if status == 'PASS' else '❌'} {name}" + (f"  — {detail}" if detail else ""))
print(f"\nrapp-molt/0 conformance: {P}/{P + F}")
sys.exit(1 if F else 0)
