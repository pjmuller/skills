# Forward geocoding

`uv run scripts/geocode.py 'ADDRESS' [--provider mapbox|geopunt] [--limit 1..5]`
(paths relative to this skill). One request, 20s timeout, no retries, batches or saved responses.
JSON stdout contains `provider`, `query`, `storage`, `attribution` and `results` with named
`lat`/`lng`, `label`, `type`, `accuracy` (nullable), `id`. Review candidates: a street/city match is not
an address match. Exit 0 = candidates, 3 = no match, 1 = JSON error on stderr, 2 = CLI usage.

## Choose storage before calling

- **Mapbox (default): ephemeral only.** Needs `MAPBOX_TOKEN` from your scoped mise env.
  Always sends `permanent=false`, `autocomplete=false`, default limit 1; optional `--country be`.
  No permanent mode. Consume stdout in memory; never redirect, tee, log, cache, commit or save
  results, including derived/offset coordinates. Only use with a Mapbox map.
  The usual paid-enrichment cache rule does **not** apply here.
- **Geopunt (`--provider geopunt`): stored website coordinates.** Official Digitaal Vlaanderen
  Geolocation v4, no key; **Flanders and Brussels only**, not Wallonia or worldwide.
  Results may be saved. Preserve helper-emitted attribution and original location type/source ID.
  Flemish Basisregisters data uses Modellicentie Gratis Hergebruik; show
  `Bron: Digitaal Vlaanderen` on maps. Brussels UrbIS is open data; retain `Bron: UrbIS / Paradigm`
  for `urbis_` matches. Unknown source types fail until their storage rights are checked.
  No automatic provider fallback: a miss stays a miss.

```sh
# Persistable address lookup; keep this JSON as provenance alongside your website data.
uv run scripts/geocode.py --provider geopunt 'Martelarenplein 7, 3000 Leuven' > location.json
```

Small, deliberate lookups only. Send public addresses, not confidential/personal data.
A website should ship stored Geopunt coordinates rather than query this service per visitor.
For other regions choose and verify a storage-permitting provider explicitly.
The public Nominatim service is not a generic fallback for agent-built geocoding tools;
its policy also requires identification, attribution, caching and traffic limits.

Primary contracts checked 2026-10-19:

- [Mapbox storage, request flags, map-use restriction](https://docs.mapbox.com/api/search/geocoding/).
- [Geopunt coverage and response fields](https://geo.api.vlaanderen.be/geolocation/),
  [v4 parameters](https://geo.api.vlaanderen.be/geolocation/help/Api/GET-v4-Location_q_latlon_xy_type_c).
- [Service terms defer to dataset licenses](https://www.vlaanderen.be/digitaal-vlaanderen/onze-diensten-en-platformen/geografische-webdiensten/gebruiksrecht-en-privacyverklaring-geografische-webdiensten),
  [Basisregisters license](https://docs.basisregisters.vlaanderen.be/docs/api-documentation.html),
  [Flemish license terms](https://data.vlaanderen.be/doc/licentie/),
  [UrbIS open data](https://be.brussels/en/about-region/urbis-data).
- [Public Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/).
