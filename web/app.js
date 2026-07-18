"use strict";

const state = { manifest: null, data: {}, places: [], hours: 24, day: 0, selected: null, raster: [], rasterSample: [] };
const sourceNames = { firms: "NASA FIRMS", meteo_forets: "Météo des forêts", aemet_warnings: "AEMET-waarschuwingen", aemet_danger: "AEMET-brandgevaar", effis_danger: "EFFIS Europees brandgevaar", cems_rapid_mapping: "CEMS Rapid Mapping", pla_alfa: "Pla Alfa (Catalonië)", galicia_irdi: "IRDI (Galicië)", meteoalarm_nl: "MeteoAlarm (NL)", meteoalarm_be: "MeteoAlarm (BE)", meteoalarm_lu: "MeteoAlarm (LU)", meteoalarm_de: "MeteoAlarm (DE)", meteoalarm_at: "MeteoAlarm (AT)", meteoalarm_ch: "MeteoAlarm (CH)", meteoalarm_it: "MeteoAlarm (IT)", meteoalarm_fr: "MeteoAlarm (FR)" };
const statusLabels = { ok: "actueel", ok_stale: "verouderd", stale_reused: "oude geldige data hergebruikt", failed: "bron niet bereikbaar", skipped_no_key: "overgeslagen: sleutel ontbreekt" };
const countryNames = new Intl.DisplayNames(["nl"], { type: "region" });
const fmt = new Intl.DateTimeFormat("nl-NL", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Amsterdam" });
const map = L.map("map", { zoomControl: false, minZoom: 3, preferCanvas: true }).setView([43.2, 1.5], 5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap-bijdragers" }).addTo(map);

const layers = {
  detections: L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 45, showCoverageOnHover: false }),
  incidents: L.layerGroup(), warnings: L.geoJSON(null), dangerEffis: L.layerGroup(), dangerFr: L.geoJSON(null), dangerEs: L.layerGroup(), dangerRegional: L.geoJSON(null)
};
const layerGroups = { danger: ["dangerEffis","dangerFr","dangerEs","dangerRegional"] };
Object.values(layers).forEach(layer => layer.addTo(map));

async function fetchGzipJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  if (!window.DecompressionStream) throw new Error("Deze browser ondersteunt geen gzip-decompressie. Gebruik een actuele browser.");
  const stream = response.body.pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(stream).text());
}

const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const dateText = value => value ? fmt.format(new Date(value)) : "niet opgegeven";
const severityColor = value => ({ 1: "#5c9c63", 2: "#d8b321", 3: "#e5811b", 4: "#c52e22" })[Number(value)] || "#748078";
const warningColor = word => ({ amarillo: "#d8b321", naranja: "#e5811b", rojo: "#c52e22" })[String(word).toLowerCase()] || "#748078";
const dangerLabel = n => ({ 1: "Laag", 2: "Matig", 3: "Hoog", 4: "Zeer hoog" })[Number(n)] || "Onbekend";
const { currentIncidentFeatures, dangerValidOnDay, hasPointGeometry, isClosedIncident, rasterPixel, safeUrl } = BrandkaartHelpers;

function popup(props, type) {
  const sourceTime = props.observed_at || props.issued_at || props.valid_from;
  return `<strong>${esc(type)}</strong><br>${esc(props.area_text || props.severity_source || "")}${props.severity_source ? `<br><small>Bronniveau: ${esc(props.severity_source)}</small>` : ""}<br><small>Brontijd: ${esc(dateText(sourceTime))}<br>Opgehaald: ${esc(dateText(props.fetched_at))}</small><br><a href="${esc(safeUrl(props.source_url))}" target="_blank" rel="noopener">Open bron ↗</a>`;
}

