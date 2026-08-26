#!/usr/bin/env python3
"""mutation_check.py — prove the conformance suite actually TESTS what it claims.

A suite reporting 33/33 tells you nothing on its own. Round-3 adversarial audit
(2026-08-26) showed this concretely: `_check_fertility` could be deleted outright and
rapp-molt/0 conformance still reported 29/29, because the sterile fixture also tripped a
different guard. Three more guards were equally untested — V4 whole-set, the one-class
contract rule, and V5's unknown-contract branch. Several tests "passed" via a bare
`except ValueError` that a completely unrelated error satisfies.

So: break each guard on purpose, in a scratch copy, and require the suite to NOTICE.
A guard whose removal leaves the suite green is not covered, and this script says so.

    python3 mutation_check.py          exit 0 only if EVERY mutation is caught
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (name, file, pattern-to-replace, replacement) — each neuters exactly one guard.
MUTATIONS = [
    ("V3 fertility check entirely", "molt.py",
     r"    ok_f, fert_why = _check_fertility\(source\)|    fert_ok, fert_why = _check_fertility\(source\)",
     "    fert_ok, fert_why = True, 'MUTATED: fertility disabled'"),
    ("V3 requires constructible-by-descendant", "molt.py",
     r"        if unfilled <= 0 and kwonly_unfilled == 0:",
     "        if True:  # MUTATED: accept any constructor"),
    ("V4 whole-set duplicate detection", "molt.py",
     r'    checks\["whole_set"\] = "fail" if dup else "pass"',
     '    checks["whole_set"] = "pass"  # MUTATED'),
    ("V2 one-class-satisfies-whole-contract", "molt.py",
     r"        if all\(w in have for w in wants\):",
     "        if any(w in have for w in wants) or True:  # MUTATED: any-class"),
    ("V5 unknown contract is unverifiable", "molt.py",
     r"        return False, f\"contract: \{contract!r\} unknown to this gate — unverifiable \(V5\)\"",
     '        return True, "MUTATED: unknown contract waved through"'),
    ("genesis re-mint refusal", "molt.py",
     r'        raise ValueError\("genesis already minted — a floor is never re-minted \(§5\.1\)"\)',
     '        pass  # MUTATED: allow re-mint'),
    ("trust anchor requirement (V1)", "molt.py",
     r'        raise ValueError\("no trusted gate recorded on this locus — activation refused \(V5\). "',
     '        trusted = {"MUTATED-any"} or ValueError("'),
    ("host-own-stream verdict refusal (V1)", "molt.py",
     r'            raise ValueError\("verdict is in the host\'s own stream — refused \(§5\.3 V1\)"\)',
     '            pass  # MUTATED: accept self-issued'),
    ("content-matches-recorded-ring check", "molt.py",
     r'        checks\["content"\] = "fail"',
     '        checks["content"] = "pass"  # MUTATED'),
    ("pinned policy blocks activation", "molt.py",
     r'        raise ValueError\("locus is pinned — activation refused \(§5\.6\)"\)',
     '        pass  # MUTATED: ignore pin'),
]


def run_suite(d: Path) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, "conformance_molt.py"], cwd=d,
                       capture_output=True, text=True, timeout=600)
    tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
    return r.returncode == 0, tail[0]


def main() -> int:
    scratch = Path(tempfile.mkdtemp(prefix="molt-mutation-"))
    try:
        work = scratch / "tools"
        shutil.copytree(HERE, work)
        shutil.copy(HERE.parent / "rapp.py", scratch / "rapp.py")
        ok, line = run_suite(work)
        print(f"baseline (unmutated): {'PASS' if ok else 'FAIL'} — {line}")
        if not ok:
            print("  the suite must be green before mutation testing means anything")
            return 1

        pristine = {f: (work / f).read_text() for f in {m[1] for m in MUTATIONS}}
        caught, missed, skipped = [], [], []
        for name, fname, pat, repl in MUTATIONS:
            (work / fname).write_text(pristine[fname])          # restore
            src = pristine[fname]
            new, n = re.subn(pat, repl, src, count=1)
            if n == 0:
                skipped.append(name)
                continue
            (work / fname).write_text(new)
            still_green, tail = run_suite(work)
            (caught, missed)[still_green].append((name, tail))
            print(f"  {'❌ UNCAUGHT' if still_green else '✅ caught  '}  {name}")
        for f, txt in pristine.items():
            (work / f).write_text(txt)

        print(f"\ncaught {len(caught)}/{len(caught) + len(missed)} mutations"
              + (f"   ({len(skipped)} pattern(s) did not match — treated as FAILURE)" if skipped else ""))
        if missed:
            print("\nUNTESTED GUARDS — removing these changes no test result:")
            for name, tail in missed:
                print(f"  • {name}   (suite still: {tail})")
        if skipped:
            print("\nPATTERN DRIFT — these mutations no longer apply; the guard may have moved:")
            for name in skipped:
                print(f"  • {name}")
        return 0 if (not missed and not skipped) else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
