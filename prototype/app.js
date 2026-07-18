/* Interactive concept only: every incident, warning and risk area below is dummy data. */

const places = [
  { name: "Collioure", region: "Pyrénées-Orientales · Frankrijk", lat: 42.525, lon: 3.083, zoom: 10, level: "Hoog" },
  { name: "Marseille", region: "Bouches-du-Rhône · Frankrijk", lat: 43.296, lon: 5.369, zoom: 9, level: "Zeer hoog" },
  { name: "Bordeaux", region: "Gironde · Frankrijk", lat: 44.838, lon: -0.579, zoom: 9, level: "Matig" },
  { name: "Girona", region: "Catalonië · Spanje", lat: 41.979, lon: 2.821, zoom: 10, level: "Hoog" },
  { name: "Valencia", region: "Comunitat Valenciana · Spanje", lat: 39.47, lon: -0.376, zoom: 9, level: "Zeer hoog" },
  { name: "Málaga", region: "Andalusië · Spanje", lat: 36.721, lon: -4.421, zoom: 9, level: "Hoog" },
  { name: "Faro", region: "Algarve · Portugal", lat: 37.019, lon: -7.93, zoom: 9, level: "Hoog" },
  { name: "Athene", region: "Attica · Griekenland", lat: 37.984, lon: 23.728, zoom: 9, level: "Zeer hoog" }
];

const map = L.map("map", { zoomControl: false, attributionControl: false, minZoom: 4 }).setView([43.7, 1.2], 6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "© OpenStreetMap"
}).addTo(map);

const layers = {
  risk: L.layerGroup().addTo(map),
  detections: L.layerGroup().addTo(map),
  warnings: L.layerGroup().addTo(map),
  closures: L.layerGroup().addTo(map)
};

const riskZones = [
  { center: [42.55, 2.55], radius: 78000, color: "#e85732", label: "Hoog brandgevaar · dummy" },
  { center: [40.05, -0.55], radius: 105000, color: "#e85732", label: "Zeer hoog brandgevaar · dummy" },
  { center: [37.15, -4.1], radius: 95000, color: "#f3a52e", label: "Hoog brandgevaar · dummy" },
  { center: [43.25, 5.45], radius: 72000, color: "#d9472d", label: "Zeer hoog brandgevaar · dummy" },
  { center: [44.35, -0.5], radius: 85000, color: "#f3ca46", label: "Matig brandgevaar · dummy" }
];
riskZones.forEach(zone => {
  L.circle(zone.center, {
    radius: zone.radius,
    color: zone.color,
    weight: 1,
    fillColor: zone.color,
    fillOpacity: .16
  }).bindTooltip(zone.label).addTo(layers.risk);
});

const hotspotIcon = L.divIcon({ className: "dummy-hotspot", html: "<span></span>", iconSize: [14,14], iconAnchor: [7,7] });
[
  [42.46, 2.95], [42.40, 3.18], [43.19, 5.61], [39.71, -0.72],
  [36.88, -4.16], [37.21, -7.61], [38.10, 23.45]
].forEach((point, index) => {
  L.marker(point, { icon: hotspotIcon })
    .bindPopup(`<strong>Satellietdetectie</strong><br><small>Dummy · VIIRS · ${28 + index * 11} minuten geleden<br>Niet lokaal bevestigd</small>`)
    .on("click", () => openNearbyLocation(point))
    .addTo(layers.detections);
});

const warningIcon = L.divIcon({ className: "dummy-warning", html: "<span>!</span>", iconSize: [25,25], iconAnchor: [12,12] });
[
  { point: [42.63, 2.88], text: "Hittewaarschuwing · geel" },
  { point: [43.42, 5.25], text: "Brandgevaarwaarschuwing · oranje" },
  { point: [39.55, -0.45], text: "Waarschuwing hoge temperatuur · oranje" },
  { point: [37.05, -4.52], text: "Waarschuwing wind en hitte · geel" }
].forEach(item => L.marker(item.point, { icon: warningIcon }).bindPopup(`<strong>${item.text}</strong><br><small>Officiële waarschuwing · dummy-data</small>`).addTo(layers.warnings));

const closureIcon = L.divIcon({ className: "dummy-closure", html: "×", iconSize: [27,27], iconAnchor: [13,13] });
[
  { point: [42.50, 3.02], text: "Toegang bosmassief beperkt" },
  { point: [43.25, 5.72], text: "Natuurgebied tijdelijk gesloten" }
].forEach(item => L.marker(item.point, { icon: closureIcon }).bindPopup(`<strong>${item.text}</strong><br><small>Officiële maatregel · dummy-data</small>`).addTo(layers.closures));

