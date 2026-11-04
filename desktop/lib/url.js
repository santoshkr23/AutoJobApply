"use strict";
// Pure helpers (unit tested) deciding which URLs the app may load.
function normalizeServerUrl(input) {
  let u;
  try { u = new URL(String(input).trim()); } catch { return null; }
  if (u.protocol !== "https:" && !(u.protocol === "http:" && ["localhost", "127.0.0.1"].includes(u.hostname))) return null;
  u.hash = ""; u.search = "";
  return u.origin;
}
function isInternal(url, serverOrigin) {
  try { return new URL(url).origin === serverOrigin; } catch { return false; }
}
module.exports = { normalizeServerUrl, isInternal };
