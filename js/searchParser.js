// Lightweight parser for boolean/field search.
// Supports:
//   "exact phrase"           -> Fuse phrase match
//   agency:nypd              -> agency filter, AND
//   tag:permits              -> tag filter, AND
//   type:map                 -> view-type filter
//   cat:"public safety"      -> category filter
//   updated:30d  updated:1y  -> freshness pill
//   -tag:historical          -> negation
// Produces: { fuseQuery: string|null, filters: {agencies:[], tags:[], types:[], cats:[], notTags:[], notCats:[], notAgencies:[]}, freshness: 'all'|'30'|'365'|'stale' }

window.NYC_PARSE_QUERY = function parseQuery(input) {
  const filters = { agencies: [], tags: [], types: [], cats: [], notTags: [], notCats: [], notAgencies: [], notTypes: [] };
  let freshness = null;
  if (!input) return { fuseQuery: "", filters, freshness };

  // Tokenize: respect quoted phrases and field:value pairs (with optional leading minus)
  const tokens = [];
  const re = /-?\w+:"[^"]+"|-?\w+:\S+|"[^"]+"|\S+/g;
  let m;
  while ((m = re.exec(input)) !== null) tokens.push(m[0]);

  const terms = [];
  for (const tok of tokens) {
    let neg = false;
    let t = tok;
    if (t.startsWith("-")) { neg = true; t = t.slice(1); }
    const colon = t.indexOf(":");
    if (colon > 0 && /^[a-zA-Z]+$/.test(t.slice(0, colon))) {
      const field = t.slice(0, colon).toLowerCase();
      let value = t.slice(colon + 1);
      if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1);
      value = value.trim();
      if (!value) continue;
      const val = value.toLowerCase();
      if (field === "agency") (neg ? filters.notAgencies : filters.agencies).push(val);
      else if (field === "tag") (neg ? filters.notTags : filters.tags).push(val);
      else if (field === "type") (neg ? filters.notTypes : filters.types).push(val);
      else if (field === "cat" || field === "category") (neg ? filters.notCats : filters.cats).push(val);
      else if (field === "updated") {
        if (val === "30d" || val === "month") freshness = "30";
        else if (val === "1y" || val === "year") freshness = "365";
        else if (val === "old" || val === "stale") freshness = "stale";
      } else {
        // unknown field — fall through to plain term
        terms.push(tok);
      }
    } else {
      terms.push(tok);
    }
  }

  return { fuseQuery: terms.join(" ").trim(), filters, freshness };
};

// Apply parsed filters to a list of dataset records (catalog.min.json shape).
window.NYC_APPLY_FILTERS = function applyFilters(list, f) {
  if (!f) return list;
  return list.filter((d) => {
    if (f.agencies.length && !f.agencies.some((a) => (d.a || "").toLowerCase().includes(a))) return false;
    if (f.notAgencies.length && f.notAgencies.some((a) => (d.a || "").toLowerCase().includes(a))) return false;
    if (f.types.length && !f.types.includes((d.t || "").toLowerCase())) return false;
    if (f.notTypes.length && f.notTypes.includes((d.t || "").toLowerCase())) return false;
    if (f.cats.length && !f.cats.some((c) => (d.c || "").toLowerCase().includes(c))) return false;
    if (f.notCats.length && f.notCats.some((c) => (d.c || "").toLowerCase().includes(c))) return false;
    const tagsLower = (d.g || []).map((t) => (t || "").toLowerCase());
    if (f.tags.length && !f.tags.every((t) => tagsLower.some((dt) => dt.includes(t)))) return false;
    if (f.notTags.length && f.notTags.some((t) => tagsLower.some((dt) => dt.includes(t)))) return false;
    return true;
  });
};