let searchMarker;
const searchIcon = L.divIcon({ className: "search-pin", iconSize: [24,24], iconAnchor: [4,22] });
const input = document.getElementById("location-search");
const results = document.getElementById("search-results");

function renderResults(query = "") {
  const matches = places.filter(place => `${place.name} ${place.region}`.toLowerCase().includes(query.toLowerCase())).slice(0, 6);
  results.innerHTML = matches.map((place, index) => `
    <button class="search-result" type="button" data-place="${places.indexOf(place)}">
      <span>⌖</span><span><strong>${place.name}</strong><small>${place.region}</small></span>
    </button>`).join("");
  results.hidden = matches.length === 0;
  results.querySelectorAll("button").forEach(button => button.addEventListener("click", () => selectPlace(places[Number(button.dataset.place)])));
}

function showPanel() {
  document.querySelector(".detail-panel").style.display = "block";
}

function selectPlace(place, animate = true) {
  input.value = place.name;
  results.hidden = true;
  if (animate) map.flyTo([place.lat, place.lon], place.zoom, { duration: 1.1 });
  else map.setView([place.lat, place.lon], place.zoom, { animate: false });
  if (searchMarker) map.removeLayer(searchMarker);
  searchMarker = L.marker([place.lat, place.lon], { icon: searchIcon }).addTo(map);
  showPanel();
  updatePanel(place);
}

function updatePanel(place) {
  document.getElementById("location-title").textContent = place.name;
  document.getElementById("location-subtitle").textContent = place.region;
  document.getElementById("summary-title").textContent = place.level === "Matig" ? "Blijf alert" : "Extra opletten";
  document.querySelector(".status-label").textContent = place.level;
  document.getElementById("plain-summary").textContent = `${place.level} brandgevaar volgens fictieve modeldata. Controleer officiële lokale berichten voordat je een natuurgebied bezoekt.`;
  document.querySelector(".detail-panel").scrollTo({ top: 0, behavior: "smooth" });
}

function openNearbyLocation(point) {
  const nearest = places.reduce((best, place) => {
    const distance = Math.hypot(place.lat - point[0], place.lon - point[1]);
    return !best || distance < best.distance ? { place, distance } : best;
  }, null);
  showPanel();
  updatePanel(nearest.place);
}

input.addEventListener("focus", () => renderResults(input.value));
input.addEventListener("input", () => renderResults(input.value));
input.addEventListener("keydown", event => {
  if (event.key === "Enter") {
    const first = places.find(place => `${place.name} ${place.region}`.toLowerCase().includes(input.value.toLowerCase()));
    if (first) selectPlace(first);
  }
  if (event.key === "Escape") results.hidden = true;
});
document.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    input.focus();
  }
});
document.addEventListener("click", event => {
  if (!event.target.closest(".search-shell")) results.hidden = true;
});

document.querySelectorAll("[data-layer]").forEach(toggle => {
  toggle.addEventListener("change", () => {
    const layer = layers[toggle.dataset.layer];
    if (toggle.checked) layer.addTo(map); else map.removeLayer(layer);
  });
});

document.querySelectorAll(".time-tabs button").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".time-tabs button").forEach(item => {
      item.classList.toggle("active", item === button);
      item.setAttribute("aria-selected", item === button ? "true" : "false");
    });
  });
});

document.getElementById("zoom-in").addEventListener("click", () => map.zoomIn());
document.getElementById("zoom-out").addEventListener("click", () => map.zoomOut());
document.getElementById("locate-button").addEventListener("click", () => {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(position => {
    const place = { name: "Jouw locatie", region: "Browserlocatie · alleen lokaal gebruikt", lat: position.coords.latitude, lon: position.coords.longitude, zoom: 11, level: "Onbekend" };
    selectPlace(place);
  });
});

document.querySelector(".collapse-button").addEventListener("click", event => {
  const card = document.querySelector(".layer-card");
  const labels = card.querySelectorAll(".layer-toggle");
  const collapsed = card.classList.toggle("collapsed");
  labels.forEach(label => label.hidden = collapsed);
  event.currentTarget.textContent = collapsed ? "+" : "−";
});

document.querySelector(".panel-close").addEventListener("click", () => {
  document.querySelector(".detail-panel").style.display = "none";
});

map.on("click", () => {
  document.querySelector(".detail-panel").style.display = "block";
});

selectPlace(places[0], false);
window.addEventListener("load", () => map.invalidateSize());
