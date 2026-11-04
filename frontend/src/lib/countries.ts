// Lets people type "Japan" or "jp" instead of memorising ISO codes.
const NAMES: Record<string, string> = {
  india: "IN", "united states": "US", usa: "US", america: "US", "united kingdom": "GB", uk: "GB", england: "GB", britain: "GB",
  japan: "JP", canada: "CA", australia: "AU", germany: "DE", france: "FR", singapore: "SG", "united arab emirates": "AE", uae: "AE",
  netherlands: "NL", ireland: "IE", spain: "ES", italy: "IT", sweden: "SE", switzerland: "CH", "new zealand": "NZ", china: "CN",
  "south korea": "KR", korea: "KR", brazil: "BR", mexico: "MX", "south africa": "ZA", poland: "PL", portugal: "PT", qatar: "QA",
  "saudi arabia": "SA", malaysia: "MY", indonesia: "ID", philippines: "PH", thailand: "TH", vietnam: "VN", "hong kong": "HK",
  norway: "NO", denmark: "DK", finland: "FI", belgium: "BE", austria: "AT", israel: "IL", turkey: "TR", egypt: "EG", nigeria: "NG",
};

/** "Japan" -> "JP", "jp" -> "JP". Returns null when the text is not recognised. */
export function toCountryCode(text: string): string | null {
  const t = text.trim().toLowerCase();
  if (!t) return null;
  if (NAMES[t]) return NAMES[t];
  if (/^[a-z]{2}$/.test(t)) return t.toUpperCase();
  return null;
}

export function parseCountries(text: string): { codes: string[]; unknown: string[] } {
  const codes: string[] = []; const unknown: string[] = [];
  for (const part of text.split(/[,;\n]/)) {
    if (!part.trim()) continue;
    const c = toCountryCode(part);
    if (!c) unknown.push(part.trim()); else if (!codes.includes(c)) codes.push(c);
  }
  return { codes, unknown };
}
