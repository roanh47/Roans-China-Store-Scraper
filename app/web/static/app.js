/* Roans China Store Scraper — UI.
   Alles wordt met DOM-nodes opgebouwd (titels komen van het web, dus nooit
   als HTML ingevoegd). */

const eur = new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" });
const $ = (id) => document.getElementById(id);

const state = {
  query: "",
  stores: "aliexpress",
  choiceOnly: false,
  useImages: true,
  data: null,
  selected: new Map(), // "store|pid" -> {offer}
  busy: false,
};

const STORE_QUERY = {
  aliexpress: "aliexpress",
  temu: "temu",
  both: "aliexpress,temu",
};

const money = (v) => (v === null || v === undefined ? "—" : eur.format(v));
const key = (o) => `${o.store}|${o.pid}`;

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "href") node.setAttribute("href", v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

/* --- zoeken ---------------------------------------------------------------- */
async function search({ refresh = false } = {}) {
  const query = $("q").value.trim();
  if (!query) {
    $("q").focus();
    return;
  }
  state.query = query;
  state.busy = true;
  $("search-button").disabled = true;
  $("meta").textContent = "bezig…";
  $("empty").hidden = true;

  const params = new URLSearchParams({ q: query, stores: STORE_QUERY[state.stores] });
  if (state.choiceOnly) params.set("choice", "1");
  if (!state.useImages) params.set("noimages", "1");
  if (refresh) params.set("refresh", "1");

  try {
    const response = await fetch(`/api/search?${params}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    state.data = payload;
    for (const k of [...state.selected.keys()]) state.selected.delete(k);
    render(payload);
  } catch (error) {
    $("meta").textContent = "mislukt";
    $("empty").hidden = false;
    $("empty").textContent = `Zoeken mislukt: ${error.message}`;
    $("matches").hidden = true;
    $("results").replaceChildren();
    $("store-status").hidden = true;
  } finally {
    state.busy = false;
    $("search-button").disabled = false;
    updateCart();
  }
}

/* --- renderen -------------------------------------------------------------- */
function render(data) {
  $("meta").textContent =
    `${data.counts.offers} aanbiedingen · ${data.counts.groups} zelfde-product-groep(en) · ` +
    `${data.took_s}s${data.cached ? " (cache)" : ""}`;

  renderStatus(data);
  renderMatches(data);
  renderCards(data);

  if (!data.offers.length) {
    $("empty").hidden = false;
    const notes = data.stores.map((s) => s.note).filter(Boolean);
    $("empty").textContent = notes.length
      ? `Geen aanbiedingen. ${notes.join(" ")}`
      : "Geen aanbiedingen gevonden. Probeer een andere zoekterm.";
  } else {
    $("empty").hidden = true;
  }
}

function renderStatus(data) {
  const box = $("store-status");
  box.replaceChildren();
  for (const store of data.stores) {
    const chip = el("span", { class: `chip ${store.status}` }, [
      el("span", { class: "dot" }),
      el("strong", { text: store.store_label }),
      el("span", { class: "why", text: statusText(store) }),
    ]);
    box.append(chip);
  }
  box.hidden = false;
}

function statusText(store) {
  const counts = `${store.count} resultaten`;
  switch (store.status) {
    case "ok":
      return `${counts} · ${store.elapsed_s ?? "?"}s`;
    case "empty":
      return store.note || "geen resultaten";
    case "blocked":
      return store.note || "geblokkeerd";
    case "skipped":
      return "niet meegenomen";
    case "error":
      return `fout: ${store.error || "onbekend"}`;
    default:
      return store.status;
  }
}

function renderMatches(data) {
  const box = $("matches");
  box.replaceChildren();
  if (!data.groups.length) {
    box.hidden = true;
    return;
  }
  for (const group of data.groups) {
    const head = el("div", { class: "match-head" }, [
      el("strong", { text: `Zelfde product — ${group.size} aanbiedingen` }),
      group.spread !== null && group.spread > 0
        ? el("span", { class: "spread", text: `verschil ${money(group.spread)}` })
        : null,
      el("span", { class: "why", text: (group.reasons || []).join(", ") }),
    ]);
    const row = el(
      "div",
      { class: "grid" },
      group.offers.map((offer) => card(offer, { inGroup: true }))
    );
    box.append(el("div", { class: "match" }, [head, row]));
  }
  box.hidden = false;
}

function renderCards(data) {
  const box = $("results");
  const singles = data.offers.filter((o) => !o.match_id);
  box.replaceChildren(...singles.map((offer) => card(offer, { inGroup: false })));
}

function card(offer, { inGroup }) {
  const off =
    offer.price_before && offer.price && offer.price_before > offer.price
      ? Math.round((1 - offer.price / offer.price_before) * 100)
      : null;

  const checkbox = el("input", {
    type: "checkbox",
    onchange: (event) => {
      if (event.target.checked) state.selected.set(key(offer), offer);
      else state.selected.delete(key(offer));
      updateCart();
    },
  });
  checkbox.checked = state.selected.has(key(offer));

  const bits = [];
  if (offer.cheapest) bits.push(el("span", { class: "badge good", text: "goedkoopste" }));
  if (offer.choice) bits.push(el("span", { class: "badge choice", text: "Choice" }));
  bits.push(el("span", { class: "badge store", text: offer.store_label }));
  if (offer.shipping_text) bits.push(el("span", { class: "badge", text: offer.shipping_text }));
  else if (offer.free_ship_from)
    bits.push(el("span", { class: "badge", text: `gratis vanaf ${money(offer.free_ship_from)}` }));
  if (offer.rating) bits.push(el("span", { class: "badge", text: `★ ${offer.rating}` }));
  if (offer.sold) bits.push(el("span", { class: "badge", text: offer.sold }));
  else if (offer.sold_count) bits.push(el("span", { class: "badge", text: `${offer.sold_count}× verkocht` }));
  if (inGroup) bits.push(el("span", { class: "badge", text: `zelfde product ×${offer.match_size}` }));

  const thumb = el("div", { class: "thumb" }, [
    offer.image
      ? el("img", { src: offer.image, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
      : null,
  ]);

  return el("article", { class: `card${offer.cheapest ? " winner" : ""}` }, [
    el("label", { class: "pick", title: "In mandje" }, [checkbox, el("span", { text: "mandje" })]),
    offer.cheapest ? el("span", { class: "ribbon", text: "goedkoopst" }) : null,
    thumb,
    el("div", { class: "body" }, [
      el("div", { class: "title" }, [
        el("a", { href: offer.url, target: "_blank", rel: "noopener noreferrer", text: offer.title }),
      ]),
      el("div", { class: "bits" }, bits),
      el("div", { class: "prices" }, [
        el("span", { class: "price", text: money(offer.price) }),
        off ? el("span", { class: "off", text: `-${off}%` }) : null,
        offer.price_before ? el("span", { class: "was", text: money(offer.price_before) }) : null,
      ]),
    ]),
  ]);
}

/* --- mandje ---------------------------------------------------------------- */
async function updateCart() {
  const cart = $("cart");
  if (!state.selected.size || !state.data) {
    cart.hidden = true;
    return;
  }
  cart.hidden = false;

  const items = [...state.selected.values()].map((o) => ({ store: o.store, pid: o.pid, qty: 1 }));
  try {
    const response = await fetch("/api/cart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: state.data.query,
        stores: state.data.stores,
        limit: state.data.limit,
        choice_only: state.data.choice_only,
        items,
      }),
    });
    const summary = await response.json();
    if (!response.ok) throw new Error(summary.error || `HTTP ${response.status}`);
    renderCart(summary);
  } catch (error) {
    $("choice-note").textContent = `Mandje rekenen mislukt: ${error.message}`;
  }
}

function renderCart(summary) {
  const threshold = summary.choice_threshold || 10;
  const met = summary.choice_threshold_met;
  const percent = Math.max(0, Math.min(100, (summary.choice_total / threshold) * 100));

  $("choice-total").textContent = `${money(summary.choice_total)} / ${money(threshold)}`;
  $("choice-fill").style.width = `${percent}%`;
  const note = $("choice-note");
  note.className = `gauge-note${met ? " met" : ""}`;
  note.textContent = met
    ? "Choice-drempel gehaald: gratis én snelle verzending op je Choice-artikelen."
    : `nog ${money(summary.choice_missing)} aan Choice-artikelen tot gratis en snelle verzending.`;

  $("cart-lines").replaceChildren(
    ...summary.lines.map((line) =>
      el("li", {}, [
        el("span", { text: `${line.qty}×` }),
        el("span", { class: "line-title", text: line.title }),
        line.note ? el("span", { class: "line-note", text: line.note }) : null,
        el("span", { text: money(line.total) }),
      ])
    )
  );

  $("sum-items").textContent = money(summary.items_total);
  $("sum-ship").textContent = summary.shipping_total
    ? `${money(summary.shipping_total)}${summary.shipping_estimated ? " (schatting)" : ""}`
    : "gratis";
  $("sum-total").textContent = money(summary.total);
  $("cart-notes").replaceChildren(...(summary.notes || []).map((text) => el("li", { text })));
}

/* --- gebeurtenissen -------------------------------------------------------- */
$("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  search();
});

$("store-switch").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-store]");
  if (!button) return;
  state.stores = button.dataset.store;
  for (const other of $("store-switch").querySelectorAll("button")) {
    other.classList.toggle("on", other === button);
  }
  if (state.query) search();
});

$("choice-only").addEventListener("change", (event) => {
  state.choiceOnly = event.target.checked;
  if (state.query) search();
});

$("use-images").addEventListener("change", (event) => {
  state.useImages = event.target.checked;
  if (state.query) search();
});

$("refresh").addEventListener("click", () => {
  if (state.query || $("q").value.trim()) search({ refresh: true });
});

$("cart-clear").addEventListener("click", () => {
  state.selected.clear();
  for (const box of document.querySelectorAll(".pick input")) box.checked = false;
  updateCart();
});