const FLAME = '<svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M13.2 1.8c.4 3-1.5 4.7-3.3 6.7-1.9 2.2-3.5 4.4-3.5 7.5a5.6 5.6 0 0 0 11.2 0c0-3.2-1.7-5.9-4.9-8.4.1 2.1-.5 3.8-2 5.1.2-3.7-.5-6.8 2.5-10.9Zm.1 11.9c.2 1.7-.6 2.9-1.6 4-.6.7-1.1 1.4-1.1 2.3a2.4 2.4 0 0 0 4.8 0c0-1.3-.7-2.5-2.2-3.7.1-.9.1-1.7.1-2.6Z"/></svg>';
function detectionIcon() { return L.divIcon({ className: "hotspot-marker", html: "<span></span>", iconSize: [13,13], iconAnchor: [7,7] }); }
function incidentIcon() { return L.divIcon({ className: "incident-marker", html: FLAME, iconSize: [30,30], iconAnchor: [15,15] }); }

function renderDetections() {
  layers.detections.clearLayers();
  const cutoff = Date.now() - state.hours * 3600000;
  const features = (state.data.detections?.features || []).filter(f => hasPointGeometry(f) && new Date(f.properties.observed_at).getTime() >= cutoff);
  for (const feature of features) {
    const [lon, lat] = feature.geometry.coordinates;
    L.marker([lat, lon], { icon: detectionIcon(), keyboard: true, title: "Satellietdetectie — niet bevestigd" }).bindPopup(popup(feature.properties, "Satellietdetectie — niet bevestigd")).addTo(layers.detections);
  }
  document.getElementById("count-detections").textContent = features.length.toLocaleString("nl-NL");
}

function renderVectors() {
  layers.incidents.clearLayers();
  const incidents = (state.data.incidents?.features || []).filter(hasPointGeometry);
  incidents.forEach(feature => { const [lon, lat] = feature.geometry.coordinates, historical = isClosedIncident(feature), label = historical ? "Historische CEMS-activatie (gesloten)" : "Bevestigd incident (CEMS-activatie)"; L.marker([lat, lon], { icon: incidentIcon(), keyboard: true, title: label }).bindPopup(popup(feature.properties, label)).addTo(layers.incidents); });
  document.getElementById("count-incidents").textContent = currentIncidentFeatures(incidents).length;
  const warnings = (state.data.warnings?.features || []).filter(f => !f.properties.valid_to || new Date(f.properties.valid_to) >= new Date());
  layers.warnings.clearLayers();
  layers.warnings.addData({ type: "FeatureCollection", features: warnings });
  layers.warnings.setStyle(f => ({ color: severityColor(f.properties.severity_normalized), fillColor: severityColor(f.properties.severity_normalized), weight: 2, fillOpacity: .18, dashArray: "6 4" }));
  layers.warnings.eachLayer(layer => layer.bindPopup(popup(layer.feature.properties, "Officiële waarschuwing ◇")));
  document.getElementById("count-warnings").textContent = warnings.length;
  const dangers = (state.data.dangerFr?.features || []).filter(f => dangerValidOnDay(f, state.day));
  layers.dangerFr.clearLayers().addData({ type: "FeatureCollection", features: dangers });
  layers.dangerFr.setStyle(f => ({ color: severityColor(f.properties.severity_normalized), fillColor: severityColor(f.properties.severity_normalized), weight: 1, fillOpacity: .27 }));
  layers.dangerFr.eachLayer(layer => layer.bindPopup(popup(layer.feature.properties, "Brandgevaar — modelberekening")));
  const regional = [...(state.data.plaAlfa?.features || []), ...(state.data.galiciaIrdi?.features || [])].filter(f => dangerValidOnDay(f, state.day));
  layers.dangerRegional.clearLayers().addData({ type: "FeatureCollection", features: regional });
  layers.dangerRegional.setStyle(f => ({ color: severityColor(Math.min(4, f.properties.severity_normalized)), fillColor: severityColor(Math.min(4, f.properties.severity_normalized)), weight: 1, fillOpacity: .3 }));
  layers.dangerRegional.eachLayer(layer => layer.bindPopup(popup(layer.feature.properties, "Regionaal brandgevaar — officiële index")));
}

