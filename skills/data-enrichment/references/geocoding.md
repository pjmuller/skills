# Forward geocoding (`scripts/geocode.py`)

`uv run scripts/geocode.py 'ADDRESS' [--provider mapbox|geopunt] [--limit 1..5] [--country be]`:
one request, 20 s timeout, no retries or batches. JSON stdout: `provider`, `query`, `storage`,
`attribution`, `results[]` (`lat`, `lng`, `label`, `type`, nullable `accuracy`, `id`). A street or
city match is not an address match: review candidates. Exit 0 = candidates, 3 = no match,
1 = JSON error on stderr, 2 = usage.

## Choose storage before calling

- **Mapbox (default): ephemeral only.** Scoped `MAPBOX_TOKEN` from your mise env; always
  `permanent=false`, no permanent mode. Consume stdout in memory; **never redirect, tee, log, cache,
  commit or save results, derived/offset coordinates included**, and use them only on a Mapbox map.
  The usual "store paid results" rule does not apply here.
- **Geopunt (`--provider geopunt`): storable.** Digitaal Vlaanderen Geolocation v4, no key,
  **Flanders and Brussels only**. Keep the emitted attribution, location type and source id with the
  stored coordinates; maps show `Bron: Digitaal Vlaanderen` (Modellicentie Gratis Hergebruik) or, for
  `urbis_` matches, `Bron: UrbIS / Paradigm`. Unknown source types fail until their storage rights
  are checked. No automatic fallback between providers: a miss stays a miss.

```sh
uv run scripts/geocode.py --provider geopunt 'Martelarenplein 7, 3000 Leuven' > location.json  # provenance
```

Small, deliberate lookups of public addresses only. Websites ship stored Geopunt coordinates, never
a per-visitor query. Other regions: pick and verify a storage-permitting provider explicitly; public
Nominatim is not a generic fallback (its policy demands identification, attribution, caching, limits).

Contracts checked 2026-10-19: [Mapbox geocoding](https://docs.mapbox.com/api/search/geocoding/) ·
[Geopunt](https://geo.api.vlaanderen.be/geolocation/)
([v4 params](https://geo.api.vlaanderen.be/geolocation/help/Api/GET-v4-Location_q_latlon_xy_type_c)) ·
[service terms](https://www.vlaanderen.be/digitaal-vlaanderen/onze-diensten-en-platformen/geografische-webdiensten/gebruiksrecht-en-privacyverklaring-geografische-webdiensten) ·
[Basisregisters license](https://docs.basisregisters.vlaanderen.be/docs/api-documentation.html) ·
[Flemish license](https://data.vlaanderen.be/doc/licentie/) ·
[UrbIS open data](https://be.brussels/en/about-region/urbis-data) ·
[Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/).
