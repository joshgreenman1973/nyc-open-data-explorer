(() => {
  const els = {
    q: document.getElementById("q"),
    sort: document.getElementById("sort"),
    clear: document.getElementById("clear"),
    surprise: document.getElementById("surprise"),
    stats: document.getElementById("stats"),
    catMap: document.getElementById("cat-map"),
    results: document.getElementById("results"),
    empty: document.getElementById("empty"),
    activeChips: document.getElementById("active-chips"),
    typePills: document.getElementById("type-pills"),
    freshPills: document.getElementById("freshness-pills"),
    agencyList: document.getElementById("agency-list"),
    agencySearch: document.getElementById("agency-search"),
    agencyToggle: document.getElementById("agency-toggle"),
    agencyCount: document.getElementById("agency-count"),
    tagCloud: document.getElementById("tag-cloud"),
    picksOnly: document.getElementById("picks-only"),
    favsOnly: document.getElementById("favs-only"),
    favCount: document.getElementById("fav-count"),
    freshNew: document.getElementById("fresh-new"),
    freshUpdated: document.getElementById("fresh-updated"),
  };

  const state = {
    catalog: null,
    fuse: null,
    picksById: new Map(),
    activeCat: null,
    activeAgencies: new Set(),
    activeType: null,
    activeTags: new Set(),
    excludedTags: new Set(),
    picksOnly: false,
    favs: new Set(),
    favsOnly: false,
    query: "",
    parsed: { fuseQuery: "", filters: null, freshness: null },
    sort: "relevance",
    fresh: "all",
    fetchedAt: null,
    showAllAgencies: false,
    showAllTypes: false,
    agencyFilter: "",
  };

  const SIZE_RULES = [
    { min: 500, klass: "size-xl" },
    { min: 200, klass: "size-l" },
  ];
  const AGENCY_INITIAL = 12;
  const TYPE_INITIAL = 4;
  const RENDER_CAP = 200;
  const FAVS_KEY = "nyc-ode-favorites-v1";

  // ---------- Helpers ----------
  function escapeHTML(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[m]));
  }
  const escapeAttr = escapeHTML;

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

  // Agency display: show plain name, suppress trailing acronym in parens.
  function plainAgencyName(name) {
    if (!name) return "";
    return name.replace(/\s*\([A-Z][A-Z0-9 &/\-]*\)\s*$/, "").trim();
  }
  function agencyAcronym(name) {
    const m = (name || "").match(/\(([A-Z][A-Z0-9 &/\-]*)\)\s*$/);
    return m ? m[1] : "";
  }

  function median(arr) {
    if (!arr || !arr.length) return 0;
    const s = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
  }

  // ---------- Favorites (localStorage) ----------
  function loadFavs() {
    try {
      const raw = localStorage.getItem(FAVS_KEY);
      if (!raw) return new Set();
      const parsed = JSON.parse(raw);
      return new Set(Array.isArray(parsed) ? parsed : []);
    } catch (_) { return new Set(); }
  }
  function saveFavs(set) { try { localStorage.setItem(FAVS_KEY, JSON.stringify([...set])); } catch (_) {} }

  function updateFavCount() {
    if (els.favCount) els.favCount.textContent = state.favs.size;
    renderMyFavorites();
  }

  function renderMyFavorites() {
    const sec = document.getElementById("my-favorites");
    const track = document.getElementById("favs-track");
    const headCount = document.getElementById("favs-head-count");
    const clearBtn = document.getElementById("favs-clear");
    if (!sec || !track) return;
    if (!state.favs.size || !state.catalog) {
      sec.hidden = true;
      return;
    }
    sec.hidden = false;
    if (headCount) headCount.textContent = `(${state.favs.size})`;
    if (clearBtn) clearBtn.hidden = false;
    const favList = state.catalog.datasets
      .filter((d) => state.favs.has(d.i))
      .sort((a, b) => (b.u || "").localeCompare(a.u || ""));
    track.innerHTML = favList.map((d) => {
      const cat = d.c || "Uncategorized";
      const url = `https://data.cityofnewyork.us/d/${encodeURIComponent(d.i)}`;
      const updated = relativeDate(d.u) || "no date";
      const agency = plainAgencyName(d.a) || "NYC agency";
      return `<div class="fav-tile" data-cat="${escapeAttr(cat)}">
        <button type="button" class="fav-btn on" data-fav="${escapeAttr(d.i)}" title="Remove from favorites" aria-label="Remove ${escapeAttr(d.n)} from favorites">♥</button>
        <a class="fav-name" href="${url}" target="_blank" rel="noopener">${escapeHTML(d.n)}</a>
        <span class="fav-meta">${escapeHTML(agency)}</span>
        <span class="fav-meta"><span class="cat-dot"></span>${escapeHTML(cat)} · updated ${escapeHTML(updated)}</span>
      </div>`;
    }).join("");
    track.querySelectorAll(".fav-btn").forEach((b) => {
      b.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleFav(b.dataset.fav);
        const main = els.results.querySelector(`.fav-btn[data-fav="${CSS.escape(b.dataset.fav)}"]`);
        if (main) {
          main.classList.remove("on");
          main.textContent = "♡";
          main.setAttribute("aria-label", `Add ${main.dataset.fav} to favorites`);
        }
      });
    });
  }
  function toggleFav(id) {
    if (state.favs.has(id)) state.favs.delete(id); else state.favs.add(id);
    saveFavs(state.favs);
    updateFavCount();
  }

  function tileSize(count) {
    for (const r of SIZE_RULES) if (count >= r.min) return r.klass;
    return "";
  }

  // ---------- Category map ----------
  function renderCatMap() {
    const cats = state.catalog.categories;
    els.catMap.innerHTML = cats.map((c) => {
      const sz = tileSize(c.count);
      const active = state.activeCat === c.name ? " active" : "";
      const desc = (window.NYC_CAT_DESC && window.NYC_CAT_DESC[c.name]) || "";
      return `<button class="cat-tile ${sz}${active}" data-cat="${escapeAttr(c.name)}" aria-pressed="${state.activeCat === c.name}" title="${escapeAttr(desc)}">
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

  // ---------- Sidebar: freshness pills ----------
  function renderFreshPills() {
    if (!els.freshPills) return;
    els.freshPills.querySelectorAll(".pill-btn").forEach((b) => {
      b.classList.toggle("on", b.dataset.fresh === state.fresh);
      b.setAttribute("aria-pressed", b.dataset.fresh === state.fresh);
    });
  }
  function bindFreshPills() {
    if (!els.freshPills) return;
    els.freshPills.querySelectorAll(".pill-btn").forEach((b) => {
      b.addEventListener("click", () => {
        state.fresh = b.dataset.fresh;
        renderFreshPills();
        render();
        syncURL();
      });
    });
  }

  // ---------- Sidebar: view-type pills (top 4 + "more" toggle) ----------
  function renderTypePills() {
    const types = (state.catalog.types || []).filter((t) => t.name);
    const limit = state.showAllTypes ? types.length : Math.min(TYPE_INITIAL, types.length);
    const visible = types.slice(0, limit);
    const all = `<button type="button" class="pill-btn ${state.activeType === null ? "on" : ""}" data-type="" aria-pressed="${state.activeType === null}">All</button>`;
    const rest = visible.map((t) => {
      const on = state.activeType === t.name;
      return `<button type="button" class="pill-btn ${on ? 'on' : ''}" data-type="${escapeAttr(t.name)}" aria-pressed="${on}">${escapeHTML(t.name)} <small>${t.count}</small></button>`;
    }).join("");
    const moreBtn = types.length > TYPE_INITIAL
      ? `<button type="button" class="pill-btn muted-toggle" id="type-more">${state.showAllTypes ? "Show fewer" : `+${types.length - TYPE_INITIAL} more`}</button>`
      : "";
    els.typePills.innerHTML = all + rest + moreBtn;
    els.typePills.querySelectorAll(".pill-btn").forEach((b) => {
      if (b.id === "type-more") {
        b.addEventListener("click", () => { state.showAllTypes = !state.showAllTypes; renderTypePills(); });
        return;
      }
      b.addEventListener("click", () => {
        const v = b.dataset.type || null;
        state.activeType = state.activeType === v ? null : v;
        renderTypePills();
        render();
        syncURL();
      });
    });
  }

  // ---------- Sidebar: agencies (plain names) ----------
  function renderAgencyList() {
    const all = state.catalog.agencies || [];
    const filter = state.agencyFilter.toLowerCase();
    const filtered = filter ? all.filter((a) => a.name.toLowerCase().includes(filter)) : all;
    const limit = state.showAllAgencies ? filtered.length : Math.min(AGENCY_INITIAL, filtered.length);
    const list = filtered.slice(0, limit);
    els.agencyList.innerHTML = list.map((a) => {
      const checked = state.activeAgencies.has(a.name) ? "checked" : "";
      const plain = plainAgencyName(a.name);
      const acro = agencyAcronym(a.name);
      const acroHTML = acro ? ` <small class="acro">${escapeHTML(acro)}</small>` : "";
      return `<label class="checkbox"><input type="checkbox" data-agency="${escapeAttr(a.name)}" ${checked}> <span>${escapeHTML(plain)}${acroHTML}</span> <small>${a.count}</small></label>`;
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
      return `<button type="button" class="tag-chip ${on}" data-tag="${escapeAttr(t)}" aria-pressed="${state.activeTags.has(t)}">${escapeHTML(t)} <small>${n}</small></button>`;
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

  // ---------- Weekly stats (richer) ----------
  function sparklineSVG(trend) {
    if (!trend || trend.length < 2) return "";
    const W = 200, H = 36, pad = 2;
    const max = Math.max(...trend);
    const min = Math.min(...trend);
    const range = Math.max(1, max - min);
    const step = (W - pad * 2) / (trend.length - 1);
    const pts = trend.map((v, i) => {
      const x = pad + i * step;
      const y = H - pad - ((v - min) / range) * (H - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const last = pts[pts.length - 1].split(",");
    const path = `M${pts.join(" L")}`;
    const area = `M${pts[0]} L${pts.join(" L")} L${(pad + (trend.length - 1) * step).toFixed(1)},${H - pad} L${pad},${H - pad} Z`;
    // Median reference line (across the prior 11 weeks; excludes current)
    const refSrc = trend.slice(0, -1);
    const med = median(refSrc);
    const medY = H - pad - ((med - min) / range) * (H - pad * 2);
    const medLine = `<line x1="${pad}" x2="${W - pad}" y1="${medY.toFixed(1)}" y2="${medY.toFixed(1)}" class="spark-median"/>`;
    return `<svg class="sparkline" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
      ${medLine}
      <path d="${area}" class="spark-area"/>
      <path d="${path}" class="spark-line"/>
      <circle cx="${last[0]}" cy="${last[1]}" r="2.5" class="spark-dot"/>
    </svg>`;
  }

  function deltaHTML(pct) {
    if (pct == null) return "";
    const dir = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
    const arrow = pct > 0 ? "↑" : pct < 0 ? "↓" : "→";
    const sign = pct > 0 ? "+" : "";
    return `<span class="weekly-delta ${dir}">${arrow} ${sign}${pct}% vs prior week</span>`;
  }

  function interpretation(trend) {
    if (!trend || trend.length < 4) return "";
    const cur = trend[trend.length - 1];
    const prev = trend.slice(0, -1);
    const med = median(prev);
    if (med <= 0) return "";
    const ratio = cur / med;
    if (ratio >= 1.25) return "Higher than typical";
    if (ratio >= 1.10) return "A bit above typical";
    if (ratio <= 0.75) return "Notably lower than typical";
    if (ratio <= 0.90) return "A bit below typical";
    return "Right around typical";
  }

  function categoryCount(cat) {
    if (!cat || !state.catalog) return 0;
    return state.catalog.datasets.filter((d) => d.c === cat).length;
  }

  function renderWeeklyStats(stats) {
    if (!stats || !stats.stats || !stats.stats.length) return;
    const wrap = document.getElementById("weekly-stats");
    const grid = document.getElementById("weekly-grid");
    const sub = document.getElementById("weekly-sub");
    wrap.hidden = false;
    const computed = (stats.computed_at || "").slice(0, 10);
    const weeks = stats.trend_weeks || 12;
    sub.innerHTML = `Pulled live from City datasets. Dashed line is the ${weeks - 1}-week median; the dot is this week. Click a card to filter results to that category.`;
    grid.innerHTML = stats.stats.map((s) => {
      const cat = s.category || "";
      const link = s.dataset_id ? `https://data.cityofnewyork.us/d/${encodeURIComponent(s.dataset_id)}` : null;
      const name = escapeHTML(s.dataset_name || "");
      const spark = sparklineSVG(s.trend);
      const delta = deltaHTML(s.delta_pct);
      const interp = interpretation(s.trend);
      const interpLine = interp ? `<span class="weekly-interp">${escapeHTML(interp)}</span>` : "";
      const catLine = cat ? `<span class="cat-dot"></span><span>${escapeHTML(cat)}</span>` : "<span>NYC catalog overall</span>";
      const catCount = cat ? categoryCount(cat) : (state.catalog ? state.catalog.datasets.length : 0);
      const cta = cat
        ? `<span>→ Browse all ${catCount.toLocaleString()} ${escapeHTML(cat)} datasets</span>`
        : `<span>→ Browse all datasets</span>`;
      const sourceLink = link
        ? `<a class="source-link" href="${link}" target="_blank" rel="noopener" title="Open ${name} on data.cityofnewyork.us">${name} ↗</a>`
        : `<span class="source-link">${name}</span>`;
      const inner = `
        <span class="weekly-headline">${escapeHTML(s.headline)}</span>
        <span class="weekly-label">${escapeHTML(s.label)}</span>
        ${interpLine}
        ${delta}
        ${spark}
        <span class="weekly-sub2">${escapeHTML(s.sub || "")}</span>
        <span class="weekly-sub2" style="font-size:11px;color:var(--ink-mute);">${catLine}</span>
        <div class="weekly-cta">
          ${cta}
          ${sourceLink}
        </div>`;
      return `<button type="button" class="weekly-card" data-cat="${escapeAttr(cat)}" data-stat="${escapeAttr(s.key)}" aria-label="Filter results to ${escapeAttr(cat || 'all datasets')}, sorted by most recently updated">${inner}</button>`;
    }).join("");
    grid.querySelectorAll(".weekly-card").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        if (e.target.closest(".source-link")) return;
        const cat = btn.dataset.cat || null;
        state.activeCat = cat || null;
        state.sort = "updated";
        els.sort.value = "updated";
        renderCatMap();
        render();
        syncURL();
        const results = document.getElementById("results");
        if (results) results.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  // ---------- In the news (curated headline → dataset matches) ----------
  function renderNewsMatch(news) {
    const sec = document.getElementById("news-match");
    const list = document.getElementById("news-list");
    const meta = document.getElementById("news-meta");
    if (!sec || !list) return;
    if (!news || !Array.isArray(news.matches) || news.matches.length === 0) {
      sec.hidden = true;
      return;
    }
    sec.hidden = false;
    const computed = (news.computed_at || "").slice(0, 10);
    if (meta) meta.textContent = computed ? `(refreshed ${computed})` : "";
    list.innerHTML = news.matches.map((m) => {
      const cat = m.dataset_category || "Uncategorized";
      const headlineLink = m.link
        ? `<a class="news-headline" href="${escapeAttr(m.link)}" target="_blank" rel="noopener">${escapeHTML(m.headline)} ↗</a>`
        : `<span class="news-headline">${escapeHTML(m.headline)}</span>`;
      const source = m.source ? `<span class="news-source">${escapeHTML(m.source)}</span>` : "";
      return `<div class="news-item" data-cat="${escapeAttr(cat)}">
        ${headlineLink}
        ${source}
        <span class="news-arrow">→ Backed by</span>
        <a class="news-dataset" href="${escapeAttr(m.dataset_url)}" target="_blank" rel="noopener"><span class="cat-dot"></span>${escapeHTML(m.dataset_name)}</a>
        <span class="news-meta-line">${escapeHTML(m.dataset_agency || "")}${m.topic ? ` · topic: ${escapeHTML(m.topic)}` : ""}</span>
      </div>`;
    }).join("");
  }

  // ---------- Fresh strip (vertical in right rail) ----------
  function renderFreshStrip() {
    const fresh = state.catalog.fresh || { new_this_month: [], updated_this_week: [] };
    const labelEl = document.getElementById("fresh-new-label");
    if (labelEl && fresh.new_label) labelEl.textContent = fresh.new_label;
    const renderTile = (it, isNew) => {
      const date = relativeDate(isNew ? (it.x || it.u) : it.u);
      const cat = it.c || "Uncategorized";
      const agency = plainAgencyName(it.a);
      return `<a class="fresh-tile" data-cat="${escapeAttr(cat)}" href="https://data.cityofnewyork.us/d/${encodeURIComponent(it.i)}" target="_blank" rel="noopener">
        ${isNew ? '<span class="badge-new">NEW</span>' : ""}
        <span class="fresh-name">${escapeHTML(it.n)}</span>
        <span class="fresh-meta">${escapeHTML(agency)} · ${escapeHTML(date)}</span>
        <span class="fresh-meta"><span class="cat-dot"></span>${escapeHTML(cat)}</span>
      </a>`;
    };
    els.freshNew.innerHTML = (fresh.new_this_month || []).slice(0, 6).map((it) => renderTile(it, true)).join("") || "<em style='font-size:12px;color:var(--ink-mute);'>No brand-new datasets in the last 30 days.</em>";
    els.freshUpdated.innerHTML = (fresh.updated_this_week || []).slice(0, 6).map((it) => renderTile(it, false)).join("") || "<em style='font-size:12px;color:var(--ink-mute);'>Nothing updated in the last 7 days.</em>";
  }

  // ---------- Active filter chips ----------
  function renderActiveChips() {
    const chips = [];
    if (state.activeCat) chips.push({ label: `Category: ${state.activeCat}`, clear: () => { state.activeCat = null; renderCatMap(); } });
    if (state.activeType) chips.push({ label: `Type: ${state.activeType}`, clear: () => { state.activeType = null; renderTypePills(); } });
    for (const a of state.activeAgencies) chips.push({ label: `Agency: ${plainAgencyName(a)}`, clear: () => { state.activeAgencies.delete(a); renderAgencyList(); } });
    for (const t of state.activeTags) chips.push({ label: `Tag: ${t}`, clear: () => { state.activeTags.delete(t); renderTagCloud(); } });
    if (state.fresh !== "all") {
      const map = { "30": "Updated in last 30 days", "365": "Updated in last year", stale: "Older than 1 year" };
      chips.push({ label: map[state.fresh] || state.fresh, clear: () => { state.fresh = "all"; renderFreshPills(); } });
    }
    if (state.picksOnly) chips.push({ label: "Journalist picks only", clear: () => { state.picksOnly = false; els.picksOnly.checked = false; } });
    if (state.favsOnly) chips.push({ label: "Favorites only", clear: () => { state.favsOnly = false; if (els.favsOnly) els.favsOnly.checked = false; } });

    if (chips.length === 0) {
      els.activeChips.innerHTML = "";
      return;
    }
    els.activeChips.innerHTML = chips.map((c, i) => `<button type="button" class="chip" data-i="${i}" aria-label="Remove filter: ${escapeAttr(c.label)}">${escapeHTML(c.label)} <span class="x" aria-hidden="true">×</span></button>`).join("");
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

    if (state.parsed.filters) list = window.NYC_APPLY_FILTERS(list, state.parsed.filters);
    if (state.activeCat) list = list.filter((d) => d.c === state.activeCat);
    if (state.activeType) list = list.filter((d) => d.t === state.activeType);
    if (state.activeAgencies.size) list = list.filter((d) => state.activeAgencies.has(d.a));
    if (state.activeTags.size) list = list.filter((d) => (d.g || []).some((t) => state.activeTags.has(t)));
    if (state.picksOnly) list = list.filter((d) => state.picksById.has(d.i));
    if (state.favsOnly) list = list.filter((d) => state.favs.has(d.i));
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
    const agency = d.a ? `<span class="agency">${escapeHTML(plainAgencyName(d.a))}</span>` : `<span class="agency">NYC agency</span>`;
    const type = d.t && d.t !== "dataset" ? `<span class="pill type">${escapeHTML(d.t)}</span>` : "";
    const pick = state.picksById.get(d.i);
    const star = pick ? `<span class="pick-star" title="Journalist pick: ${escapeAttr(pick.why)}" aria-label="Journalist pick">★</span>` : "";
    const tagChips = (d.g || []).slice(0, 4).map((t) => `<button type="button" class="tag-mini" data-tag="${escapeAttr(t)}">${escapeHTML(t)}</button>`).join("");
    const isFav = state.favs.has(d.i);
    const favBtn = `<button type="button" class="fav-btn ${isFav ? 'on' : ''}" data-fav="${escapeAttr(d.i)}" aria-label="${isFav ? 'Remove from favorites' : 'Add to favorites'}: ${escapeAttr(d.n)}" title="${isFav ? 'Saved to your favorites' : 'Save to favorites'}" aria-pressed="${isFav}">${isFav ? '♥' : '♡'}</button>`;
    return `<article class="card" data-cat="${escapeAttr(d.c)}" data-url="${escapeAttr(url)}" tabindex="0" role="link" aria-label="Open ${escapeAttr(d.n)} on data.cityofnewyork.us">
      ${favBtn}
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
      // Whole-card click: navigate to dataset URL unless click hit an inner control
      const handleCardOpen = (card) => {
        const u = card && card.dataset.url;
        if (u) window.open(u, "_blank", "noopener");
      };
      els.results.querySelectorAll(".card").forEach((card) => {
        card.addEventListener("click", (e) => {
          if (e.target.closest(".fav-btn, .tag-mini, .pick-star, a, button")) return;
          handleCardOpen(card);
        });
        // Keyboard accessibility: Enter or Space opens the link
        card.addEventListener("keydown", (e) => {
          if ((e.key === "Enter" || e.key === " ") && !e.target.closest(".fav-btn, .tag-mini, a, button")) {
            e.preventDefault();
            handleCardOpen(card);
          }
        });
      });
      els.results.querySelectorAll(".tag-mini").forEach((b) => {
        b.addEventListener("click", () => {
          state.activeTags.add(b.dataset.tag);
          renderTagCloud();
          render();
          syncURL();
        });
      });
      els.results.querySelectorAll(".fav-btn").forEach((b) => {
        b.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const id = b.dataset.fav;
          toggleFav(id);
          const nowFav = state.favs.has(id);
          b.classList.toggle("on", nowFav);
          b.textContent = nowFav ? "♥" : "♡";
          b.classList.add("pulsing");
          setTimeout(() => b.classList.remove("pulsing"), 450);
          b.setAttribute("aria-label", nowFav ? "Remove from favorites" : "Add to favorites");
          b.setAttribute("aria-pressed", nowFav);
          b.setAttribute("title", nowFav ? "Saved to your favorites" : "Save to favorites");
          if (state.favsOnly) render();
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
    if (state.favsOnly) params.set("favs", "1");
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
    if (params.get("age")) { state.fresh = params.get("age"); }
    if (params.get("sort")) { state.sort = params.get("sort"); els.sort.value = state.sort; }
    if (params.get("picks") === "1") { state.picksOnly = true; els.picksOnly.checked = true; }
    if (params.get("favs") === "1") { state.favsOnly = true; if (els.favsOnly) els.favsOnly.checked = true; }
  }

  // ---------- Init ----------
  async function init() {
    let data, picks, weekly, news;
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        fetch("data/catalog.min.json", { cache: "no-cache" }),
        fetch("data/journalist_picks.json", { cache: "no-cache" }),
        fetch("data/weekly_stats.json", { cache: "no-cache" }).catch(() => null),
        fetch("data/news_matches.json", { cache: "no-cache" }).catch(() => null),
      ]);
      data = await r1.json();
      picks = await r2.json();
      try { weekly = r3 && r3.ok ? await r3.json() : null; } catch (_) { weekly = null; }
      try { news = r4 && r4.ok ? await r4.json() : null; } catch (_) { news = null; }
    } catch (e) {
      els.stats.textContent = "Failed to load the catalog. Try refreshing.";
      console.error(e);
      return;
    }
    state.catalog = data;
    state.fetchedAt = (data.fetched_at || "").slice(0, 10) || "recently";
    state.picksById = new Map((picks.picks || []).map((p) => [p.id, p]));
    state.favs = loadFavs();
    updateFavCount();

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
    renderFreshPills(); bindFreshPills();
    renderAgencyList();
    renderTagCloud();
    renderWeeklyStats(weekly);
    renderFreshStrip();
    renderNewsMatch(news);
    render();

    els.q.addEventListener("input", debounce(() => {
      state.query = els.q.value;
      state.parsed = window.NYC_PARSE_QUERY(state.query);
      if (state.query) state.sort = "relevance";
      render();
      syncURL();
    }, 120));
    els.sort.addEventListener("change", () => { state.sort = els.sort.value; render(); syncURL(); });
    if (els.surprise) els.surprise.addEventListener("click", () => {
      const list = getResults();
      if (!list.length) {
        // Fall back to the full catalog if filters yield nothing
        const all = state.catalog.datasets;
        if (!all.length) return;
        const pick = all[Math.floor(Math.random() * all.length)];
        window.open(`https://data.cityofnewyork.us/d/${encodeURIComponent(pick.i)}`, "_blank", "noopener");
        return;
      }
      const pick = list[Math.floor(Math.random() * list.length)];
      // Brief visual feedback on the button
      const original = els.surprise.textContent;
      els.surprise.textContent = "🎲 …";
      setTimeout(() => { els.surprise.textContent = original; }, 250);
      window.open(`https://data.cityofnewyork.us/d/${encodeURIComponent(pick.i)}`, "_blank", "noopener");
    });
    function resetAll(scrollTop) {
      state.query = ""; state.activeCat = null; state.sort = "relevance"; state.fresh = "all";
      state.activeAgencies.clear(); state.activeType = null; state.activeTags.clear();
      state.picksOnly = false; state.favsOnly = false;
      state.agencyFilter = "";
      els.q.value = ""; els.sort.value = "relevance"; els.picksOnly.checked = false;
      if (els.favsOnly) els.favsOnly.checked = false;
      if (els.agencySearch) els.agencySearch.value = "";
      state.parsed = window.NYC_PARSE_QUERY("");
      renderCatMap(); renderTypePills(); renderFreshPills(); renderAgencyList(); renderTagCloud(); render();
      history.replaceState(null, "", window.location.pathname);
      if (scrollTop) window.scrollTo({ top: 0, behavior: "smooth" });
    }
    els.clear.addEventListener("click", () => resetAll(false));
    const homeLink = document.getElementById("home-link");
    if (homeLink) homeLink.addEventListener("click", (e) => {
      e.preventDefault();
      resetAll(true);
    });
    els.agencySearch.addEventListener("input", debounce(() => { state.agencyFilter = els.agencySearch.value; renderAgencyList(); }, 80));
    els.agencyToggle.addEventListener("click", () => { state.showAllAgencies = !state.showAllAgencies; renderAgencyList(); });
    els.picksOnly.addEventListener("change", () => { state.picksOnly = els.picksOnly.checked; render(); syncURL(); });
    if (els.favsOnly) els.favsOnly.addEventListener("change", () => { state.favsOnly = els.favsOnly.checked; render(); syncURL(); });
    const clearBtn = document.getElementById("favs-clear");
    if (clearBtn) clearBtn.addEventListener("click", () => {
      if (!confirm(`Clear all ${state.favs.size} favorites? This can't be undone.`)) return;
      state.favs.clear();
      saveFavs(state.favs);
      updateFavCount();
      els.results.querySelectorAll(".fav-btn.on").forEach((b) => { b.classList.remove("on"); b.textContent = "♡"; });
      if (state.favsOnly) render();
    });

    window.addEventListener("hashchange", () => {
      if (window._suppressHash) return;
      loadURL();
      state.parsed = window.NYC_PARSE_QUERY(state.query);
      renderCatMap(); renderTypePills(); renderFreshPills(); renderAgencyList(); renderTagCloud(); render();
    });
  }

  init();
})();