async function renderRaster() {
  layers.dangerEs.clearLayers();
  const index = state.data.dangerEs?.features || [];
  const entries = index.filter(f => dangerValidOnDay(f, state.day) && ["p", "c"].includes(f.properties.source_attrs?.area));
  for (const entry of entries) {
    try {
      await loadRasterEntry(entry,layers.dangerEs,.55,`AEMET-brandgevaar ${entry.properties.area_text}`,true);
    } catch (error) { console.warn("Raster kon niet worden geladen", error); }
  }
  if (!document.querySelector('[data-layer="danger"]').checked) map.removeLayer(layers.dangerEs);
}

async function renderEffisRaster() {
  layers.dangerEffis.clearLayers(); state.rasterSample = [];
  const entry = (state.data.dangerEffis?.features || []).find(f => dangerValidOnDay(f, state.day));
  if (entry) {
    try { await loadRasterEntry(entry,layers.dangerEffis,.42,"EFFIS Europees brandgevaar",false); }
    catch (error) { console.warn("EFFIS-raster kon niet worden geladen",error); }
  }
  if (!document.querySelector('[data-layer="danger"]').checked) map.removeLayer(layers.dangerEffis);
}

async function loadRasterEntry(entry,layer,opacity,alt,prioritize) {
  const meta=await fetchGzipJson(`data/${entry.properties.source_attrs.meta}.gz`),b=meta.bounds,imagePath=`data/${entry.properties.source_attrs.png}`;
  const overlay=L.imageOverlay(imagePath,[[b.south,b.west],[b.north,b.east]],{opacity,alt,interactive:false}).addTo(layer);if(!prioritize)overlay.bringToBack();
  const image=new Image();image.src=imagePath;await image.decode();
  const canvas=document.createElement("canvas");canvas.width=meta.width;canvas.height=meta.height;
  const context=canvas.getContext("2d",{willReadFrequently:true});context.drawImage(image,0,0);
  const sample={meta,context,entry};if(prioritize)state.rasterSample.unshift(sample);else state.rasterSample.push(sample);
}

function pointInRing(lon, lat, ring) { let inside = false; for (let i=0,j=ring.length-1;i<ring.length;j=i++) { const xi=ring[i][0], yi=ring[i][1], xj=ring[j][0], yj=ring[j][1]; if (((yi>lat)!==(yj>lat)) && lon < (xj-xi)*(lat-yi)/(yj-yi)+xi) inside=!inside; } return inside; }
function pointInGeometry(lon, lat, geometry) { if (!geometry) return false; const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : []; return polygons.some(poly => pointInRing(lon,lat,poly[0]) && !poly.slice(1).some(ring => pointInRing(lon,lat,ring))); }
function haversine(lat1,lon1,lat2,lon2) { const r=6371, dLat=(lat2-lat1)*Math.PI/180, dLon=(lon2-lon1)*Math.PI/180; const a=Math.sin(dLat/2)**2+Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2; return 2*r*Math.asin(Math.sqrt(a)); }
function sampleRaster(lat,lon) { for (const sample of state.rasterSample) { const position=rasterPixel(sample.meta,lat,lon);if(!position)continue;const pixel=sample.context.getImageData(position.x,position.y,1,1).data; if (!pixel[3]) continue; let best=null, delta=Infinity; for (const [id,def] of Object.entries(sample.meta.classes)) { const rgb=def.color.match(/[a-f\d]{2}/gi).map(v=>parseInt(v,16)); const d=Math.abs(pixel[0]-rgb[0])+Math.abs(pixel[1]-rgb[1])+Math.abs(pixel[2]-rgb[2]); if(d<delta){delta=d;best={id:Number(id),provider:sample.meta.provider||sample.entry.properties.authority,...def};} } return best; } return null; }

