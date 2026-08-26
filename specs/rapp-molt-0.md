# rapp-molt/0 — a rapp/1 profile for self-modifying agents

**Status:** draft-0 · **Depends on:** [rapp/1](https://github.com/kody-w/rapp-1)
**Supersedes:** `gitprotocol-molt(5)` (kody-w/git-molt), whose guarantees this carries
forward on rapp/1 frames instead of Git objects. See [LINEAGE.md](LINEAGE.md) for why.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as in
RFC 2119.

## 0. A molt IS a frame — this is a profile, not a second object model

**There is no "molt" object.** A ring is a rapp/1 frame. Genesis is a rapp/1 frame. A
verdict is a rapp/1 frame. This document defines **no new data structure, no new hash, no
new envelope, and no second verifier.** Strip the `kind` values out and what remains is an
ordinary chain that `rapp.py` already verifies.

What a profile adds is *meaning a host must act on*. Plain rapp/1 answers "is this record
authentic and in order?" It has no opinion about what a host may then **run**. Three rules
supply that, and none of them is a new mechanism:

| Rule | What it actually is |
|---|---|
| **The gate** (§5.3) | a convention that activation requires a `pass` frame in a *different stream* |
| **The floor** (§5.1) | a convention about which fields a seq-0 payload may contain |
| **Fertility** (V3) | a check the gate runs before it writes `pass` |

So the honest answer to "do frames and molts both need to exist?" is **no — only frames
exist.** rapp-molt/0 is the vocabulary for using them on a thing that rewrites itself, so
that behaviour is written down once instead of re-derived per agent. If that vocabulary
ever stops earning its keep, deleting this document leaves every chain it described still
valid and still verifiable. That is the test a profile has to pass, and it is the reason
this is a profile rather than a protocol.

Its predecessor could not be a profile: Git objects are not frames, so it had to build a
parallel mechanism (its own identity rule, its own bundles, its own verifier hook) to get
the same guarantees. That parallel mechanism — not the ideas in it — is what this retires.

## 1. The problem

An agent that rewrites itself has four problems Git alone does not solve:

1. **Divergence** — every instance adapts differently and nothing can tell you how far
   apart two copies have drifted, or in which direction.
2. **No floor** — after a bad adaptation there is nothing guaranteed to fall back to.
3. **No provenance** — you cannot prove which generation produced a behaviour, or that
   it was ever checked by anything.
4. **No interchange** — an adaptation learned on one instance cannot be handed to
   another without trusting the courier.

rapp/1 chains already give content-addressing, append-only history, tamper-evidence, and
interchange. This spec adds the three things a *self-modifying* thing needs on top:
**a gate between recording and activating**, **a guaranteed floor**, and **a fertility
requirement so lineages cannot degrade across generations.**

## 2. Vocabulary

| Term | Meaning |
|---|---|
| **locus** | one independently adaptable unit (typically one agent) |
| **ring** | one generation of a locus — a tree ring, counted outward from genesis |
| **genesis** | ring 0: the factory baseline, the floor a locus can always return to |
| **molt** | the act of recording a new ring |
| **gate** | the verifier that decides whether a ring may be *activated* |
| **live** | the ring a locus currently runs |

## 3. Identity — and the law this spec exists to keep

A locus MUST carry a rappid minted once per rapp/1 §6.2 (uuid entropy, or a key's SPKI).
**A locus identity MUST NOT be derived from its name, its content, or any hash of
either.** Two loci that happen to share a name are two loci.

This spec's predecessor derived the locus id from *name + content*, to buy one real
property: the same agent gets the same id on every machine, with no coordination. That
property is worth keeping — but a name-hash buys it by making collision *definitional*,
which is how a fleet ends up with several things it cannot tell apart.

rapp/1 supplies both properties natively, because a frame has two hashes:

- **`payload_hash` (the particle)** is computed from payload content alone. Two hosts
  that build a genesis frame from byte-identical baseline source and identical payload
  fields produce **the same `payload_hash`** — with no coordination whatsoever. This is
  the **floor key**: the world-wide "same agent, same baseline version" equivalence key.
- **`frame_hash` (the wave)** additionally covers `stream_id`, which carries the locus's
  minted rappid. It is therefore **unique per instance** and cannot collide.

So: **equivalence rides the particle; identity rides the wave.** The predecessor had to
choose one and chose the colliding one. Nothing is given up by refusing name-hashes.

A genesis payload MUST therefore contain only reproducible fields (§5.1) — no rappid, no
timestamp, no hostname — or the floor key is not shared and this property is lost.

## 4. Chains

A lineage uses **two** streams, and the separation is the whole enforcement mechanism.

| Stream | Written by | Carries |
|---|---|---|
| `molt:@<owner>/<locus>` | the **host** | genesis, rings, activations, reversals, policy |
| `verdict:@<verifier>/<name>` | the **verifier** | verdicts on rings |

A locus's chain MUST be linear and append-only — which rapp/1 gives for free: a frame
names exactly one `prev`, so a lineage cannot fork or merge within a stream.

## 5. Frame kinds

### 5.1 `molt.genesis` (seq 0) — the floor

```json
{ "kind": "molt.genesis", "stream_id": "molt:@owner/planner", "seq": 0,
  "payload": { "locus": "planner", "source_sha256": "<of the baseline bytes>",
               "contract": "<runtime agent-contract id>", "molt": "rapp-molt/0" } }
```

- The payload MUST contain only fields reproducible from the baseline distribution.
- A host MUST NOT rewrite or re-mint genesis. It is the floor for the life of the locus.
- Two loci whose genesis `payload_hash` matches are running the same baseline (§3).
- A host MUST be able to restore the genesis source bytes without network access.

### 5.2 `molt.ring` — one generation

```json
{ "kind": "molt.ring", "payload": {
    "source_sha256": "<of this generation's bytes>", "rationale": "…",
    "derived_from": "<frame_hash of the ring this adapted>" } }
```

Recording a ring is **always permitted**. It grants nothing.

### 5.3 `molt.verdict` — minted in the VERIFIER's stream, never the host's

```json
{ "kind": "molt.verdict", "stream_id": "verdict:@owner/gate", "payload": {
    "ring": "<frame_hash of the ring judged>", "verdict": "pass" | "fail",
    "checks": { "structural": "pass", "fertility": "pass", "whole_set": "pass" },
    "gate": "<verifier rappid>", "detail": "…" } }
```

**V1 · The verdict belongs to the verifier.** A candidate MUST NOT be able to determine
its own verdict. Under this spec that is *structural rather than procedural*: a verdict
lives in the verifier's stream, chained under the verifier's identity, so a host cannot
mint one at all — an appended frame carrying a foreign `stream_id` fails rapp/1
verification. The predecessor achieved this by asking every host to install a
`pre-receive` hook; here, forging a verdict is not a policy violation but an invalid
frame.

**V2 · Structural validity.** The ring MUST satisfy the runtime's agent contract.

**V3 · Fertility.** The ring MUST itself be a valid parent for a further generation. A
ring that loads but can never be adapted again is a dead end and MUST NOT be activated.
This is what stops a lineage from degrading into sterility over many generations.

**V4 · Whole-set validation.** The complete composed set MUST be validated together, not
only ring by ring — duplicate tool names and import collisions are visible only at set
scope.

**V5 · Fail closed.** Any ambiguity — timeout, crash, unreadable output, malformed
metadata, a missing verdict — MUST resolve to *not verified*. Unreadable is never pass.

### 5.4 `molt.activated`

```json
{ "kind": "molt.activated", "payload": {
    "ring": "<ring frame_hash>", "verdict": "<verdict frame_hash>",
    "gate": "<verifier rappid>" } }
```

A host MUST NOT append `molt.activated` unless it holds a `pass` verdict frame naming
exactly that ring, from a verifier it trusts, that verifies against the verifier's chain.

### 5.5 `molt.reverted`

```json
{ "kind": "molt.reverted", "payload": { "to": "<genesis frame_hash>", "reason": "…" } }
```

Reversal is an append, never a deletion; the reverted rings remain in the chain and MAY
be re-activated later.

### 5.6 `molt.policy` — `mutable` (default) or `pinned`

A `pinned` locus MUST resolve to genesis regardless of what has been activated, and a
host MUST refuse to activate a ring on it. Recording rings remains permitted. This lets
an operator freeze a compliance-critical agent at its factory source for life while an
adjacent agent adapts continuously.

## 6. Resolution and composition

**R1 · Resolve.** The live ring is the ring named by the most recent `molt.activated`
frame not followed by a `molt.reverted`. If the chain is missing, unreadable, broken, or
the locus is `pinned`, resolve to **genesis**.

**R2 · Fail-safe.** Composition MUST NOT fail. Every error path falls back — to the last
activated ring, and ultimately to genesis. The composed set MUST always be loadable.

**R3 · Atomic activation.** The set MUST be staged, validated whole (V4), then activated
atomically. A partially composed set MUST NOT serve traffic.

**R4 · Substitute, never subtract.** A lineage layer MUST NOT make an instance less
capable than the same instance without it. Any failure in lineage control MUST degrade to
the runtime's native behaviour.

**R5 · Zero-adaptation identity.** With every locus at genesis, the composed output MUST
be byte-identical to what the host produces with no lineage layer at all. **Adopting this
spec MUST be a no-op until something molts.**

## 7. The code/data boundary

**B1.** Lineage versions *code*. Agent memory, user data, and conversation state are NOT
rings and MUST NOT be reverted by a lineage operation. This separation is what makes
reversal safe to hand to an end user: factory behaviour is restored while everything they
accumulated persists.

**B2.** Reversal is an append (§5.5) — non-destructive, and re-activation stays available.

**B3.** Reversal SHOULD be directly reachable by the user, without operator tooling, and
MUST NOT interfere with normal operation if it fails (R4).

**B4 · Honest reporting.** A host MUST NOT report a state change that did not occur. If
the layer is disabled, a locus is pinned, or some loci failed, the response MUST say so.

**B5 · Disable means disable.** When the layer is disabled a host MUST NOT record
deferred activations that would silently fire on re-enable.

## 8. Interchange

Interchange is rapp/1's. A lineage travels as an **egg** (rapp/1 §8) or a `.dogg` bundle,
over the network, a LAN pool, or sneakernet.

**I1 · Verify on ingest.** A receiver MUST re-verify every frame of an ingested chain
against its own copy of genesis before considering any ring. A chain whose genesis
`payload_hash` differs from the receiver's floor is **a different lineage**, not an
update, and MUST NOT be merged into it.

**I2.** An ingested ring arrives *unactivated*, always. Someone else's verdict is
evidence, not authority; the receiving host's own gate decides (V1).

## 9. Conformance

A **Recorder** implements §4, §5.1, §5.2, §8.
A **Host** additionally implements §5.4–5.6, §6, §7 and MUST fail closed per V5.
A **Gate** implements §5.3 including V2, V3, V4, and MUST NOT be co-resident with the
authority of the candidate it judges.

An implementation claiming rapp-molt/0 MUST pass [`conformance.py`](conformance.py).
