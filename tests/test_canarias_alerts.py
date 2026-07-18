from pipeline.adapters.canarias_alerts import parse_events,reduce_state

FIXTURE="""
<section><h3>A partir del 01/07/2026 Hora: 08:00</h3><p>DECLARA la situación de Prealerta por Riesgo de Incendios Forestales para las islas de Tenerife y Gran Canaria.</p></section>
<section><h3>A partir del 02/07/2026 Hora: 08:00</h3><p>DECLARA la situación de Alerta por Riesgo de Incendios Forestales para Tenerife, en medianías y cumbres del sur y oeste.</p></section>
<section><h3>A partir del 03/07/2026 Hora: 12:00</h3><p>ACTUALIZA la situación de Alerta por Riesgo de Incendios Forestales para Tenerife, solo por encima de 400 metros.</p></section>
<section><h3>A partir del 04/07/2026 Hora: 20:00</h3><p>FINALIZA la situación de Alerta por Riesgo de Incendios Forestales para Tenerife.</p></section>
"""

def test_parser_bewaart_letterlijk_territorium():
    events=parse_events(FIXTURE); assert len(events)==4; assert "400 metros" in events[2].territory_text; assert events[0].effective_at.isoformat()=="2026-07-01T07:00:00+00:00"

def test_finaliza_alerta_laat_prealerta_staan():
    state=reduce_state(parse_events(FIXTURE)); assert ("incendios forestales","Tenerife","alerta") not in state; assert ("incendios forestales","Tenerife","prealerta") in state; assert ("incendios forestales","Gran Canaria","prealerta") in state

def test_wintertijd_canarias_is_utc():
    fixture="<p>A partir del 01/01/2026 Hora: 08:00 DECLARA la situación de Alerta por Riesgo de Incendios Forestales para Tenerife.</p>"
    assert parse_events(fixture)[0].effective_at.isoformat()=="2026-01-01T08:00:00+00:00"
