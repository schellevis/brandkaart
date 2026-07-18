"""Adapternormalisatie op synthetische bronfragmenten (geen netwerk)."""

from datetime import datetime, timezone

from pipeline.adapters import (
    aemet_danger,
    aemet_warnings,
    cems_rapid_mapping,
    firms,
    meteo_forets,
)


def test_firms_rij_normaliseren():
    row = {
        "latitude": "48.4047",
        "longitude": "2.7075",
        "bright_ti4": "345.2",
        "acq_date": "2026-07-15",
        "acq_time": "134",
        "satellite": "N20",
        "instrument": "VIIRS",
        "confidence": "n",
        "frp": "12.3",
        "daynight": "D",
    }
    record, key, observed = firms._normalize_row(row, "VIIRS_NOAA20_NRT", "2026-07-15T12:00:00Z")
    assert record["kind"] == "detection"
    assert record["certainty"] == "nominal"
    assert record["geometry"]["coordinates"] == [2.7075, 48.4047]
    assert record["observed_at"] == "2026-07-15T01:34:00Z"
    assert record["source_attrs"]["frp"] == "12.3"
    assert key[0] == "N20"
    # Vrije velden buiten de bewuste attributenlijst komen niet mee.
    assert "version" not in record["source_attrs"]


def test_firms_modis_numerieke_confidence_wordt_ingedeeld():
    base = {
        "latitude": "48.4", "longitude": "2.7", "acq_date": "2026-07-15",
        "acq_time": "1200", "satellite": "Terra", "instrument": "MODIS",
    }
    expected = (("29", "low"), ("30", "nominal"), ("79", "nominal"), ("80", "high"))
    for confidence, certainty in expected:
        record, _, _ = firms._normalize_row(
            {**base, "confidence": confidence}, "MODIS_NRT", "2026-07-15T12:00:00Z"
        )
        assert record["certainty"] == certainty
        assert record["severity_source"] == f"confidence={confidence}"


def _daily_match(name="r_D+2_20260715110717_penbal_20260717CEST_000.geojson"):
    return aemet_warnings.DAILY_FILE_PATTERN.match(name)


def test_aemet_feature_zonder_severity_info_wordt_overgeslagen():
    feature = {"properties": {"COD_Z": "610401", "Nombre_zona": "Testzone"}, "geometry": None}
    record = aemet_warnings._normalize_feature(
        feature, _daily_match(), "f.geojson", "2026-07-15T12:00:00Z"
    )
    assert record is None


def test_aemet_tekstuele_severity_is_leidend():
    # Tekst zegt naranja terwijl het rangordeveld 2 is; meerdere fenomenen
    # per zone: het ernstigste woord wint.
    feature = {
        "properties": {
            "Nivel_ATTA": "2",
            "Av_mayor": 2,
            "COD_Z": "733004",
            "Nombre_zona": "Valle del Testejo",
            "N_avisos": "2",
            "Avis_ATTA": "[{'severity': 'Naranja', 'descripcion': 'Temperatura máxima: 40 ºC'}]",
            "Avis_TOTO": "[{'severity': 'Amarillo', 'descripcion': 'Tormentas'}]",
        },
        "geometry": {"type": "Polygon", "coordinates": [[[0, 40], [1, 40], [1, 41], [0, 40]]]},
    }
    record = aemet_warnings._normalize_feature(
        feature, _daily_match(), "f.geojson", "2026-07-15T12:00:00Z"
    )
    assert record["severity_source"] == "naranja"
    assert record["severity_normalized"] == 3
    assert record["certainty"] == "aviso"
    assert record["valid_from"] == "2026-07-17T00:00:00Z"
    assert "Temperatura máxima: 40 ºC" in record["source_attrs"]["phenomena"]
    # De ruwe stringified detailvelden komen niet integraal mee.
    assert "Avis_ATTA" not in str(record)