function analyzeLocation() {
  if (!state.selected) return;
  const { lat, lon, name, subtitle } = state.selected, radius = Number(document.getElementById("radius").value);
  const detections=(state.data.detections?.features||[]).filter(hasPointGeometry).map(f=>({f,d:haversine(lat,lon,f.geometry.coordinates[1],f.geometry.coordinates[0])})).filter(x=>x.d<=radius&&new Date(x.f.properties.observed_at)>=new Date(Date.now()-state.hours*3600000)).sort((a,b)=>a.d-b.d);
  const incidents=currentIncidentFeatures(state.data.incidents?.features||[]).map(f=>({f,d:haversine(lat,lon,f.geometry.coordinates[1],f.geometry.coordinates[0])})).filter(x=>x.d<=radius).sort((a,b)=>a.d-b.d);
  const warnings=(state.data.warnings?.features||[]).filter(f=>pointInGeometry(lon,lat,f.geometry)&&(!f.properties.valid_to||new Date(f.properties.valid_to)>=new Date()));
  const dangerFr=(state.data.dangerFr?.features||[]).filter(f=>dangerValidOnDay(f,state.day)&&pointInGeometry(lon,lat,f.geometry));
  const dangerRegional=[...(state.data.plaAlfa?.features||[]),...(state.data.galiciaIrdi?.features||[])].filter(f=>dangerValidOnDay(f,state.day)&&pointInGeometry(lon,lat,f.geometry));
  const dangerRaster=sampleRaster(lat,lon), highestFr=dangerFr.sort((a,b)=>b.properties.severity_normalized-a.properties.severity_normalized)[0], highestRegional=dangerRegional.sort((a,b)=>b.properties.severity_normalized-a.properties.severity_normalized)[0];
  const dangerText=highestRegional?highestRegional.properties.severity_source:highestFr?dangerLabel(highestFr.properties.severity_normalized):dangerRaster?dangerRaster.label:"Geen aangesloten gevaarlaag op deze locatie";
  let summary = `${dangerText !== "Geen aangesloten gevaarlaag op deze locatie" ? `${dangerText} brandgevaar volgens de aangesloten modelbron. ` : ""}`;
  if (detections.length) summary += `Er ${detections.length===1?"is":"zijn"} ${detections.length} recente satellietdetectie${detections.length===1?"":"s"} binnen ${radius} km, maar geen daarvan wordt op basis van satellietdata als natuurbrand bevestigd. `;
  if (incidents.length) summary += `${incidents.length} bevestigde CEMS-activatie${incidents.length===1?" ligt":"s liggen"} binnen ${radius} km. `;
  if (warnings.length) summary += `${warnings.length} officiële waarschuwing${warnings.length===1?" geldt":"en gelden"} voor deze locatie. `;
  if (!detections.length&&!incidents.length&&!warnings.length) summary += "Geen actuele meldingen gevonden in de aangesloten bronnen. Dit betekent niet dat er geen gevaar is.";
  document.getElementById("location-title").textContent=name; document.getElementById("location-subtitle").textContent=`${subtitle} · zoekstraal ${radius} km`;
  document.getElementById("summary-title").textContent=(warnings.length||incidents.length||detections.length)?"Actuele informatie gevonden":"Geen actuele meldingen gevonden";
  document.getElementById("plain-summary").textContent=summary;
  document.getElementById("danger-summary").innerHTML=highestRegional?card("Regionaal brandgevaar",`${esc(highestRegional.properties.severity_source)} · ${esc(highestRegional.properties.authority)}<br>Geldig: ${esc(dateText(highestRegional.properties.valid_from))} – ${esc(dateText(highestRegional.properties.valid_to))}`):highestFr?card("Brandgevaar",`${esc(dangerLabel(highestFr.properties.severity_normalized))} · bronniveau: ${esc(highestFr.properties.severity_source)}<br>Geldig: ${esc(dateText(highestFr.properties.valid_from))} – ${esc(dateText(highestFr.properties.valid_to))}`):dangerRaster?card("Brandgevaar",`${esc(dangerRaster.label)} · ${esc(dangerRaster.provider)} rasterklasse ${dangerRaster.id}<br>Pixelwaarde uit officiële gevaarkaart`):'<div class="empty-card">Geen gevaargegevens voor deze locatie en dag.</div>';
  document.getElementById("warning-summary").innerHTML=warnings.length?warningCards(warnings):'<div class="empty-card">Geen actuele officiële waarschuwing gevonden voor dit punt.</div>';
  const nearby=[...incidents.slice(0,5).map(x=>nearbyCard(x,"incident")),...detections.slice(0,8).map(x=>nearbyCard(x,"detection"))]; document.getElementById("nearby-summary").innerHTML=nearby.join("")||'<div class="empty-card">Geen recente detecties of bevestigde incidenten binnen de gekozen straal.</div>';
  document.getElementById("detail-panel").hidden=false;document.body.classList.add("panel-open");
}
function card(title,body){return `<div class="forecast-item"><strong>${title}</strong>${body}</div>`;}
function warningCards(features){return features.sort((a,b)=>b.properties.severity_normalized-a.properties.severity_normalized).map(f=>`<div class="result-card"><strong>◇ ${esc(f.properties.severity_source)} — ${esc(f.properties.area_text)}</strong>${esc(f.properties.source_attrs?.awareness_type||f.properties.source_attrs?.phenomena?.join(" ")||"Officiële waarschuwing")}<br><small>Uitgegeven ${esc(dateText(f.properties.issued_at))} · geldig tot ${esc(dateText(f.properties.valid_to))} · opgehaald ${esc(dateText(f.properties.fetched_at))}</small><br><a href="${esc(safeUrl(f.properties.source_url))}" target="_blank" rel="noopener">${esc(f.properties.attribution||"Bron")} ↗</a></div>`).join("");}
function nearbyCard(x,type){const p=x.f.properties,mark=type==="incident"?`<span class="ico-fire">${FLAME}</span> Bevestigd incident: ${esc(p.area_text)}`:"● Satellietdetectie — niet bevestigd";return `<div class="result-card ${type}"><strong>${mark}</strong>${x.d.toFixed(1)} km afstand<br><small>Brontijd ${esc(dateText(p.observed_at||p.issued_at))} · opgehaald ${esc(dateText(p.fetched_at))}</small><br><a href="${esc(safeUrl(p.source_url))}" target="_blank" rel="noopener">Bron ↗</a></div>`;}

