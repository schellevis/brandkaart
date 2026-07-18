"""Skelet voor de Canarische alert-toestandmachine; nog niet live geactiveerd."""
from __future__ import annotations
import re,unicodedata
from dataclasses import dataclass
from datetime import datetime,timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

ISLANDS=("El Hierro","La Palma","La Gomera","Tenerife","Gran Canaria","Fuerteventura","Lanzarote","La Graciosa")
STATUS_RANK={"prealerta":1,"alerta":2,"alerta maxima":3}
LOCAL_ZONE=ZoneInfo("Atlantic/Canary")

@dataclass(frozen=True)
class Event:
    effective_at: datetime; action: str; status: str; risk: str; islands: tuple[str,...]; territory_text: str

class TextParser(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):
        value=" ".join(data.split())
        if value:self.parts.append(value)

def _norm(value): return "".join(c for c in unicodedata.normalize("NFKD",value).casefold() if not unicodedata.combining(c))
def parse_events(source_html):
    parser=TextParser();parser.feed(source_html);text="\n".join(parser.parts); events=[]
    # Iedere fixture/live sectie begint met "A partir del dd/mm/yyyy Hora: hh:mm".
    chunks=re.split(r"(?=A partir del\s+\d{2}/\d{2}/\d{4}\s+Hora:\s*\d{1,2}:\d{2})",text,flags=re.I)
    for chunk in chunks:
        stamp=re.search(r"A partir del\s+(\d{2})/(\d{2})/(\d{4})\s+Hora:\s*(\d{1,2}):(\d{2})",chunk,re.I)
        normalized=_norm(chunk)
        if not stamp or "incend" not in normalized:continue
        action=next((a for a in ("finaliza","actualiza","declara") if a in normalized),None)
        status=next((s for s in ("alerta maxima","prealerta","alerta") if s in normalized),None)
        if not action or not status:continue
        islands=tuple(name for name in ISLANDS if _norm(name) in normalized)
        territory_match=re.search(r"(?:para|en)\s+(?:las islas de\s+)?(.+?)(?:\.|Observaciones|$)",chunk,re.I|re.S)
        territory=" ".join((territory_match.group(1) if territory_match else ", ".join(islands)).split())[:300]
        local=datetime(int(stamp.group(3)),int(stamp.group(2)),int(stamp.group(1)),int(stamp.group(4)),int(stamp.group(5)),tzinfo=LOCAL_ZONE)
        effective=local.astimezone(timezone.utc)
        events.append(Event(effective,action,status,"incendios forestales",islands,territory))
    return sorted(events,key=lambda e:e.effective_at)

def reduce_state(events):
    """Behoud staten per (risico, eiland, status), zodat finaliza alerta geen prealerta wist."""
    state={}
    for event in sorted(events,key=lambda e:e.effective_at):
        for island in event.islands:
            key=(event.risk,island,event.status)
            if event.action=="finaliza":state.pop(key,None)
            else:state[key]=event
    return state

def fetch():
    """Niet live: activering wacht op robuuste bronsectie-detectie en eilandasset."""
    from ..common import SourceResult
    return SourceResult(source="canarias_alerts",status="failed",attribution="Fuente: Gobierno de Canarias — Dirección General de Emergencias",source_url="https://www.gobiernodecanarias.org/emergencias/alertas/Alerta_vigente.html",error="adapter-skelet: live publicatie bewust niet geactiveerd",coverage={"countries":["ES"],"regions":["Canarische Eilanden"],"kind":"measure","publication_enabled":False,"spatial_precision":"heel eiland met letterlijke territoriale tekst"})
