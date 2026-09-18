# User workflow comparisons

Select cases by behavior and interactions: simple baseline, unusual data types, conditional/repeated structures, locale/timezone, import/export, multi-step flows and existing-record edits. Include authorization and failure states. Use real examples for realism and owned synthetic fixtures for precise expected outcomes. A large corpus does not replace an adversarial combination.

## Compare what the user experiences

Use equivalent identity, configuration, input and starting data. Verify which version and environment each interface actually reaches. For browsers, check redirects, cookies, cached assets and public/share links: an existing session can hide a broken login path.

When the medium changes (e.g. desktop to web), compare task outcomes and persisted/exported artifacts; do not demand identical layout or interaction mechanics. Check that old-saved artifacts open correctly in the new system and round-trip where compatibility requires it. Within the same medium, compare visual and semantic results: labels/options/order, visibility, selected values, validation and keyboard behavior; include responsive layouts where relevant.

Screenshots complement state and persisted-data checks. Browser DOM, console and network inspection help locate failures. Wait for meaningful readiness; distinguish animation/capture artifacts from real layout defects. Explain visual deviations rather than broadly weakening assertions.

## Test the full loop

Create → persist → cold reopen → modify → verify retained, replaced and removed data. Confirm unchanged content survives. Exercise downstream use: an editor's preview does not prove its exported artifact works in the consuming application.

Choose combinations that cross boundaries, such as embedded assets plus related records, or locale-sensitive values through export/import. Test missing permissions, unavailable dependencies and repeat actions without triggering uncontrolled duplicate writes. A clicked button is not proof of execution; a success screen is not proof of correct persistence.

Follow the [data/effect execution and cleanup guidance](data-and-effects.md#replay-versus-real-execution). When writes are prohibited, prevent effects before transmission and label the proof read-only.

## Handoff and future diagnosis

Humans add most value on workflow fit, confusing interactions, visual quality and representative business edge cases. Give exact entry points, access steps, safe test scope, known gaps and what automation already proved.

Document a short case-based support path: case ID → version/settings → inputs/schema → interaction → persistence/effects. Default diagnosis to reads; require existing task authorization for writes. Keep one reproducible failing example before fixing, then recheck the integrated flow.