const detailPanel=document.getElementById("detail-panel"),panelExpand=document.getElementById("panel-expand"),panelExpandLabel=document.getElementById("panel-expand-label"),panelExpandIcon=document.getElementById("panel-expand-icon");
function setPanelExpanded(expanded){detailPanel.classList.toggle("expanded",expanded);document.body.classList.toggle("panel-expanded",expanded);panelExpand.setAttribute("aria-expanded",String(expanded));panelExpandLabel.textContent=expanded?"Invouwen":"Details";panelExpandIcon.textContent=expanded?"↓":"↑";}
panelExpand.onclick=()=>setPanelExpanded(!detailPanel.classList.contains("expanded"));

let searchMarker; const searchIcon=L.divIcon({className:"search-pin",iconSize:[23,23],iconAnchor:[4,21]});
function selectLocation(lat,lon,name,subtitle="Aangeklikte kaartlocatie") { state.selected={lat,lon,name,subtitle}; if(searchMarker)map.removeLayer(searchMarker); searchMarker=L.marker([lat,lon],{icon:searchIcon,keyboard:true,title:name}).addTo(map); map.flyTo([lat,lon],Math.max(map.getZoom(),8)); if(window.matchMedia("(max-width:650px)").matches)setPanelExpanded(false); analyzeLocation(); }
function parseCoordinates(value){const match=value.trim().match(/^(-?\d{1,2}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)$/);if(!match)return null;const lat=Number(match[1]),lon=Number(match[2]);return Math.abs(lat)<=90&&Math.abs(lon)<=180?{lat,lon}:null;}
function searchPlaces(query){const q=query.trim().toLocaleLowerCase("nl");if(!q)return[];return state.places.filter(p=>`${p[0]} ${p[1]}`.toLocaleLowerCase("nl").includes(q)).slice(0,8);}
function renderSearch(){const input=document.getElementById("location-search"),box=document.getElementById("search-results"),coords=parseCoordinates(input.value),matches=searchPlaces(input.value);let html=coords?`<button class="search-result" data-coords="${coords.lat},${coords.lon}" role="option"><strong>Coördinaten ${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)}</strong><small>Direct op de kaart</small></button>`:"";html+=matches.map((p,i)=>`<button class="search-result" data-index="${i}" role="option"><strong>${esc(p[0])}</strong><small>${esc(countryNames.of(p[1])||p[1])} · ${Number(p[4]||0).toLocaleString("nl-NL")} inwoners</small></button>`).join("");box.innerHTML=html;box.hidden=!html;input.setAttribute("aria-expanded",html?"true":"false");box.querySelectorAll("button").forEach(button=>button.onclick=()=>{if(button.dataset.coords){const [lat,lon]=button.dataset.coords.split(",").map(Number);selectLocation(lat,lon,"Gekozen coördinaten");}else{const p=matches[Number(button.dataset.index)];selectLocation(Number(p[2]),Number(p[3]),p[0],countryNames.of(p[1])||p[1]);}box.hidden=true;input.setAttribute("aria-expanded","false");});}

