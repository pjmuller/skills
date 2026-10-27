# Google My Maps

My Maps (`google.com/maps/d`) is not Google Maps Platform (paid geo APIs for apps). Its content has no
read/write REST API (Maps Engine API ended 2016): Drive handles discovery, feature export goes through
the browser or the Data Portability API, editing through the My Maps UI. Verified 2026-10.

| Capability | OAuth token | Browser session as the owning account |
|---|---|---|
| Discover / metadata / sharing | ✅ `drive-search "mimeType='application/vnd.google-apps.map'"` | ✅ |
| Read features (KML) | ❌ Drive `export`/`alt=media`: 403 "Export only supports Docs Editors files". Official route: Data Portability `mymaps.maps` (KMZ archive, async, 1×/24 h, time-limited consent) | ✅ `https://www.google.com/maps/d/kml?mid=<id>&forcekml=1` with the session's cookies (the UI's own export, undocumented; private maps 403 anonymously) |
| Edit features / layers | ❌ | ⚠️ UI only: import KML/CSV/XLSX/GPX/Sheet as a layer (≤2,000 rows, KML ≤5 MB), or "reimport" a Sheet/CSV layer |
| Create / copy a map | ❌ (`canCopy=false`) | ⚠️ UI |

- **Read in a browser automation tool:** in a tab signed in as the owner, `fetch(kml_url, {credentials:'include'})`
  → blob → download; never paste cookies into scripts or chat.
- **Writes:** keep the data in a Google Sheet (API read/write), import it once as a layer, then refresh
  with the layer's reimport (one UI click). Changing an existing map needs the user's request for that map.

Sources: [Drive MIME types](https://developers.google.com/workspace/drive/api/guides/mime-types),
[export formats](https://developers.google.com/workspace/drive/api/guides/ref-export-formats) (no map entry),
[Data Portability My Maps](https://developers.google.com/data-portability/schema-reference/mymaps),
[time-based access](https://developers.google.com/data-portability/user-guide/time-based),
[import limits](https://support.google.com/mymaps/answer/3024836).
