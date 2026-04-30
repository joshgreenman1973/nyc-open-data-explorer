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
  };

  const state = {
    catalog: null,
    fuse: null,
    activeCat: null,
    query: "",
    sort: "relevance",
    fresh: "all",
    fetchedAt: null,
  };

  const SIZE_RULES = [
    { min: 500, klass: "size-xl" },
    { min: 200, klass: "size-l" },
  ];

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

  function passesFreshness(d) {
    if (state.fresh === "all") return true;
    if (!d.u) return state.fresh === "stale";
    const days = (Date.now() - Date.parse(d.u)) / 86400000;
    if (state.fresh === "30") return days <= 30;
    if (state.fresh === "365") return days <= 365;
    if (state.fresh === "stale") return days > 365;
    return true;
  }

  function renderCatMap() {
    const cats = state.catalog.categories;
    els.catMap.innerHTML = cats.map((c) => {
      const sz = tileSize(c.count);
      const active = state.activeCat === c.name ? " active" : "";
      return `<button class="cat-tile ${sz}${active}" data-cat="${escapeAttr(c.name)}">
        <h3>${escapeHTML(c.name)}</h3>
        <div class="count">${c.count.toLocaleString()}<small>datasets</small></div>
      </button>`;
    }).join("");
    els.catMap.querySelectorAll(".cat-tile").forEach((b) => {
      b.addEventListener("click", () => {
        const c = b.dataset.cat;
        state.activeCat = state.activeCat === c ? null : c;
        renderCatMap();
        render();
      });
    });
  }

  function escapeHTML(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[m]));
  }
  function escapeAttr(s) { return escapeHTML(s); }

  function getResults() {
    const q = state.query.trim();
    let list;
    if (q) {
      const hits = state.fuse.search(q, { limit: 800 });
      list = hits.map((h) => h.item);
    } else {
      list = state.catalog.datasets.slice();
    }
    if (state.activeCat) list = list.filter((d) => d.c === state.activeCat);
    list = list.filter(passesFreshness);

    if (state.sort === "views") list.sort((a, b) => (b.v || 0) - (a.v || 0));
    else if (state.sort === "updated") list.sort((a, b) => (b.u || "").localeCompare(a.u || ""));
    else if (state.sort === "alpha") list.sort((a, b) => a.n.localeCompare(b.n));
    // relevance keeps Fuse order; if no query, fall back to views
    else if (!q) list.sort((a, b) => (b.v || 0) - (a.v || 0));

    return list;
  }

  function renderCard(d) {
    const f = freshnessClass(d.u);
    const url = `https://data.cityofnewyork.us/d/${encodeURIComponent(d.i)}`;
    const summary = d.s ? escapeHTML(d.s) : `<em>No description provided by the publishing agency.</em>`;
    const agency = d.a ? `<span class="agency">${escapeHTML(d.a)}</span>` : `<span class="agency">NYC agency</span>`;
    const type = d.t && d.t !== "dataset" ? `<span class="pill type">${escapeHTML(d.t)}</span>` : "";
    return `<article class="card" data-cat="${escapeAttr(d.c)}">
      <h4><a href="${url}" target="_blank" rel="noopener">${escapeHTML(d.n)}</a></h4>
      <div class="summary">${summary}</div>
      <div class="meta">
        ${agency}
        <span class="pill ${f.klass}">${f.label}</span>
        ${type}
        ${d.v ? `<span>${fmtNum(d.v)} views</span>` : ""}
      </div>
    </article>`;
  }

  function render() {
    const list = getResults();
    const total = state.catalog.datasets.length;
    const filterParts = [];
    if (state.query) filterParts.push(`matching &ldquo;${escapeHTML(state.query)}&rdquo;`);
    if (state.activeCat) filterParts.push(`in <strong>${escapeHTML(state.activeCat)}</strong>`);
    if (state.fresh !== "all") {
      const map = { "30": "updated in last 30 days", "365": "updated in last year", stale: "older than 1 year" };
      filterParts.push(map[state.fresh]);
    }
    const filterText = filterParts.length ? " " + filterParts.join(", ") : "";
    els.stats.innerHTML = `<strong>${list.length.toLocaleString()}</strong> of ${total.toLocaleString()} datasets${filterText}. <span style="color:var(--ink-mute)">Catalog refreshed ${state.fetchedAt}.</span>`;

    const RENDER_CAP = 200;
    if (list.length === 0) {
      els.results.innerHTML = "";
      els.empty.hidden = false;
    } else {
      els.empty.hidden = true;
      const slice = list.slice(0, RENDER_CAP);
      els.results.innerHTML = slice.map(renderCard).join("") +
        (list.length > RENDER_CAP ? `<div class="empty" style="grid-column:1/-1">Showing the first ${RENDER_CAP} of ${list.length.toLocaleString()} matches. Refine your search or pick a category to narrow further.</div>` : "");
    }
  }

  function debounce(fn, ms) {
    let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  async function init() {
    let data;
    try {
      const r = await fetch("data/catalog.min.json", { cache: "no-cache" });
      data = await r.json();
    } catch (e) {
      els.stats.textContent = "Failed to load the catalog. Try refreshing.";
      console.error(e);
      return;
    }
    state.catalog = data;
    state.fetchedAt = (data.fetched_at || "").slice(0, 10) || "recently";

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

    renderCatMap();
    render();

    els.q.addEventListener("input", debounce(() => {
      state.query = els.q.value;
      if (state.query) state.sort = "relevance";
      render();
    }, 120));
    els.sort.addEventListener("change", () => { state.sort = els.sort.value; render(); });
    els.fresh.addEventListener("change", () => { state.fresh = els.fresh.value; render(); });
    els.clear.addEventListener("click", () => {
      state.query = ""; state.activeCat = null; state.sort = "relevance"; state.fresh = "all";
      els.q.value = ""; els.sort.value = "relevance"; els.fresh.value = "all";
      renderCatMap(); render();
    });
  }

  init();
})();
