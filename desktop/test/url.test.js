const test = require("node:test");
const assert = require("node:assert");
const { normalizeServerUrl, isInternal } = require("../lib/url");
test("accepts https and localhost http only", () => {
  assert.equal(normalizeServerUrl("https://app.example.com/x?y=1"), "https://app.example.com");
  assert.equal(normalizeServerUrl("http://localhost:3000/"), "http://localhost:3000");
  assert.equal(normalizeServerUrl("http://evil.example.com"), null);
  assert.equal(normalizeServerUrl("file:///etc/passwd"), null);
  assert.equal(normalizeServerUrl("javascript:alert(1)"), null);
  assert.equal(normalizeServerUrl("not a url"), null);
});
test("isInternal compares origins", () => {
  assert.ok(isInternal("https://a.com/p", "https://a.com"));
  assert.ok(!isInternal("https://a.com.evil.com/", "https://a.com"));
  assert.ok(!isInternal("garbage", "https://a.com"));
});
