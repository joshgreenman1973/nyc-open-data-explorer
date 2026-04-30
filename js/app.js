(() => {
  const els = {
    q: document.getElementById("q"),
    sort: document.getElementById("sort"),
    fresh: document.getElementById("freshness"),
    clear: document.getElementById("clear"),
    stats: document.getElementById("stats"),
    catMap: document.getElementById("cat-map"),
    results: document.getElementById("results"),
    empty: document.getElementById("empty"),
    activeChips: document.getElementById("active-chips"),
    typePills: document.getElementById("type-pills"),
    agencyList: document.getElementById("agency-list"),
    agencySearch: document.getElementById("agency-search"),
    agencyToggle: document.getElementById("agency-toggle"),
    agencyCount: document.getElementById("agency-count"),
    tagCloud: document.getElementById("tag-cloud"),
    picksOnly: document.getElementById("picks-only"),
    freshStrip: document.getElementById("fresh-strip"),
    freshNew: document.getElementById("fresh-new"),
    freshUpdated: document.getElementById("fresh-updated"),
  };

  const state = {
    catalog: null,
    fuse: null,
    picksById: new Map(),
    activeCat: null,
    activeAgencies: new Set(),
    activeType: null,         // single-select for the pill row
    activeTags: new Set(),
    excludedTags: new Set(),
    picksOnly: false,
    query: "",
    parsed: { fuseQuery: "", filters: null, freshness: null },
    sort: "relevance",
    fresh: "all",
    fetchedAt: null,
    showAllAgencies: false,
    agencyFilter: "",
  };

  const SIZE_RULES = [
    { min: 500, klass: "size-xl" },
    { min: 200, klass: "size-l" },
  ];
  const AGENCY_INITIAL = 12;
  const RENDER_CAP = 200;

  function tileSize(count) {
    for (const r of SIZE_RULES) if (count >= r.min) return r.klass;
    return "";
  }

  function fmtNum(n) {
    if (n == null) return "0";
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
    return String(n);
  }

  function freshnessClass(updatedISO) {
    if (!updatedISO) return { klass: "stale", label: "No date" };
    const t = Date.parse(updatedISO);
    if (Number.isNaN(t)) return { klass: "stale", label: "No date" };
    const days = (Date.now() - t) / 86400000;
    if (days <= 30) return { klass: "fresh", label: "Updated " + Math.max(1, Math.round(days)) + "d ago" };
    if (days <= 365) return { klass: "recent", label: "Updated " + Math.round(days / 30) + " mo ago" };
    const yrs = Math.floor(days / 365);
    return { klass: "stale", label: "Updated " + yrs + "y+ ago" };
  }

  function relativeDate(iso) {
    if (!iso) return "";
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "";
    const days = Math.max(0, Math.round((Date.now() - t) / 86400000));
    if (days < 1) return "today";
    if (days < 2) return "yesterday";
    if (days < 14) return days + " days ago";
    if (days < 60) return Math.round(days / 7) + " weeks ago";
    if (days < 365) return Math.round(days / 30) + " months ago";
    return Math.round(days / 365) + " years ago";
  }

  function passesFreshness(d) {
    const f = state.parsed.freshness || state.fresh;
    if (f === "all" || !f) return true;
    if (!d.u) return f === "stale";
    const days = (Date.now() - Date.parse(d.u)) / 86400000;
    if (f === "30") return days <= 30;
    if (f === "365") return days <= 365;
    if (f === "stale") return days > 365;
    return true;
  }

  function escapeHTML(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[m]));
  }
  function escapeAttr(s) { return escapeHTML(s); }

  // ---------- Category map ----------
  function renderCatMap() {
    const cats = state.catalog.categories;
    els.catMap.innerHTML = cats.map((c) => {
      const sz = tileSize(c.count);
      const active = state.activeCat === c.name ? " active" : "";
      const desc = (window.NYC_CAT_DESC && window.NYC_CAT_DESC[c.name]) || "";
      return `<button class="cat-tile ${sz}${active}" data-cat="${escapeAttr(c.name)}" title="${escapeAttr(desc)}">
        <h3>${escapeHTML(c.name)}</h3>
        <div class="count">${c.count.toLocaleString()}<small>datasets</small></div>
        ${desc ? `<p class="cat-desc">${escapeHTML(desc)}</p>` : ""}
      </button>`;
    }).join("");
    els.catMap.querySelectorAll(".cat-tile").forEach((b) => {
      b.addEventListener("click", () => {
        const c = b.dataset.cat;
        state.activeCat = state.activeCat === c ? null : c;
        renderCatMap();
        render();
        syncURL();
      });
    });
  }

  // ---------- Sidebar ----------
  function renderTypePills() {
    const types = (state.catalog.types || []).filter((t) => t.name);
    const all = `<button type="button" class="pill-btn ${state.activeType === null ? "on" : ""}" data-type="">All</button>`;
    const rest = types.map((t) => {
      const on = state.activeType === t.name ? "on" : "";
      return `<button type="button" class="pill-btn ${on}" data-type="${escapeAttr(t.name)}">${escapeHTML(t.name)} <small>${t.count}</small></button>`;
    }).join("");
    els.typePills.innerHTML = all + rest;
    els.typePills.querySelectorAll(".pill-btn").forEach((b) => {
      b.addEventListener("click", () => {
        const v = b.dataset.type || null;
        state.activeType = state.activeType === v ? null : v;
        renderTypePills();
        render();
        syncURL();
      });
    });
  }

  function renderAgencyList() {
    const all = state.catalog.agencies || [];
    const filter = state.agencyFilter.toLowerCase();
    const filtered = filter ? all.filter((a) => a.name.toLowerCase().includes(filter)) : all;
    const limit = state.showAllAgencies ? filtered.length : Math.min(AGENCY_INITIAL, filtered.length);
    const list = filtered.slice(0, limit);
    els.agencyList.innerHTML = list.map((a) => {
      const checked = state.activeAgencies.has(a.name) ? "checked" : "";
      return `<label class="checkbox"><input type="checkbox" data-agency="${escapeAttr(a.name)}" ${checked}> <span>${escapeHTML(a.name)}</span> <small>${a.count}</small></label>`;
    }).join("");
    els.agencyList.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", () => {
        const a = cb.dataset.agency;
        if (cb.checked) state.activeAgencies.add(a); else state.activeAgencies.delete(a);
        render();
        syncURL();
      });
    });
    els.agencyToggle.textContent = state.showAllAgencies
      ? "Show top agencies only"
      : `Show all agencies (${filtered.length})`;
    els.agencyCount.textContent = `(${all.length})`;
  }

  function renderTagCloud() {
    const counts = {};
    for (const d of state.catalog.datasets) {
      for (const t of d.g || []) {
        if (!t) continue;
        counts[t] = (counts[t] || 0) + 1;
      }
    }
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 24);
    els.tagCloud.innerHTML = top.map(([t, n]) => {
      const on = state.activeTags.has(t) ? "on" : "";
      return `<button type="button" class="tag-chip ${on}" data-tag="${escapeAttr(t)}">${escapeHTML(t)} <small>${n}</small></button>`;
    }).join("");
    els.tagCloud.querySelectorAll(".tag-chip").forEach((b) => {
      b.addEventListener("click", () => {
        const t = b.dataset.tag;
        if (state.activeTags.has(t)) state.activeTags.delete(t);
        else state.activeTags.add(t);
        renderTagCloud();
        render();
        syncURL();
      });
    });
  }

  // ---------- Weekly stats ----------
  function renderWeeklyStats(stats) {
    if (!stats || !stats.stats || !stats.stats.length) return;
    const wrap = document.getElementById("weekly-stats");
    const grid = document.getElementById("weekly-grid");
    const sub = document.getElementById("weekly-sub");
    wrap.hidden = false;
    const computed = (stats.computed_at || "").slice(0, 10);
    sub.innerHTML = `A few numbers pulled from City datasets refreshed in ${escapeHTML(stats.window_label || "the past week")}. Computed ${escapeHTML(computed)}. Each card links to its source dataset.`;
    grid.innerHTML = stats.stats.map((s) => {
      const cat = s.category || "Government Operations";
      const link = s.dataset_id ? `https://data.cityofnewyork.us/d/${encodeURIComponent(s.dataset_id)}` : null;
      const name = escapeHTML(s.dataset_name || "");
      const inner = `
        <span class="weekly-headline">${escapeHTML(s.headline)}</span>
        <span class="weekly-label">${escapeHTML(s.label)}</span>
        <span class="weekly-sub2">${escapeHTML(s.sub || "")}</span>
        <span class="weekly-source">${name}</span>`;
      return link
        ? `<a class="weekly-card" data-cat="${escapeAttr(cat)}" href="${link}" target="_blank" rel="noopener">${inner}</a>`
        : `<div class="weekly-card" data-cat="${escapeAttr(cat)}">${inner}</div>`;
    }).join("");
  }

  // ---------- Fresh strip ----------
  function renderFreshStrip() {
    const fresh = state.catalog.fresh || { new_this_month: [], updated_this_week: [] };
    const labelEl = document.getElementById("fresh-new-label");
    if (labelEl && fresh.new_label) labelEl.textContent = fresh.new_label;
    const renderTile = (it, isNew) => {
      const date = relativeDate(isNew ? (it.x || it.u) : it.u);
      const cat = it.c || "Uncategorized";
      return `<a class="fresh-tile" data-cat="${escapeAttr(cat)}" href="https://data.cityofnewyork.us/d/${encodeURIComponent(it.i)}" target="_blank" rel="noopener">
        ${isNew ? '<span class="badge-new">NEW</span>' : ""}
        <span class="fresh-name">${escapeHTML(it.n)}</span>
        <span class="fresh-meta">${escapeHTML(it.a || "")} · ${escapeHTML(date)}</span>
      </a>`;
    };
    els.freshNew.innerHTML = (fresh.new_this_month || []).slice(0, 12).map((it) => renderTile(it, true)).join("") || "<em>No brand-new datasets in the last 30 days.</em>";
    els.freshUpdated.innerHTML = (fresh.updated_this_week || []).slice(0, 12).map((it) => renderTile(it, false)).join("") || "<em>Nothing updated in the last 7 days.</em>";
  }

  // ---------- Active filter chips ----------
  function renderActiveChips() {
    const chips = [];
    if (state.activeCat) chips.push({ label: `Category: ${state.activeCat}`, clear: () => { state.activeCat = null; renderCatMap(); } });
    if (state.activeType) chips.push({ label: `Type: ${state.activeType}`, clear: () => { state.activeType = null; renderTypePills(); } });
    for (const a of state.activeAgencies) chips.push({ label: `Agency: ${a}`, clear: () => { state.activeAgencies.delete(a); renderAgencyList(); } });
    for (const t of state.activeTags) chips.push({ label: `Tag: ${t}`, clear: () => { state.activeTags.delete(t); renderTagCloud(); } });
    if (state.picksOnly) chips.push({ label: "Journalist picks only", clear: () => { state.picksOnly = false; els.picksOnly.checked = false; } });

    if (chips.length === 0) {
      els.activeChips.innerHTML = "";
      return;
    }
    els.activeChips.innerHTML = chips.map((c, i) => `<button type="button" class="chip" data-i="${i}">${escapeHTML(c.label)} <span class="x">×</span></button>`).join("");
    els.activeChips.querySelectorAll(".chip").forEach((btn, i) => {
      btn.addEventListener("click", () => {
        chips[i].clear();
        render();
        syncURL();
      });
    });
  }

  // ---------- Results ----------
  function getResults() {
    const q = state.parsed.fuseQuery || "";
    let list;
    if (q) {
      const hits = state.fuse.search(q, { limit: 1500 });
      list = hits.map((h) => h.item);
    } else {
      list = state.catalog.datasets.slice();
    }

    // Apply parsed inline filters
    if (state.parsed.filters) list = window.NYC_APPLY_FILTERS(list, state.parsed.filters);

    if (state.activeCat) list = list.filter((d) => d.c === state.activeCat);
    if (state.activeType) list = list.filter((d) => d.t === state.activeType);
    if (state.activeAgencies.size) list = list.filter((d) => state.activeAgencies.has(d.a));
    if (state.activeTags.size) list = list.filter((d) => (d.g || []).some((t) => state.activeTags.has(t)));
    if (state.picksOnly) list = list.filter((d) => state.picksById.has(d.i));
    list = list.filter(passesFreshness);

    if (state.sort === "views") list.sort((a, b) => (b.v || 0) - (a.v || 0));
    else if (state.sort === "updated") list.sort((a, b) => (b.u || "").localeCompare(a.u || ""));
    else if (state.sort === "alpha") list.sort((a, b) => a.n.localeCompare(b.n));
    else if (!q) list.sort((a, b) => (b.v || 0) - (a.v || 0));

    return list;
  }

  function renderCard(d) {
    const f = freshnessClass(d.u);
    const url = `https://data.cityofnewyork.us/d/${encodeURIComponent(d.i)}`;
    const summary = d.s ? escapeHTML(d.s) : `<em>No description provided by the publishing agency.</em>`;
    const agency = d.a ? `<span class="agency">${escapeHTML(d.a)}</span>` : `<span class="agency">NYC agency</span>`;
    const type = d.t && d.t !== "dataset" ? `<span class="pill type">${escapeHTML(d.t)}</span>` : "";
    const pick = state.picksById.get(d.i);
    const star = pick ? `<span class="pick-star" title="Journalist pick: ${escapeAttr(pick.why)}">★</span>` : "";
    const tagChips = (d.g || []).slice(0, 4).map((t) => `<button type="button" class="tag-mini" data-tag="${escapeAttr(t)}">${escapeHTML(t)}</button>`).join("");
    return `<article class="card" data-cat="${escapeAttr(d.c)}">
      <h4>${star}<a href="${url}" target="_blank" rel="noopener">${escapeHTML(d.n)}</a></h4>
      <div class="summary">${summary}${pick ? `<div class="pick-note"><strong>Why journalists use it:</strong> ${escapeHTML(pick.why)} ${pick.gotcha ? `<em>Gotcha: ${escapeHTML(pick.gotcha)}</em>` : ""}</div>` : ""}</div>
      <div class="meta">
        ${agency}
        <span class="pill ${f.klass}">${f.label}</span>
        ${type}
        ${d.v ? `<span>${fmtNum(d.v)} views</span>` : ""}
      </div>
      ${tagChips ? `<div class="card-tags">${tagChips}</div>` : ""}
    </article>`;
  }

  function suggestEmptyState() {
    const q = (state.query || "").trim().toLowerCase();
    const suggestions = [];

    // If filters are active, suggest dropping each one
    if (state.activeCat) {
      const without = state.catalog.datasets.filter((d) => {
        if (state.activeType && d.t !== state.activeType) return false;
        if (state.activeAgencies.size && !state.activeAgencies.has(d.a)) return false;
        return true;
      });
      const hits = q ? state.fuse.search(q, { limit: 50 }).map((h) => h.item).filter((d) => without.includes(d)) : without;
      if (hits.length > 0) suggestions.push(`Remove the <strong>${escapeHTML(state.activeCat)}</strong> filter — <button type="button" class="link-btn" id="es-clear-cat">${hits.length} match in other categories</button>.`);
    }
    if (state.activeType) suggestions.push(`Remove the type filter — <button type="button" class="link-btn" id="es-clear-type">try all types</button>.`);
    if (state.activeAgencies.size) suggestions.push(`Remove the agency filter — <button type="button" class="link-btn" id="es-clear-agency">try all agencies</button>.`);

    // Tag-similarity suggestion
    if (q.length >= 3) {
      const tags = new Set();
      for (const d of state.catalog.datasets) for (const t of d.g || []) if (t) tags.add(t);
      const tagArr = [...tags];
      const distance = (a, b) => {
        const m = a.length, n = b.length; if (Math.abs(m - n) > 3) return 99;
        const dp = Array.from({ length: m + 1 }, (_, i) => [i].concat(new Array(n).fill(0)));
        for (let j = 1; j <= n; j++) dp[0][j] = j;
        for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++) {
          dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
        }
        return dp[m][n];
      };
      const close = tagArr.map((t) => [t, distance(t.toLowerCase(), q)]).filter((x) => x[1] <= 2).sort((a, b) => a[1] - b[1]).slice(0, 3);
      if (close.length) suggestions.push(`Did you mean: ${close.map(([t]) => `<button type="button" class="link-btn es-tag" data-tag="${escapeAttr(t)}">${escapeHTML(t)}</button>`).join(", ")}?`);
    }

    // Fallback: top 3 most-viewed in active category (or overall)
    let pool = state.catalog.datasets;
    if (state.activeCat) pool = pool.filter((d) => d.c === state.activeCat);
    const top3 = pool.slice().sort((a, b) => (b.v || 0) - (a.v || 0)).slice(0, 3);

    let html = `<h3>No matches.</h3>`;
    if (suggestions.length) html += `<ul class="empty-suggest">${suggestions.map((s) => `<li>${s}</li>`).join("")}</ul>`;
    if (top3.length) html += `<h4>Most-viewed ${state.activeCat ? `in ${escapeHTML(state.activeCat)}` : "datasets"} right now</h4><div class="empty-top3">${top3.map(renderCard).join("")}</div>`;
    return html;
  }

  function render() {
    const list = getResults();
    const total = state.catalog.datasets.length;
    els.stats.innerHTML = `<strong>${list.length.toLocaleString()}</strong> of ${total.toLocaleString()} datasets. <span style="color:var(--ink-mute)">Catalog refreshed ${state.fetchedAt}.</span>`;

    renderActiveChips();

    if (list.length === 0) {
      els.results.innerHTML = "";
      els.empty.hidden = false;
      els.empty.innerHTML = suggestEmptyState();
      // Wire up empty-state suggestion buttons
      const escClear = (sel, fn) => { const b = els.empty.querySelector(sel); if (b) b.addEventListener("click", () => { fn(); render(); syncURL(); }); };
      escClear("#es-clear-cat", () => { state.activeCat = null; renderCatMap(); });
      escClear("#es-clear-type", () => { state.activeType = null; renderTypePills(); });
      escClear("#es-clear-agency", () => { state.activeAgencies.clear(); renderAgencyList(); });
      els.empty.querySelectorAll(".es-tag").forEach((b) => {
        b.addEventListener("click", () => { state.activeTags.add(b.dataset.tag); state.query = ""; els.q.value = ""; state.parsed = window.NYC_PARSE_QUERY(""); renderTagCloud(); render(); syncURL(); });
      });
    } else {
      els.empty.hidden = true;
      const slice = list.slice(0, RENDER_CAP);
      els.results.innerHTML = slice.map(renderCard).join("") +
        (list.length > RENDER_CAP ? `<div class="empty" style="grid-column:1/-1">Showing the first ${RENDER_CAP} of ${list.length.toLocaleString()} matches. Refine your search or pick a category to narrow further.</div>` : "");
      // Wire up clickable card tag chips
      els.results.querySelectorAll(".tag-mini").forEach((b) => {
        b.addEventListener("click", () => {
          state.activeTags.add(b.dataset.tag);
          renderTagCloud();
          render();
          syncURL();
        });
      });
    }
  }

  function debounce(fn, ms) {
    let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  // ---------- URL state ----------
  function syncURL() {
    const params = new URLSearchParams();
    if (state.query) params.set("q", state.query);
    if (state.activeCat) params.set("cat", state.activeCat);
    if (state.activeType) params.set("type", state.activeType);
    if (state.activeAgencies.size) params.set("agency", [...state.activeAgencies].join("|"));
    if (state.activeTags.size) params.set("tag", [...state.activeTags].join("|"));
    if (state.fresh !== "all") params.set("age", state.fresh);
    if (state.sort !== "relevance") params.set("sort", state.sort);
    if (state.picksOnly) params.set("picks", "1");
    const hash = params.toString();
    const newUrl = hash ? `#${hash}` : window.location.pathname;
    if (("#" + hash) !== window.location.hash) {
      history.replaceState(null, "", newUrl);
    }
  }

  function loadURL() {
    const h = window.location.hash.replace(/^#/, "");
    if (!h) return;
    const params = new URLSearchParams(h);
    if (params.get("q")) {
      state.query = params.get("q");
      els.q.value = state.query;
      state.parsed = window.NYC_PARSE_QUERY(state.query);
    }
    if (params.get("cat")) state.activeCat = params.get("cat");
    if (params.get("type")) state.activeType = params.get("type");
    if (params.get("agency")) for (const a of params.get("agency").split("|")) state.activeAgencies.add(a);
    if (params.get("tag")) for (const t of params.get("tag").split("|")) state.activeTags.add(t);
    if (params.get("age")) { state.fresh = params.get("age"); els.fresh.value = state.fresh; }
    if (params.get("sort")) { state.sort = params.get("sort"); els.sort.value = state.sort; }
    if (params.get("picks") === "1") { state.picksOnly = true; els.picksOnly.checked = true; }
  }

  // ---------- Init ----------
  async function init() {
    let data, picks, weekly;
    try {
      const [r1, r2, r3] = await Promise.all([
        fetch("data/catalog.min.json", { cache: "no-cache" }),
        fetch("data/journalist_picks.json", { cache: "no-cache" }),
        fetch("data/weekly_stats.json", { cache: "no-cache" }).catch(() => null),
      ]);
      data = await r1.json();
      picks = await r2.json();
      try { weekly = r3 && r3.ok ? await r3.json() : null; } catch (_) { weekly = null; }
    } catch (e) {
      els.stats.textContent = "Failed to load the catalog. Try refreshing.";
      console.error(e);
      return;
    }
    state.catalog = data;
    state.fetchedAt = (data.fetched_at || "").slice(0, 10) || "recently";
    state.picksById = new Map((picks.picks || []).map((p) => [p.id, p]));

    state.fuse = new Fuse(data.datasets, {
      keys: [
        { name: "n", weight: 0.55 },
        { name: "s", weight: 0.25 },
        { name: "g", weight: 0.12 },
        { name: "a", weight: 0.08 },
      ],
      threshold: 0.34,
      ignoreLocation: true,
      includeScore: true,
      minMatchCharLength: 2,
    });

    loadURL();
    state.parsed = window.NYC_PARSE_QUERY(state.query);

    renderCatMap();
    renderTypePills();
    renderAgencyList();
    renderTagCloud();
    renderWeeklyStats(weekly);
    renderFreshStrip();
    render();

    els.q.addEventListener("input", debounce(() => {
      state.query = els.q.value;
      state.parsed = window.NYC_PARSE_QUERY(state.query);
      if (state.query) state.sort = "relevance";
      render();
      syncURL();
    }, 120));
    els.sort.addEventListener("change", () => { state.sort = els.sort.value; render(); syncURL(); });
    els.fresh.addEventListener("change", () => { state.fresh = els.fresh.value; render(); syncURL(); });
    els.clear.addEventListener("click", () => {
      state.query = ""; state.activeCat = null; state.sort = "relevance"; state.fresh = "all";
      state.activeAgencies.clear(); state.activeType = null; state.activeTags.clear(); state.picksOnly = false;
      els.q.value = ""; els.sort.value = "relevance"; els.fresh.value = "all"; els.picksOnly.checked = false;
      state.parsed = window.NYC_PARSE_QUERY("");
      renderCatMap(); renderTypePills(); renderAgencyList(); renderTagCloud(); render();
      history.replaceState(null, "", window.location.pathname);
    });
    els.agencySearch.addEventListener("input", debounce(() => { state.agencyFilter = els.agencySearch.value; renderAgencyList(); }, 80));
    els.agencyToggle.addEventListener("click", () => { state.showAllAgencies = !state.showAllAgencies; renderAgencyList(); });
    els.picksOnly.addEventListener("change", () => { state.picksOnly = els.picksOnly.checked; render(); syncURL(); });

    window.addEventListener("hashchange", () => {
      // Only react to outside-driven hash changes, not our own
      if (window._suppressHash) return;
      loadURL();
      state.parsed = window.NYC_PARSE_QUERY(state.query);
      renderCatMap(); renderTypePills(); renderAgencyList(); renderTagCloud(); render();
    });
  }

  init();
})();
