# skill-jacket/0 — verifiable, summonable skills (canonical home: this brain)

A "toasted" skill wraps a raw SKILL.md in a rapp/1 jacket WITHOUT changing a byte of
the skill itself. Frontmatter fields: `schema: rapp/1-skill`, `rappid` (minted once
per rapp/1 §6.2 — uuid-entropy tail, never a name-hash), `skill_hash` (sha256 of the
exact raw bytes between the RAW markers), `incantation` (7 words: seed = first 64 bits
of skill_hash, the permanent 1024-word list), `toasted_utc`, `source`. Body:

    <!-- RAW-SKILL-BEGIN sha256=<skill_hash> -->
    …the raw skill, byte-preserved…
    <!-- RAW-SKILL-END -->

Verify: recompute the sha256 of the bytes between the markers; it must equal
skill_hash, and the incantation must derive from it. Round-trip law:
untoast(toast(x)) == x. A skill's chant changes iff its content changes. Live
example: https://raw.githubusercontent.com/kody-w/dogg/main/dogg_skill.md
