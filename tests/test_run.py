import json

from pipeline import run
from pipeline.adapters import meteoalarm_warnings


def test_meteoalarm_onverwachte_fout_breekt_run_niet(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "ADAPTERS", ())
    monkeypatch.setattr(
        run.meteoalarm_geometry,
        "load_zone_asset",
        lambda *args: (_ for _ in ()).throw(ValueError("synthetisch corrupt asset")),
    )
    monkeypatch.setattr(
        meteoalarm_warnings,
        "fetch_all",
        lambda *args: (_ for _ in ()).throw(ValueError("synthetische landfout")),
    )
    output = tmp_path / "data"
    assert run.main(["--output", str(output)]) == 0
    manifest = json.loads((output / "manifest.json").read_text("utf-8"))
    assert set(manifest["sources"]) == {
        f"meteoalarm_{country}" for country in meteoalarm_warnings.COUNTRIES
    }
    assert all(entry["status"] == "failed" for entry in manifest["sources"].values())
