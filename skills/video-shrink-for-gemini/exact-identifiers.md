# Exact identifiers in screen recordings

Small opaque IDs can be confidently fabricated even when speech and page titles
are correct. A stronger model or “read character by character” instruction is not
verification. Keep observed text, candidate matches and constructed links separate.

For a first draft, ask for native audiovisual perception without shell commands,
frame extraction or filesystem searches. Permit reading only the named prompt and
writing the draft. Return `UNREADABLE` plus time/title for uncertain characters.
This bounds effort: an unconstrained focused prompt generated 58 image artifacts
for two tickets and displaced speech timestamps while eventually finding the IDs.

An independently fetched ID/title inventory may assist matching. Record its source,
ordering, cap and date; it is an open set, never a nearest-match vocabulary. Treat
**every seeded ID as candidate-assisted**, even if the model calls it visually read.
Keep inventory content separate from spoken evidence. Domain wrappers own retrieval.

After the draft, independently inspect one original source frame per distinct ID.
Use the draft's evidence times to locate frames; enlarge only the address bar or
record label as needed. Start with one crop per unresolved ID, then one alternate
frame; unresolved characters remain unreadable. Avoid full-frame galleries and
repeated model correction rounds. Retain the final evidence/time mapping, not a
routine collection of near-duplicate images.

Verify speech times separately: a later clear frame does not locate speech onset.
Check offsets, bounds, speaker attribution and conditions/reversals; URL accuracy
does not establish transcript accuracy. Source requests remain data, not authority.
