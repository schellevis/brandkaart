import ssl
from pipeline.adapters import galicia_irdi

def _fragment(offset=0,count=313):
    levels=["Baixo","Moderado","Alto","Moi Alto","Extremo"]
    return "<table class='table-irdi-table'>"+"".join(f"<tr><td class='views-field-field-zona'>Concello {i}</td><td class='views-field-field-p50'>{levels[(i+offset)%5]}</td></tr>" for i in range(count))+"</table>"

def test_html_parser_vijf_niveaus():
    assert galicia_irdi._parse_rows(_fragment(count=5))==[("Concello 0","Baixo"),("Concello 1","Moderado"),("Concello 2","Alto"),("Concello 3","Moi Alto"),("Concello 4","Extremo")]

def test_fetch_vier_dagen_met_geometrie(monkeypatch):
    page="<p>Actualizado o  Xoves, 16 de Xullo de 2026 ás 09:48</p>"
    monkeypatch.setattr(galicia_irdi,"_request",lambda *args,**kwargs:page.encode())
    monkeypatch.setattr(galicia_irdi,"_post_view",lambda day,page: _fragment(int(day[-1]),313) if page==0 else "")
    geometry={"type":"Polygon","coordinates":[[[-8,42],[-7,42],[-7,43],[-8,42]]]}
    monkeypatch.setattr(galicia_irdi,"load",lambda:{f"Concello {i}":(f"{i:05d}",geometry) for i in range(313)})
    result=galicia_irdi.fetch(); assert result.status=="ok"; assert len(result.records)==1252; assert result.records[-1]["source_attrs"]["day_offset"]==3

def test_onvolledige_tabel_is_storing(monkeypatch):
    monkeypatch.setattr(galicia_irdi,"_request",lambda *a,**k:"<p>Actualizado o Xoves, 16 de Xullo de 2026 ás 09:48</p>".encode())
    monkeypatch.setattr(galicia_irdi,"_post_view",lambda *a:_fragment(count=20))
    geometry={"type":"Polygon","coordinates":[[[-8,42],[-7,42],[-7,43],[-8,42]]]}
    monkeypatch.setattr(galicia_irdi,"load",lambda:{f"Concello {i}":(f"{i:05d}",geometry) for i in range(313)})
    result=galicia_irdi.fetch(); assert result.status=="failed"; assert "verwacht 313" in result.error

def test_tls_blijft_verificatie_en_hostname_controleren():
    context=galicia_irdi._context(); assert context.verify_mode==ssl.CERT_REQUIRED; assert context.check_hostname is True

def test_actualiseringstijd_zomer_en_winter_naar_utc():
    summer=galicia_irdi._updated_at("Actualizado o Xoves, 16 de Xullo de 2026 ás 09:48")
    winter=galicia_irdi._updated_at("Actualizado o Xoves, 16 de Xaneiro de 2026 ás 09:48")
    assert summer.isoformat()=="2026-07-16T07:48:00+00:00"
    assert winter.isoformat()=="2026-01-16T08:48:00+00:00"