def test_aemet_numerieke_fallback_lager_is_ernstiger():
    # Zonder tekstuele severity: rangorde 1 = rojo (afgeleid), niet verde.
    feature = {
        "properties": {"Nivel_ATTA": "1", "COD_Z": "610401", "Nombre_zona": "Testzone"},
        "geometry": None,
    }
    record = aemet_warnings._normalize_feature(
        feature, _daily_match(), "f.geojson", "2026-07-15T12:00:00Z"
    )
    assert record["severity_source"] == "rojo"
    assert record["severity_normalized"] == 4
    assert record["certainty"] == "afgeleid_van_rangorde"


def test_cems_activatie_normaliseren():
    activation = {
        "code": "EMSR999",
        "name": "Wildfire in Testland",
        "category": "Wildfire",
        "centroid": "POINT (2.7075 48.4047)",
        "activationTime": "2026-07-13T10:00:00Z",
        "drmPhase": "Response",
        "closed": False,
        "n_products": 3,
    }
    record = cems_rapid_mapping._normalize(activation, "2026-07-15T12:00:00Z")
    assert record["kind"] == "confirmed_incident"
    assert record["certainty"] == "official_activation"
    assert record["geometry"]["coordinates"] == [2.7075, 48.4047]
    assert record["source_attrs"]["closed"] is False


def test_cems_categorie_filter():
    assert cems_rapid_mapping._is_fire({"code": "EMSR999", "category": "Wildfire"})
    assert not cems_rapid_mapping._is_fire({"code": "EMSR999", "category": "Flood"})
    assert not cems_rapid_mapping._is_fire({"code": "EMSN999", "category": "Wildfire"})


def test_aemet_d08_wordt_overgeslagen():
    assert aemet_danger._parse_name("down_20260718_peligro_p_D08.tif") is None


def test_cems_slaat_oude_gesloten_en_risk_mapping_activaties_over(monkeypatch):
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    activations = [
        {"code": "EMSR001", "category": "Wildfire", "activationTime": "2026-06-01T00:00:00Z", "closed": True, "centroid": "POINT (2 48)"},
        {"code": "EMSN002", "category": "Wildfire", "activationTime": "2026-07-17T00:00:00Z", "closed": False, "centroid": "POINT (2 48)"},
        {"code": "EMSR003", "category": "Wildfire", "activationTime": "2026-07-17T00:00:00Z", "closed": False, "centroid": "POINT (2 48)"},
    ]
    monkeypatch.setattr(cems_rapid_mapping, "utcnow", lambda: now)
    monkeypatch.setattr(
        cems_rapid_mapping, "http_get_json", lambda url: {"results": activations, "next": None}
    )
    result = cems_rapid_mapping.fetch()
    assert result.status == "ok"
    assert [record["source_id"] for record in result.records] == ["EMSR003"]


def test_cems_slaat_activatie_zonder_puntgeometrie_over():
    activation = {"code": "EMSR004", "category": "Wildfire", "centroid": "ongeldig"}
    assert cems_rapid_mapping._normalize(activation, "2026-07-18T12:00:00Z") is None


def test_meteo_forets_oude_publicatie_is_ok_stale(monkeypatch):
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    stamp = "2026-07-16T12:00:00Z"
    rows = "\n".join(
        f"{stamp};{number:02d};1;2;Departement {number:02d}" for number in range(1, 81)
    )
    dataset = {"resources": [{"format": "csv", "url": "fixture://meteo.csv"}]}
    monkeypatch.setattr(meteo_forets, "utcnow", lambda: now)
    monkeypatch.setattr(meteo_forets, "http_get_json", lambda url: dataset)
    monkeypatch.setattr(
        meteo_forets,
        "http_get",
        lambda url: ("date;num_dep;niveau_j1;niveau_j2;nom_dep\n" + rows).encode(),
    )
    result = meteo_forets.fetch()
    assert result.status == "ok_stale"
    assert result.notes == [
        "laatste publicatie is 2026-07-16T12:00:00Z; kaart geldt niet meer voor morgen"
    ]
