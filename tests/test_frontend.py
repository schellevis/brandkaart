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


def test_locatieknop_gebruikt_een_schaalbaar_navigatieicoon():
    html = (ROOT / "web/index.html").read_text("utf-8")
    styles = (ROOT / "web/styles.css").read_text("utf-8")
    assert 'class="location-icon"' in html
    assert "◎" not in html
    assert 'aria-label="Gebruik mijn huidige locatie"' in html
    assert ".location-button{flex:none;font-size:0;gap:0;justify-content:center" in styles


def test_locatiedetails_beginnen_op_mobiel_ingevouwen_en_kunnen_fullscreen():
    html = (ROOT / "web/index.html").read_text("utf-8")
    source = (ROOT / "web/app.js").read_text("utf-8")
    styles = (ROOT / "web/styles.css").read_text("utf-8")
    assert 'id="panel-expand"' in html
    assert 'aria-expanded="false"' in html
    assert 'class="detail-content"' in html
    assert 'setPanelExpanded(false); analyzeLocation()' in source
    assert 'detailPanel.classList.toggle("expanded",expanded)' in source
    assert ".detail-panel:not(.expanded) .detail-content{display:none}" in styles
    assert ".detail-panel:not(.expanded)>.eyebrow,.detail-panel:not(.expanded)>p{display:none}" in styles
    assert "body.panel-open .time-control{display:none}" in styles
    assert ".detail-panel.expanded{border-radius:0" in styles
    assert "position:fixed" in styles[styles.index(".detail-panel.expanded") :]


def test_meteoalarm_landstatus_staat_in_bronnendialoog_niet_in_lagenpaneel():
    html = (ROOT / "web/index.html").read_text("utf-8")
    source = (ROOT / "web/app.js").read_text("utf-8")
    layers = html[html.index('<section class="layer-card') : html.index("</section>")]
    sources = html[html.index('<dialog id="sources-dialog"') :]
    assert "Details per land" not in layers
    assert 'id="warning-source-detail"' not in html
    assert "Waarschuwingen per land" not in sources
    assert 'id="source-status"' in sources
    for country_code in ("NL", "BE", "LU", "DE", "AT", "CH", "IT", "FR"):
        assert f'"MeteoAlarm ({country_code})"' in source
    assert "renderSources();" in source


def test_brandgevaar_is_een_gegroepeerde_laagschakelaar():
    html = (ROOT / "web/index.html").read_text("utf-8")
    source = (ROOT / "web/app.js").read_text("utf-8")
    assert 'data-layer="danger"' in html
    assert 'data-layer="dangerFr"' not in html
    assert 'data-layer="dangerEs"' not in html
    assert 'data-layer="dangerRegional"' not in html
    assert 'danger: ["dangerEffis","dangerFr","dangerEs","dangerRegional"]' in source


def test_effis_is_basisraster_en_lokale_rasters_krijgen_voorrang():
    html = (ROOT / "web/index.html").read_text("utf-8")
    source = (ROOT / "web/app.js").read_text("utf-8")
    assert "geharmoniseerd EFFIS-brandgevaar" in html
    assert "renderEffisRaster(); await renderRaster()" in source
    assert "if(!prioritize)overlay.bringToBack()" in source
    assert "if(prioritize)state.rasterSample.unshift(sample)" in source
    assert "effis_danger: \"EFFIS Europees brandgevaar\"" in source


def test_satellietdetecties_tonen_standaard_de_laatste_24_uur():
    html = (ROOT / "web/index.html").read_text("utf-8")
    source = (ROOT / "web/app.js").read_text("utf-8")
    assert "hours: 24" in source
    assert '<button data-hours="1" aria-pressed="false">Nu</button>' in html
    assert '<button data-hours="24" class="active" aria-pressed="true">24 uur</button>' in html
