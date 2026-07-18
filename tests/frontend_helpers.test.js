"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  currentIncidentFeatures,
  dangerValidOnDay,
  hasPointGeometry,
  safeUrl,
  targetDateKey,
} = require("../web/app-helpers.js");

function feature(validFrom, validTo, dayOffset = 99) {
  return { properties: {
    valid_from: validFrom,
    valid_to: validTo,
    source_attrs: { day_offset: dayOffset },
  } };
}

test("gevaarselectie volgt geldigheidsdatum, ook voor overmorgen en lokale middernacht", () => {
  const now = new Date(2026, 6, 18, 12, 0, 0);
  assert.equal(dangerValidOnDay(
    feature("2026-07-20T00:00:00Z", "2026-07-20T23:59:59Z", 1), 2, now
  ), true);
  assert.equal(dangerValidOnDay(
    feature("2026-07-19T00:00:00Z", "2026-07-19T23:59:59Z", 2), 2, now
  ), false);
  assert.equal(dangerValidOnDay(
    feature("2026-07-19T22:00:00Z", "2026-07-20T21:59:59Z", 0), 2, now
  ), true);
});

test("day_offset is alleen fallback wanneer geldigheidstijden ontbreken", () => {
  const now = new Date(2026, 6, 18, 12, 0, 0);
  assert.equal(dangerValidOnDay(feature(null, null, 2), 2, now), true);
  assert.equal(dangerValidOnDay(feature(null, null, 1), 2, now), false);
});

test("gekozen kalenderdag volgt de Nederlandse interfacetijdzone", () => {
  assert.equal(targetDateKey(0, new Date("2026-07-17T22:30:00Z")), "2026-07-18");
  assert.equal(targetDateKey(2, new Date("2026-07-17T22:30:00Z")), "2026-07-20");
});

test("incidenten zonder geometrie en gesloten incidenten zijn niet actueel", () => {
  const open = { geometry: { type: "Point", coordinates: [2, 48] }, properties: { source_attrs: { closed: false } } };
  const closed = { geometry: { type: "Point", coordinates: [3, 49] }, properties: { source_attrs: { closed: true } } };
  const missing = { geometry: null, properties: { source_attrs: { closed: false } } };
  assert.equal(hasPointGeometry(missing), false);
  assert.deepEqual(currentIncidentFeatures([open, closed, missing]), [open]);
});

test("alleen http- en https-links blijven klikbaar", () => {
  assert.equal(safeUrl("https://example.test/bron"), "https://example.test/bron");
  assert.equal(safeUrl("HTTP://example.test/bron"), "HTTP://example.test/bron");
  assert.equal(safeUrl("javascript:alert(1)"), "#");
  assert.equal(safeUrl("data:text/html,misbruik"), "#");
});