function renderSources() { const target=document.getElementById("source-status"); target.innerHTML=Object.entries(state.manifest.sources).map(([key,s])=>{const stale=["ok_stale","stale_reused"].includes(s.status),bad=["failed","skipped_no_key"].includes(s.status);return `<div class="source-row"><strong>${esc(sourceNames[key]||key)}</strong><span class="status-pill ${bad?"status-bad":stale?"status-stale":"status-ok"}">${esc(statusLabels[s.status]||s.status)}</span><span>Brontijd: ${esc(dateText(s.source_updated_at))}</span><span>Opgehaald: ${esc(dateText(s.last_attempt_at))} · laatste succes: ${esc(dateText(s.last_success_at))}</span><span>Geldig tot: ${esc(dateText(s.valid_until))} · ${Number(s.record_count||0).toLocaleString("nl-NL")} records</span>${s.error?`<span>Fout: ${esc(s.error)}</span>`:""}<a href="${esc(safeUrl(s.source_url))}" target="_blank" rel="noopener">${esc(s.attribution)} ↗</a></div>`;}).join(""); }

async function load() {
  const banner=document.getElementById("data-banner");
  try {
    const response=await fetch("data/manifest.json",{cache:"no-cache"}); if(!response.ok)throw new Error(`manifest HTTP ${response.status}`); state.manifest=await response.json();
  } catch(error) { banner.textContent="DEMO — geen datamanifest beschikbaar; de kaart bevat geen fictieve meldingen";banner.className="data-banner demo";console.error(error);return; }
  try {
    const s=state.manifest.sources;
    const jobs=[['detections',s.firms],['incidents',s.cems_rapid_mapping],['dangerEffis',s.effis_danger],['dangerFr',s.meteo_forets],['dangerEs',s.aemet_danger],['plaAlfa',s.pla_alfa],['galiciaIrdi',s.galicia_irdi]].map(async([key,source])=>{if(!source?.file)return;try{state.data[key]=await fetchGzipJson(`data/${source.file}`);}catch(error){console.warn(key,error);}});
    // Alle waarschuwingsbronnen (AEMET + MeteoAlarm-landen) samenvoegen tot één laag
    state.data.warnings={type:"FeatureCollection",features:[]};
    const warnKeys=Object.keys(s).filter(k=>k==="aemet_warnings"||k.startsWith("meteoalarm_"));
    jobs.push(...warnKeys.map(async k=>{const src=s[k];if(!src?.file)return;try{const fc=await fetchGzipJson(`data/${src.file}`);state.data.warnings.features.push(...(fc.features||[]));}catch(error){console.warn(k,error);}}));
    jobs.push(fetchGzipJson("data/places.eu.json.gz").then(data=>state.places=data.places||[]).catch(error=>console.warn("Plaatsnamen niet beschikbaar",error)));
    await Promise.all(jobs); renderDetections(); renderVectors(); await renderEffisRaster(); await renderRaster(); renderSources();
    const troubled=Object.values(s).filter(x=>x.status!=="ok"); banner.textContent=`Live gegevens · gebouwd ${dateText(state.manifest.built_at)}${troubled.length?` · ${troubled.length} bron${troubled.length===1?"":"nen"} vertraagd of niet beschikbaar`:""}`; banner.className=`data-banner${troubled.length?" warning":""}`;
  } catch(error) { banner.textContent="Live manifest geladen, maar de kaartweergave is niet volledig beschikbaar";banner.className="data-banner warning";console.error(error); }
}

