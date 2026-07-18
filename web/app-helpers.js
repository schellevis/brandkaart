(function (root, factory) {
  const helpers = factory();
  if (typeof module === "object" && module.exports) module.exports = helpers;
  root.BrandkaartHelpers = helpers;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const calendarFormatter = new Intl.DateTimeFormat("en", {
    timeZone: "Europe/Amsterdam", year: "numeric", month: "2-digit", day: "2-digit",
  });

  function safeUrl(value) {
    const url = String(value ?? "");
    return /^https?:/i.test(url) ? url : "#";
  }

  function hasPointGeometry(feature) {
    const coordinates = feature?.geometry?.coordinates;
    return feature?.geometry?.type === "Point" && Array.isArray(coordinates)
      && coordinates.length >= 2 && coordinates.every(Number.isFinite);
  }

  function isClosedIncident(feature) {
    return feature?.properties?.source_attrs?.closed === true;
  }

  function currentIncidentFeatures(features) {
    return (features || []).filter(feature => hasPointGeometry(feature) && !isClosedIncident(feature));
  }

  function targetDateKey(dayOffset, now = new Date()) {
    const parts = Object.fromEntries(
      calendarFormatter.formatToParts(now).map(part => [part.type, part.value])
    );
    const target = new Date(Date.UTC(
      Number(parts.year), Number(parts.month) - 1,
      Number(parts.day) + Number(dayOffset || 0)
    ));
    return target.toISOString().slice(0, 10);
  }

  function dangerValidOnDay(feature, dayOffset, now = new Date()) {
    const props = feature?.properties || {};
    const start = Date.parse(props.valid_from || "");
    const end = Date.parse(props.valid_to || "");
    if (Number.isFinite(start) || Number.isFinite(end)) {
      const representative = Number.isFinite(start) && Number.isFinite(end)
        ? start + (end - start) / 2
        : Number.isFinite(start) ? start : end;
      return new Date(representative).toISOString().slice(0, 10)
        === targetDateKey(dayOffset, now);
    }
    return Number(props.source_attrs?.day_offset) === Number(dayOffset);
  }

  function rasterPixel(meta, lat, lon) {
    const bounds = meta?.bounds;
    if (!bounds || lon < bounds.west || lon > bounds.east
      || lat < bounds.south || lat > bounds.north) return null;
    const xRatio = (lon - bounds.west) / (bounds.east - bounds.west);
    let yRatio = (bounds.north - lat) / (bounds.north - bounds.south);
    if (meta.crs === "EPSG:3857") {
      const mercatorY = value => Math.log(Math.tan(Math.PI / 4 + value * Math.PI / 360));
      yRatio = (mercatorY(bounds.north) - mercatorY(lat))
        / (mercatorY(bounds.north) - mercatorY(bounds.south));
    }
    return {
      x: Math.min(meta.width - 1, Math.max(0, Math.floor(xRatio * meta.width))),
      y: Math.min(meta.height - 1, Math.max(0, Math.floor(yRatio * meta.height))),
    };
  }

  return {
    currentIncidentFeatures,
    dangerValidOnDay,
    hasPointGeometry,
    isClosedIncident,
    rasterPixel,
    safeUrl,
    targetDateKey,
  };
});
