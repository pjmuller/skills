"""Offline contract tests. Fixtures are synthetic; never call or retain Mapbox live results."""
import io
import json
import subprocess
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import geocode


def feature():
    return {"properties": {"full_address": "Example Road 1", "feature_type": "address",
                           "mapbox_id": "synthetic", "coordinates": {"accuracy": "rooftop"}},
            "geometry": {"coordinates": [4.7, 50.9]}}


def transport(monkeypatch, body=None, error=None):
    calls = []

    class Opener:
        def open(self, req, timeout):
            calls.append((req, timeout))
            if error:
                raise error
            return io.BytesIO(body)

    def build_opener(*handlers):
        assert geocode.NoRedirect in handlers
        return Opener()

    monkeypatch.setattr(geocode.urllib.request, "build_opener", build_opener)
    return calls


def test_mapbox_flags_one_request_and_no_files(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.synthetic-secret")
    calls = transport(monkeypatch, json.dumps({"features": [feature()], "attribution": "test"}).encode())
    assert geocode.main(["Example Road 1", "--country", "BE"]) == 0
    req, timeout = calls[0]
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
    assert len(calls) == 1 and timeout == 20
    assert params == {"q": ["Example Road 1"], "limit": ["1"], "access_token": ["pk.synthetic-secret"],
                      "permanent": ["false"], "autocomplete": ["false"], "country": ["be"]}
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["storage"] == "ephemeral_only"
    assert result["results"][0]["lat"] == 50.9
    assert result["results"][0]["lng"] == 4.7
    assert "Do not save" in output.err
    assert "synthetic-secret" not in output.out + output.err
    assert list(tmp_path.iterdir()) == []


def test_geopunt_is_keyless_and_preserves_source(monkeypatch, capsys):
    monkeypatch.delenv("MAPBOX_TOKEN", raising=False)
    payload = {"LocationResult": [{"Location": {"Lat_WGS84": 50.9, "Lon_WGS84": 4.7},
                                  "FormattedAddress": "Example Road 1", "ID": 123,
                                  "LocationType": "basisregisters_huisnummer_afgeleidVanObject"}]}
    calls = transport(monkeypatch, json.dumps(payload).encode())
    assert geocode.main(["Example Road 1", "--provider", "geopunt", "--limit", "2"]) == 0
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0][0].full_url).query)
    assert params == {"q": ["Example Road 1"], "c": ["2"]}
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["storage"] == "storable_with_attribution"
    assert "Digitaal Vlaanderen" in result["attribution"]
    assert "UrbIS" not in result["attribution"]
    assert result["results"][0]["id"] == 123
    assert result["results"][0]["type"] == payload["LocationResult"][0]["LocationType"]
    assert output.err == ""


def test_geopunt_brussels_attribution(monkeypatch):
    payload = {"LocationResult": [{"Location": {"Lat_WGS84": 50.8, "Lon_WGS84": 4.3},
                                  "FormattedAddress": "Example Road 1", "ID": 123,
                                  "LocationType": "urbis_huisnummer"}]}
    transport(monkeypatch, json.dumps(payload).encode())
    result = geocode.forward("Example Road 1", provider="geopunt")
    assert result["attribution"] == "Bron: UrbIS / Paradigm"
    assert result["results"][0]["accuracy"] is None


@pytest.mark.parametrize("error", [
    urllib.error.HTTPError("https://example.com?access_token=pk.secret", 429, "pk.secret", {}, None),
    urllib.error.URLError("https://example.com?access_token=pk.secret"),
    RuntimeError("https://example.com?access_token=pk.secret"),
])
def test_errors_redact_credentials_and_never_retry(monkeypatch, capsys, error):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.secret")
    calls = transport(monkeypatch, error=error)
    assert geocode.main(["Example Road 1"]) == 1
    output = capsys.readouterr()
    assert len(calls) == 1 and not output.out
    assert "error" in json.loads(output.err)
    assert "pk.secret" not in output.err and "https:" not in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("body", [b'not json pk.secret', b'{"features":null}', b'{}',
                                  b'{"features":[{"properties":{}}]}', b'[]',
                                  b'x' * (geocode.MAX_BYTES + 1)])
def test_invalid_responses_are_safe_errors(monkeypatch, capsys, body):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.secret")
    transport(monkeypatch, body)
    assert geocode.main(["Example Road 1"]) == 1
    output = capsys.readouterr()
    assert not output.out and "pk.secret" not in output.err
    assert "error" in json.loads(output.err)


def test_no_match_has_distinct_exit_code(monkeypatch, capsys):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.synthetic")
    transport(monkeypatch, b'{"features":[]}')
    assert geocode.main(["No such road"]) == 3
    assert json.loads(capsys.readouterr().out)["results"] == []


def test_missing_token_and_invalid_arguments_do_not_call(monkeypatch, capsys):
    monkeypatch.delenv("MAPBOX_TOKEN", raising=False)
    calls = transport(monkeypatch, b'{}')
    assert geocode.main(["Example Road 1"]) == 1
    assert "MAPBOX_TOKEN" in capsys.readouterr().err
    for query in ("", "x", "x" * 257, "Example; Road"):
        assert geocode.main([query]) == 1
    assert geocode.main(["Example Road", "--country", "Belgium"]) == 1
    assert geocode.main(["Example Road", "--provider", "geopunt", "--country", "be"]) == 1
    for flag in ("--permanent", "--cache", "--out"):
        with pytest.raises(SystemExit) as exc:
            geocode.main(["Example Road", flag, "true"])
        assert exc.value.code == 2
    assert not calls


@pytest.mark.parametrize("lat,lng", [(float("nan"), 4), (50, 181), (-91, 4)])
def test_bad_coordinates_are_rejected(lat, lng):
    with pytest.raises(ValueError):
        geocode.coordinates(lat, lng)


def test_redirect_does_not_forward_token():
    assert geocode.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example") is None


def test_uv_does_not_modify_the_calling_project(tmp_path):
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nname="unrelated"\nversion="1.0"\ndependencies=["not-a-real-package-geocode"]\n')
    run = subprocess.run(["uv", "run", "--offline", str(Path(geocode.__file__).resolve()), "--help"],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pyproject.toml"]


def test_unknown_geopunt_source_does_not_claim_storage_rights(monkeypatch, capsys):
    payload = {"LocationResult": [{"Location": {"Lat_WGS84": 50.8, "Lon_WGS84": 4.3},
                                  "FormattedAddress": "Example Road 1", "ID": 123,
                                  "LocationType": "future_paid_source"}]}
    transport(monkeypatch, json.dumps(payload).encode())
    assert geocode.main(["Example Road", "--provider", "geopunt"]) == 1
    assert "storage rights not established" in capsys.readouterr().err
