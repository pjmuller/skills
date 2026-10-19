#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""One forward lookup. Mapbox output is ephemeral; Geopunt output may be stored."""
import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MAPBOX = "https://api.mapbox.com/search/geocode/v6/forward"
GEOPUNT = "https://geo.api.vlaanderen.be/geolocation/v4/Location"
MAX_BYTES = 2 * 1024 * 1024


class GeocodeError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect must not forward the Mapbox token to another endpoint.
        return None


def request_json(endpoint, params):
    request = urllib.request.Request(
        endpoint + "?" + urllib.parse.urlencode(params),
        headers={"Accept": "application/json", "User-Agent": "data-enrichment-geocode/1.0"},
    )
    try:
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(request, timeout=20) as response:
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise GeocodeError("Response exceeds 2 MiB; no retry made")
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        raise GeocodeError(f"Provider HTTP {exc.code}; no retry made") from None
    except (urllib.error.URLError, OSError):
        raise GeocodeError("Network request failed; no retry made") from None
    except (ValueError, UnicodeError):
        raise GeocodeError("Provider returned invalid JSON") from None


def coordinates(lat, lng):
    lat, lng = float(lat), float(lng)
    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError
    return {"lat": lat, "lng": lng}


def forward(query, provider="mapbox", limit=1, country=None):
    query = query.strip()
    if not 2 <= len(query) <= 256 or ";" in query:
        raise GeocodeError("Query must be 2..256 characters without semicolons")
    if provider not in ("mapbox", "geopunt") or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise GeocodeError("Choose mapbox or geopunt and limit 1..5")
    if country and (len(country) != 2 or not country.isascii() or not country.isalpha()):
        raise GeocodeError("Country must be a two-letter ISO code")
    if provider == "geopunt" and country:
        raise GeocodeError("--country is Mapbox-only; Geopunt covers Flanders and Brussels")
    if provider == "mapbox":
        token = os.environ.get("MAPBOX_TOKEN", "").strip()
        if not token:
            raise GeocodeError("MAPBOX_TOKEN is missing; load your scoped mise env")
        params = {"q": query, "limit": limit, "access_token": token,
                  "permanent": "false", "autocomplete": "false"}
        if country:
            params["country"] = country.lower()
        data = request_json(MAPBOX, params)
    else:
        data = request_json(GEOPUNT, {"q": query, "c": limit})
    try:
        results = []
        items = data["features" if provider == "mapbox" else "LocationResult"]
        if not isinstance(items, list):
            raise ValueError
        for item in items[:limit]:
            if provider == "mapbox":
                props = item["properties"]
                lng, lat = item["geometry"]["coordinates"]
                result = {"label": props.get("full_address") or props["name"],
                          "type": props["feature_type"], "id": props.get("mapbox_id"),
                          "accuracy": props.get("coordinates", {}).get("accuracy")}
            else:
                location = item["Location"]
                lat, lng = location["Lat_WGS84"], location["Lon_WGS84"]
                result = {"label": item["FormattedAddress"], "type": item["LocationType"],
                          "id": item.get("ID"), "accuracy": None}
                if not result["type"].startswith(("basisregisters_", "urbis_")):
                    raise GeocodeError("Unrecognized Geopunt source; storage rights not established")
            result.update(coordinates(lat, lng))
            results.append(result)
        attribution = data.get("attribution", "© Mapbox and its suppliers") if provider == "mapbox" else (
            "; ".join(source for prefix, source in (
                ("basisregisters_", "Bron: Digitaal Vlaanderen"), ("urbis_", "Bron: UrbIS / Paradigm"))
                if any(result["type"].startswith(prefix) for result in results)))
        return {"provider": provider, "query": query,
                "storage": "ephemeral_only" if provider == "mapbox" else "storable_with_attribution",
                "attribution": attribution, "results": results}
    except (KeyError, TypeError, ValueError, OverflowError):
        raise GeocodeError("Provider returned an unexpected result schema") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Public address or place; one lookup per invocation")
    parser.add_argument("--provider", choices=("mapbox", "geopunt"), default="mapbox")
    parser.add_argument("--limit", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--country", help="Mapbox-only ISO country code, e.g. be")
    args = parser.parse_args(argv)
    try:
        result = forward(args.query, args.provider, args.limit, args.country)
    except GeocodeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except Exception:
        # Never include upstream exception text: it can contain the credential-bearing URL.
        print(json.dumps({"error": "Unexpected geocoding failure; no retry made"}), file=sys.stderr)
        return 1
    if args.provider == "mapbox":
        print("Mapbox temporary: stdout is ephemeral. Do not save, log or cache it; use only with a Mapbox map.",
              file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["results"] else 3


if __name__ == "__main__":
    sys.exit(main())
