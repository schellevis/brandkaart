"""Departementsgeometrie: vereenvoudiging en koppeling (geen netwerk)."""

from pathlib import Path

from pipeline.geometry import ASSET_PATH, attach_geometry, load_departements, simplify_geometry


def _square_ring(step: float = 0.0001) -> list[list[float]]:
    """Een vierkante ring met een extra, bijna-collineair tussenpunt.

    Het tussenpunt op de onderrand ligt vrijwel op de lijn tussen de twee
    hoekpunten en moet door Douglas-Peucker worden weggelaten bij een
    tolerantie die groter is dan `step`.
    """
    return [
        [0.0, 0.0],
        [0.5, step],  # bijna-collineair tussenpunt, ruim binnen tolerantie
        [1.0, 0.0],
        [1.0, 1.0],
        [0.0, 1.0],
        [0.0, 0.0],
    ]


def test_simplify_polygon_ring_blijft_gesloten():
    geometry = {"type": "Polygon", "coordinates": [_square_ring()]}
    result = simplify_geometry(geometry, tolerance=0.01)
    ring = result["coordinates"][0]
    assert ring[0] == ring[-1]
    assert len(ring) >= 4


def test_simplify_vermindert_puntenaantal():
    geometry = {"type": "Polygon", "coordinates": [_square_ring()]}
    original_points = len(geometry["coordinates"][0])
    result = simplify_geometry(geometry, tolerance=0.01)
    simplified_points = len(result["coordinates"][0])
    assert simplified_points < original_points


def test_simplify_rondt_coordinaten_af():
    geometry = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.23456789, 0.0], [1.0, 1.0], [0.0, 0.0]]]}
    result = simplify_geometry(geometry, tolerance=0.0)
    for x, y in result["coordinates"][0]:
        assert round(x, 3) == x
        assert round(y, 3) == y


def test_simplify_degenererende_ring_vervalt():
    # Een bijna-rechte "ring" met een minimale uitwijking valt bij een grove
    # tolerantie terug op 2 punten en moet dus geheel vervallen (< 4 punten).
    ring = [[0.0, 0.0], [0.5, 0.001], [1.0, 0.0], [0.0, 0.0]]
    geometry = {"type": "Polygon", "coordinates": [ring]}
    result = simplify_geometry(geometry, tolerance=1.0)
    assert result["coordinates"] == []


def test_simplify_polygon_zonder_buitenring_vervalt():
    # De buitenring ontaardt bij een zeer grove tolerantie; het gat
    # (tweede ring) mag de polygon dan niet in leven houden.
    outer = [[0.0, 0.0], [0.5, 0.001], [1.0, 0.0], [0.0, 0.0]]
    hole = [[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.4], [0.2, 0.2]]
    geometry = {"type": "Polygon", "coordinates": [outer, hole]}
    result = simplify_geometry(geometry, tolerance=1.0)
    assert result["coordinates"] == []


def test_simplify_multipolygon():
    square_a = [_square_ring()]
    square_b = [[[2.0, 2.0], [2.5, 2.0 + 0.0001], [3.0, 2.0], [3.0, 3.0], [2.0, 3.0], [2.0, 2.0]]]
    geometry = {"type": "MultiPolygon", "coordinates": [square_a, square_b]}
    result = simplify_geometry(geometry, tolerance=0.01)
    assert result["type"] == "MultiPolygon"
    assert len(result["coordinates"]) == 2
    for polygon in result["coordinates"]:
        outer_ring = polygon[0]
        assert outer_ring[0] == outer_ring[-1]
        assert len(outer_ring) >= 4


def _synthetic_record(num_dep: str | None) -> dict:
    record = {
        "id": f"test-{num_dep}",
        "kind": "danger",
        "geometry": None,
        "source_attrs": {"num_dep": num_dep} if num_dep is not None else {},
    }
    return record


def test_attach_geometry_koppelt_bekende_departementen():
    departements = {
        "01": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        "2A": {"type": "Polygon", "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 2]]]},
    }
    records = [_synthetic_record("01"), _synthetic_record("2A"), _synthetic_record("99")]
    matched, unmatched = attach_geometry(records, departements)
    assert matched == 2
    assert unmatched == 1
    assert records[0]["geometry"] == departements["01"]
    assert records[1]["geometry"] == departements["2A"]
    assert records[2]["geometry"] is None


def test_attach_geometry_verwijdert_records_nooit():
    departements = {"01": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
    records = [_synthetic_record("01"), _synthetic_record(None), _synthetic_record("77")]
    matched, unmatched = attach_geometry(records, departements)
    assert matched == 1
    assert unmatched == 2
    assert len(records) == 3


def test_asset_bevat_alle_departementen():
    if not Path(ASSET_PATH).exists():
        return  # asset wordt niet in elke omgeving meegeleverd/gegenereerd
    departements = load_departements(ASSET_PATH)
    assert len(departements) == 96
    for code in ("2A", "2B", "13"):
        assert code in departements
        assert departements[code]["type"] in ("Polygon", "MultiPolygon")
