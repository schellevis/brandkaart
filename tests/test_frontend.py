"""Netwerkloze regressietests voor de browserhulplogica."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_frontend_helpers_met_node():
    result = subprocess.run(
        ["node", "--test", "tests/frontend_helpers.test.js"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_vectorlagen_worden_voor_hertekenen_geleegd():
    source = (ROOT / "web/app.js").read_text("utf-8")
    render = source[source.index("function renderVectors()") : source.index("async function renderRaster()")]
    assert render.index("layers.incidents.clearLayers()") < render.index("incidents.forEach")
    assert render.index("layers.warnings.clearLayers()") < render.index("layers.warnings.addData")


def test_renderfout_wordt_niet_als_ontbrekend_manifest_gemeld():
    source = (ROOT / "web/app.js").read_text("utf-8")
    assert source.count("DEMO — geen datamanifest beschikbaar") == 1
    assert "Live manifest geladen, maar de kaartweergave is niet volledig beschikbaar" in source
