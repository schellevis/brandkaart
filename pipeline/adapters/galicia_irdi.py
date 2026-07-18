"""Xunta IRDI: 313 gemeenten, vandaag plus drie dagen, uit Drupal Views."""
from __future__ import annotations
import json,re,ssl,unicodedata,urllib.parse,urllib.request
from datetime import datetime,time,timedelta,timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
from ..common import SourceResult,iso,utcnow,USER_AGENT
from ..galicia_geometry import load
from ..schema import make_record

PAGE_URL="https://mediorural.xunta.gal/gl/temas/defensa-monte/irdi"
VIEWS_URL="https://mediorural.xunta.gal/gl/views/ajax"
ATTRIBUTION="Fonte: Xunta de Galicia — Consellería do Medio Rural (IRDI)"
INTERMEDIATE=Path(__file__).resolve().parents[2]/"assets"/"certs"/"globalsign-rsa-ov-ssl-ca-2018.pem"
LEVELS={"baixo":1,"moderado":2,"alto":3,"moi alto":4,"extremo":5}
MONTHS={"xaneiro":1,"febreiro":2,"marzo":3,"abril":4,"maio":5,"xuño":6,"xullo":7,"agosto":8,"setembro":9,"outubro":10,"novembro":11,"decembro":12}
MIN_ROWS=313
LOCAL_ZONE=ZoneInfo("Europe/Madrid")
MUNICIPALITY_ALIASES={"alfoz":"alfoz do castrodouro","cangas":"cangas de morrazo","castro caldelas":"castro de caldelas"}

class TableParser(HTMLParser):
    def __init__(self): super().__init__(); self.cell=None; self.buf=[]; self.rows=[]; self.current=[]
    def handle_starttag(self,tag,attrs):
        classes=dict(attrs).get("class","")
        if tag=="td" and ("views-field-field-zona" in classes or "views-field-field-p50" in classes): self.cell="name" if "field-zona" in classes else "level"; self.buf=[]
    def handle_data(self,data):
        if self.cell:self.buf.append(data)
    def handle_endtag(self,tag):
        if tag=="td" and self.cell:
            self.current.append(" ".join("".join(self.buf).split())); self.cell=None
            if len(self.current)==2:self.rows.append(tuple(self.current));self.current=[]

def _context():
    context=ssl.create_default_context(); context.load_verify_locations(cafile=str(INTERMEDIATE)); return context
def _request(url,data=None):
    request=urllib.request.Request(url,data=data,headers={"User-Agent":USER_AGENT,"Content-Type":"application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request,timeout=60,context=_context()) as response:return response.read()
def _post_view(day,page):
    data=urllib.parse.urlencode({"view_name":"tabla_irdi","view_display_id":"block_1","view_args":day}).encode(); response=json.loads(_request(f"{VIEWS_URL}?page={page}",data))
    for item in response:
        if isinstance(item,dict) and isinstance(item.get("data"),str) and "table-irdi-table" in item["data"]: return item["data"]
    raise ValueError("Drupal Views-response mist IRDI-tabel")
def _parse_rows(fragment): parser=TableParser();parser.feed(fragment);return parser.rows
def _norm(value):return "".join(c for c in unicodedata.normalize("NFKD",value).casefold() if not unicodedata.combining(c)).strip()
def _municipality_key(value):
    """Normaliseer ook officiële `Arnoia, A` versus IRDI `A Arnoia`."""
    value=_norm(value).replace("'"," "); parts=[p.strip() for p in value.split(",",1)]
    if len(parts)==2 and parts[1] in {"a","o","as","os"}: value=f"{parts[1]} {parts[0]}"
    value=re.sub(r"[^a-z0-9]+"," ",value).strip()
    value=re.sub(r"^(?:a|o|as|os)\s+","",value)
    return MUNICIPALITY_ALIASES.get(value,value)
def _updated_at(page):
    match=re.search(r"Actualizado\s+o\s+\w+,\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+ás\s+(\d{1,2}):(\d{2})",page,re.I)
    if not match or _norm(match.group(2)) not in MONTHS: raise ValueError("actualiseringstijd niet gevonden")
    local=datetime(int(match.group(3)),MONTHS[_norm(match.group(2))],int(match.group(1)),int(match.group(4)),int(match.group(5)),tzinfo=LOCAL_ZONE)
    return local.astimezone(timezone.utc)

def fetch():
    result=SourceResult(source="galicia_irdi",attribution=ATTRIBUTION,source_url=PAGE_URL,coverage={"countries":["ES"],"regions":["Galicië"],"municipalities_expected":313,"days":[0,1,2,3],"kind":"danger","complete_within_region":True})
    try:
        page=_request(PAGE_URL).decode("utf-8"); updated=_updated_at(page); local_day=updated.astimezone(LOCAL_ZONE).date(); geometries=load(); geom_norm={_municipality_key(k):v for k,v in geometries.items()}; records=[]; fetched=iso(utcnow())
        if len(geom_norm)!=313: raise ValueError("gemeente-normalisatie levert geen 313 unieke geometrieën")
        for offset in range(4):
            rows=[]
            for page_no in range(10):
                batch=_parse_rows(_post_view(f"dia_{offset+1}",page_no))
                if not batch:break
                rows.extend(batch)
                if len(batch)<50:break
            unique={_municipality_key(name):(name,level) for name,level in rows}
            if len(unique)!=MIN_ROWS: raise ValueError(f"dia_{offset+1}: {len(unique)} gemeenten, verwacht 313")
            target=local_day+timedelta(days=offset)
            for key,(name,level_word) in unique.items():
                level=LEVELS.get(_norm(level_word)); joined=geom_norm.get(key)
                if level is None or joined is None:raise ValueError(f"onbekend niveau of gemeente: {name} / {level_word}")
                code,geometry=joined; records.append(make_record(id=f"irdi-{target.isoformat()}-{code}",source_id=code,kind="danger",authority="Xunta de Galicia — Consellería do Medio Rural",source_url=PAGE_URL,geometry=geometry,area_text=name,severity_source=level_word,severity_normalized=level,certainty="official_danger_index",issued_at=iso(updated),valid_from=iso(datetime.combine(target,time.min,tzinfo=LOCAL_ZONE)),valid_to=iso(datetime.combine(target,time.max,tzinfo=LOCAL_ZONE)),fetched_at=fetched,expires_policy="hide_after_valid_to",attribution=ATTRIBUTION,raw_payload_ref=f"galicia_irdi:d{offset}:{code}",source_attrs={"municipality_code":code,"day_offset":offset}))
    except Exception as exc:return result.fail(f"IRDI schema/plausibiliteit: {exc}")
    result.records=records;result.source_updated_at=iso(updated);result.valid_until=iso(datetime.combine(local_day+timedelta(days=3),time.max,tzinfo=LOCAL_ZONE));result.status="ok";return result