document.querySelectorAll("[data-layer]").forEach(input=>input.addEventListener("change",()=>{const names=layerGroups[input.dataset.layer]||[input.dataset.layer];names.forEach(name=>input.checked?layers[name].addTo(map):map.removeLayer(layers[name]));}));
document.querySelectorAll("[data-hours]").forEach(button=>button.onclick=()=>{state.hours=Number(button.dataset.hours);document.querySelectorAll("[data-hours]").forEach(b=>{b.classList.toggle("active",b===button);b.setAttribute("aria-pressed",b===button);});renderDetections();analyzeLocation();});
document.querySelectorAll("[data-day]").forEach(button=>button.onclick=async()=>{state.day=Number(button.dataset.day);document.querySelectorAll("[data-day]").forEach(b=>{b.classList.toggle("active",b===button);b.setAttribute("aria-pressed",b===button);});document.getElementById("danger-day-label").textContent=`D+${state.day}`;renderVectors();await renderEffisRaster();await renderRaster();analyzeLocation();});
document.getElementById("radius").onchange=analyzeLocation;document.getElementById("zoom-in").onclick=()=>map.zoomIn();document.getElementById("zoom-out").onclick=()=>map.zoomOut();
const layerCard=document.querySelector(".layer-card"),collapseBtn=document.getElementById("collapse-layers");
function setLayersCollapsed(collapsed){layerCard.classList.toggle("collapsed",collapsed);layerCard.querySelectorAll(".layer-toggle").forEach(x=>x.hidden=collapsed);collapseBtn.textContent=collapsed?"+":"−";collapseBtn.setAttribute("aria-expanded",String(!collapsed));collapseBtn.setAttribute("aria-label",collapsed?"Kaartlagen uitklappen":"Kaartlagen inklappen");}
collapseBtn.onclick=()=>setLayersCollapsed(!layerCard.classList.contains("collapsed"));
if(window.matchMedia("(max-width:650px)").matches)setLayersCollapsed(true);
document.getElementById("panel-close").onclick=()=>{detailPanel.hidden=true;document.body.classList.remove("panel-open");setPanelExpanded(false);};
const search=document.getElementById("location-search"),results=document.getElementById("search-results");search.oninput=renderSearch;search.onfocus=renderSearch;search.onkeydown=event=>{if(event.key==="Enter")results.querySelector("button")?.click();if(event.key==="Escape")results.hidden=true;};document.addEventListener("click",event=>{if(!event.target.closest(".search-shell"))results.hidden=true;});document.addEventListener("keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="k"){event.preventDefault();search.focus();}});
document.getElementById("locate-button").onclick=()=>navigator.geolocation?navigator.geolocation.getCurrentPosition(p=>selectLocation(p.coords.latitude,p.coords.longitude,"Jouw locatie","Browserlocatie · blijft lokaal"),()=>alert("Locatie kon niet worden gebruikt. Controleer de browsertoestemming."),{enableHighAccuracy:false,timeout:10000}):alert("Deze browser ondersteunt geen locatiebepaling.");
map.on("click",event=>selectLocation(event.latlng.lat,event.latlng.lng,"Gekozen kaartlocatie"));
const dialog=document.getElementById("sources-dialog");document.getElementById("sources-open").onclick=()=>dialog.showModal();document.getElementById("sources-close").onclick=()=>dialog.close();
const welcomeDialog=document.getElementById("welcome-dialog"), welcomeKey="brandkaart-experimenteel-akkoord-v1";
let welcomeSeen=false;
try { welcomeSeen=localStorage.getItem(welcomeKey)==="1"; } catch(error) { console.warn("localStorage niet beschikbaar",error); }
if(!welcomeSeen) welcomeDialog.showModal();
document.getElementById("welcome-ok").onclick=()=>{try{localStorage.setItem(welcomeKey,"1");}catch(error){console.warn("Voorkeur kon niet worden opgeslagen",error);}welcomeDialog.close();};
load();
