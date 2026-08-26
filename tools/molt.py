#!/usr/bin/env python3
"""molt.py — reference implementation of rapp-molt/0 (specs/rapp-molt-0.md).

A molt IS a frame. This file adds no envelope, no hash, and no second verifier — it is
rules over ordinary rapp/1 chains, and every chain it writes verifies with plain rapp.py.

The one structural idea worth reading the code for: **a host cannot forge a verdict on
itself.** Verdicts live in the verifier's stream, so a host appending its own `pass` is
not a policy violation to be caught by a hook — it is an invalid frame that rapp/1
refuses. `activate()` below therefore has nothing to trust and nothing to enforce; it
just checks the arithmetic.

  python3 molt.py genesis <chain> <locus> <file>     mint the floor (ring 0)
  python3 molt.py ring    <chain> <file> [rationale] record a generation (grants nothing)
  python3 molt.py judge   <vchain> <chain> <ring#>   the GATE: V2/V3/V4, writes a verdict
  python3 molt.py activate <chain> <vchain> <ring#>  refuses without a foreign pass verdict
  python3 molt.py pin     <chain> | unpin <chain>
  python3 molt.py resolve <chain>                    what should be running, fail-closed
  python3 molt.py floor   <chain>                    the world-wide baseline key
"""
from __future__ import annotations

import ast
import datetime
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rapp as R

SPEC = "rapp-molt/0"


