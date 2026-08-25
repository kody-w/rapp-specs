# cast/0 — films as verifiable casts

A **cast** is one `cast.video` frame on a channel's `casts/` chain (rapp/1 envelope,
DOGG dir form) binding a video file to the network:

```json
{ "kind": "cast.video", "stream_id": "cast:@owner/channel",
  "payload": { "title": "…", "description": "…", "file": "videos/name.mp4",
               "bytes": 35063247, "sha256": "<of the file>",
               "tick": 102, "tick_frame": "<spine anchor>", "published_utc": "…" } }
```

Rules: the file is immutable once cast (a re-cut is a NEW cast frame); recompute the
sha256 to verify any copy of the film, over any transport; the publish tick anchors the
film in shared time. A player page may present the film beside live network data, but
the frame — not the page — is the record. Files over ~95 MB must split into part casts
(one frame per part) or ship via releases; hosts cap single files at 100 MB.