def _utc() -> str:
    n = datetime.datetime.now(datetime.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def load(path: Path, stream: str | None = None) -> list[dict]:
    """Read and verify a chain end to end. V5: a broken chain raises — never pretend."""
    p = Path(path)
    if not p.exists():
        return []
    frames = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    head = None
    for f in frames:
        sid = stream or f.get("stream_id")
        ok, step, why = R.verify_frame(f, head=head, stream_id_of_record=sid)
        if not ok:
            raise ValueError(f"molt chain BROKEN at seq {f.get('seq')}: {step}: {why}")
        head = f
    return frames


def _append(path: Path, kind: str, stream: str, payload: dict) -> dict:
    frames = load(path, stream)
    head = frames[-1] if frames else None
    f = R.build_frame(kind, stream, (head["seq"] + 1) if head else 0, _utc(), payload,
                      prev=(head["payload_hash"] if head else None))
    ok, step, why = R.verify_frame(f, head=head, stream_id_of_record=stream)
    if not ok:
        raise ValueError(f"refusing invalid frame: {step}: {why}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(f) + "\n")
    return f


def _stream_of(path: Path) -> str:
    frames = load(path)
    if not frames:
        raise ValueError(f"{path}: no genesis — mint the floor first")
    return frames[0]["stream_id"]


# ---------- §5.1 the floor ----------
def genesis(path: Path, locus: str, source: bytes, owner: str = "kody-w",
            contract: str = "rapp/agent") -> dict:
    """Mint ring 0. The payload carries ONLY reproducible fields, so two hosts building
    genesis from byte-identical baseline source get the same payload_hash with zero
    coordination — that shared value is the floor key (§3). Identity is separate: the
    minted rappid rides in stream_id, which only frame_hash covers. Equivalence on the
    particle, identity on the wave; nothing is given up by refusing a name-hash."""
    if load(path):
        raise ValueError("genesis already minted — a floor is never re-minted (§5.1)")
    rappid = R.mint_rappid(owner, locus)            # §6.2 uuid entropy, NEVER name-hash
    stream = f"molt:@{owner}/{rappid.rsplit(':', 1)[1][:12]}"
    # The rappid must NOT enter the payload: it is random per host, so including it would
    # make every host's genesis payload_hash unique and destroy the shared floor key that
    # is the entire point of §3. It rides in stream_id (covered by frame_hash) and is
    # recorded in a sidecar, exactly as the rest of the estate carries rappid.json.
    f = _append(path, "molt.genesis", stream, {
        "locus": locus, "source_sha256": hashlib.sha256(source).hexdigest(),
        "contract": contract, "molt": SPEC})
    Path(str(path) + ".rappid.json").write_text(json.dumps(
        {"rappid": rappid, "kind": "molt.locus", "locus": locus,
         "stream_id": stream, "floor_key": f["payload_hash"]}, indent=2) + "\n")
    return f


def floor_key(path: Path) -> str:
    """The world-wide 'same agent, same baseline' key: genesis payload_hash (§3)."""
    frames = load(path)
    if not frames:
        raise ValueError("no genesis")
    return frames[0]["payload_hash"]


# ---------- §5.2 recording is free ----------
def ring(path: Path, source: bytes, rationale: str = "") -> dict:
    frames = load(path)
    return _append(path, "molt.ring", _stream_of(path), {
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "rationale": rationale[:400],
        "derived_from": frames[-1]["frame_hash"] if frames else None})


# ---------- §5.3 the gate ----------
# What each known contract requires of a ring. A contract this gate does not know is NOT
# waved through — an unrecognised contract is an unverifiable one (V5).
CONTRACTS = {
    "rapp/agent":     {"class": True, "methods": ("__init__",)},
    "rapp/brainstem-agent": {"class": True, "methods": ("__init__", "perform")},
}


def _check_contract(tree, contract: str) -> tuple[bool, str]:
    """V2 — does the ring satisfy the contract genesis recorded?"""
    if not contract:
        return False, "contract: genesis recorded none — unverifiable (V5)"
    spec = CONTRACTS.get(contract)
    if spec is None:
        return False, f"contract: {contract!r} unknown to this gate — unverifiable (V5)"
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if spec.get("class") and not classes:
        return False, f"contract: {contract} requires a class; none found"
    for want in spec.get("methods", ()):
        if not any(isinstance(b, ast.FunctionDef) and b.name == want
                   for c in classes for b in c.body):
            return False, f"contract: {contract} requires {want}(); missing"
    return True, f"contract: satisfies {contract}"


def _check_fertility(source: bytes) -> tuple[bool, str]:
    """V3 — is this ring a valid PARENT for a further generation, not merely loadable?
    A dead end passes every load test and still ends the lineage. Minimum bar: it parses,
    and it still exposes the adaptation surface the contract names (a class with the
    entry point), so the next generation has something to derive from."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"unparseable: {e}"[:120]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if not classes:
        return False, "sterile: no class to derive a further generation from"
    for c in classes:
        if any(isinstance(n, ast.FunctionDef) and n.name == "__init__" for n in c.body):
            return True, f"fertile: {c.name} can parent a further generation"
    return False, "sterile: no constructor — a subclass cannot initialize"


def judge(vchain: Path, chain: Path, ring_seq: int, source: bytes,
          gate_owner: str = "kody-w", gate_name: str = "gate", peers: list[bytes] = ()) -> dict:
    """THE GATE. Writes into the VERIFIER's stream — a host running this on itself is
    still writing to a stream it does not own, which rapp/1 rejects on ingest by anyone
    who checks. V5: every failure path below resolves to 'fail', never to silence."""
    frames = load(chain)
    target = next((f for f in frames if f["seq"] == ring_seq), None)
    if target is None:
        raise ValueError(f"no ring at seq {ring_seq}")
    checks, detail = {}, []

    # V2 structural — against the contract genesis actually RECORDED, not just "it parses".
    # The original implementation called ast.parse() and nothing else, while genesis's
    # `contract` field was never read once — so the check claimed conformance to a contract
    # it had never looked at. Found by adversarial audit 2026-08-26.
    contract = (frames[0]["payload"].get("contract") or "") if frames else ""
    try:
        tree = ast.parse(source)
        checks["structural"] = "pass"
    except Exception as e:
        tree = None
        checks["structural"] = "fail"; detail.append(f"structural: {e}"[:120])
    if tree is not None:
        ok_c, why_c = _check_contract(tree, contract)
        checks["contract"] = "pass" if ok_c else "fail"
        detail.append(why_c)

    # V2b the recorded content is the content being judged
    actual = hashlib.sha256(source).hexdigest()
    if actual != target["payload"].get("source_sha256"):
        checks["content"] = "fail"
        detail.append("source does not match the recorded ring — judging a different file")
    else:
        checks["content"] = "pass"

    # V3 fertility
    fert_ok, fert_why = _check_fertility(source)
    checks["fertility"] = "pass" if fert_ok else "fail"
    detail.append(fert_why)

    # V4 whole-set: interaction failures are visible only at set scope
    names = set()
    dup = False
    for blob in (list(peers) + [source]):
        try:
            for n in ast.walk(ast.parse(blob)):
                if isinstance(n, ast.ClassDef):
                    if n.name in names:
                        dup = True
                    names.add(n.name)
        except Exception:
            dup = True                                  # V5 unreadable is never pass
    checks["whole_set"] = "fail" if dup else "pass"
    if dup:
        detail.append("whole-set: duplicate class name across the composed set")

    verdict = "pass" if all(v == "pass" for v in checks.values()) else "fail"
    # The gate's identity is the trust anchor §5.4 points at, so it MUST be stable —
    # re-minting per verdict (the original bug) both violates rapp/1 §6.2 mint-once and
    # makes trust impossible to express, since the value a host trusted yesterday is gone.
    gate_rappid = _gate_identity(vchain, gate_owner, gate_name)
    vstream = f"verdict:@{gate_owner}/{gate_name}"
    return _append(vchain, "molt.verdict", vstream, {
        "ring": target["frame_hash"], "verdict": verdict, "checks": checks,
        "gate": gate_rappid, "detail": " · ".join(detail)[:400]})


def _gate_identity(vchain: Path, owner: str, name: str) -> str:
    """Mint the gate's rappid once and keep it beside its chain (§6.2 mint-once)."""
    side = Path(str(vchain) + ".rappid.json")
    if side.exists():
        try:
            return json.loads(side.read_text())["rappid"]
        except Exception:
            pass
    rid = R.mint_rappid(owner, name)
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(json.dumps({"rappid": rid, "kind": "molt.gate", "gate": name}, indent=2) + "\n")
    return rid


def trust(chain: Path, gate_rappid: str, note: str = "") -> dict:
    """Record that this host accepts verdicts from a named gate.

    Trust is DATA a host records deliberately, never something inferred from a verdict that
    shows up. Without this, activate() had only one test — "is this stream not literally
    mine?" — which an attacker passes by inventing any other stream name. Demonstrated
    2026-08-26: forging `verdict:@attacker/anything` activated a malicious ring."""
    if not R.rappid_valid(gate_rappid):
        raise ValueError(f"not a valid rappid: {gate_rappid!r}")
    return _append(chain, "molt.trust", _stream_of(chain),
                   {"gate": gate_rappid, "note": note[:200]})


def trusted_gates(chain: Path) -> set:
    return {f["payload"]["gate"] for f in load(chain) if f["kind"] == "molt.trust"}


# ---------- §5.4 activation ----------
def activate(chain: Path, vchain: Path, ring_seq: int) -> dict:
    """Fail-closed. Note what this function does NOT have to do: it never checks whether
    the verdict was self-issued, because a verdict in the host's own stream would have
    failed load(). V1 is arithmetic here, not policy."""
    if policy(chain) == "pinned":
        raise ValueError("locus is pinned — activation refused (§5.6)")
    frames = load(chain)
    target = next((f for f in frames if f["seq"] == ring_seq), None)
    if target is None:
        raise ValueError(f"no ring at seq {ring_seq}")
    if target["kind"] != "molt.ring":
        raise ValueError(f"seq {ring_seq} is {target['kind']}, not a ring")
    vframes = load(vchain)
    if not vframes:
        raise ValueError("no verdict chain — V5 fail closed, activation refused")
    host_stream = _stream_of(chain)
    trusted = trusted_gates(chain)
    if not trusted:
        raise ValueError("no trusted gate recorded on this locus — activation refused (V5). "
                         "Record one deliberately with trust(chain, <gate rappid>).")
    match = None
    for v in vframes:
        if v["kind"] != "molt.verdict":
            continue
        if v["payload"].get("ring") != target["frame_hash"]:
            continue
        if v["stream_id"] == host_stream:                       # V1, belt and braces
            raise ValueError("verdict is in the host's own stream — refused (§5.3 V1)")
        if v["payload"].get("gate") not in trusted:
            continue                       # a verdict from an unvouched gate is not evidence
        if v["payload"].get("verdict") == "pass":
            match = v
    if match is None:
        raise ValueError("no passing verdict from a TRUSTED verifier for this ring — refused (V5)")
    return _append(chain, "molt.activated", host_stream, {
        "ring": target["frame_hash"], "verdict": match["frame_hash"],
        "gate": match["payload"].get("gate")})


def revert(chain: Path, reason: str = "") -> dict:
    frames = load(chain)
    return _append(chain, "molt.reverted", _stream_of(chain),
                   {"to": frames[0]["frame_hash"], "reason": reason[:200]})


def set_policy(chain: Path, value: str) -> dict:
    if value not in ("mutable", "pinned"):
        raise ValueError("policy is 'mutable' or 'pinned'")
    return _append(chain, "molt.policy", _stream_of(chain), {"policy": value})


def policy(chain: Path) -> str:
    pol = [f for f in load(chain) if f["kind"] == "molt.policy"]
    return pol[-1]["payload"]["policy"] if pol else "mutable"


# ---------- §6 resolution ----------
def resolve(chain: Path) -> dict:
    """What should be running. R2: this MUST NOT fail — every error path lands on the
    floor, which is the whole reason the floor exists."""
    try:
        frames = load(chain)
        if not frames:
            return {"live": None, "why": "no chain", "at_floor": True}
        gen = frames[0]
        if policy(chain) == "pinned":
            return {"live": gen["frame_hash"], "why": "locus is pinned (§5.6)",
                    "at_floor": True, "floor_key": gen["payload_hash"]}
        live, why = gen["frame_hash"], "never molted — at genesis"
        for f in frames:
            if f["kind"] == "molt.activated":
                live, why = f["payload"]["ring"], f"activated at seq {f['seq']}"
            elif f["kind"] == "molt.reverted":
                live, why = gen["frame_hash"], f"reverted at seq {f['seq']}"
        return {"live": live, "why": why, "at_floor": live == gen["frame_hash"],
                "floor_key": gen["payload_hash"]}
    except Exception as e:
        return {"live": None, "why": f"chain unusable ({str(e)[:80]}) — FALL BACK TO FLOOR",
                "at_floor": True, "degraded": True}


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(0)
    cmd = a[0]
    if cmd == "genesis":
        print(json.dumps(genesis(Path(a[1]), a[2], Path(a[3]).read_bytes())["payload"], indent=2))
    elif cmd == "ring":
        print(json.dumps(ring(Path(a[1]), Path(a[2]).read_bytes(),
                              a[3] if len(a) > 3 else "")["payload"], indent=2))
    elif cmd == "judge":
        print(json.dumps(judge(Path(a[1]), Path(a[2]), int(a[3]),
                               Path(a[4]).read_bytes())["payload"], indent=2))
    elif cmd == "activate":
        print(json.dumps(activate(Path(a[1]), Path(a[2]), int(a[3]))["payload"], indent=2))
    elif cmd in ("pin", "unpin"):
        print(set_policy(Path(a[1]), "pinned" if cmd == "pin" else "mutable")["payload"])
    elif cmd == "resolve":
        print(json.dumps(resolve(Path(a[1])), indent=2))
    elif cmd == "floor":
        print(floor_key(Path(a[1])))
    else:
        print(__doc__)
