/* =====================================================================
   Brother'sTrust Travel SPA — flights, hotels, cars, visa, payments, admin.
   No framework, no build step. Hash-routed.
   ===================================================================== */
"use strict";

const state = {
  token: localStorage.getItem("dt_token") || "",
  user: null,
  meta: { airports: [], cabins: [], hotelCities: [], carCities: [], carCats: [], visaCountries: [] },
  flightSel: {},   // {out: flightObj, ret: flightObj}
  sel: {},         // generic selection per module (hotel room, car, visa slot)
};

/* ---------------- utils ---------------- */
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const GHS = n => "GH\u00A2" + Number(n || 0).toLocaleString("en-GH");
const SERVICE_FEE = 100;
const todayISO = () => new Date().toISOString().slice(0, 10);
const addDaysISO = (iso, n) => { const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
const fmtDate = iso => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
const fmtTime = t => { let [h, m] = t.split(":").map(Number); const ap = h >= 12 ? "PM" : "AM"; h = h % 12 || 12; return `${h}:${String(m).padStart(2, "0")} ${ap}`; };
const durFmt = mins => `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`;
const qs = new URLSearchParams(location.hash.split("?")[1] || "");

function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.textContent = msg;
  $("#toast-root").appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(state.token ? { Authorization: "Bearer " + state.token } : {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    openAuthModal("Sign in to continue");
    throw new Error("Sign in to continue");
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-json */ }
  if (!res.ok) {
    const detail = data && data.detail;
    const msg = Array.isArray(detail) ? detail.map(d => d.msg).join("; ")
      : (typeof detail === "string" ? detail : `Request failed (${res.status})`);
    throw new Error(msg);
  }
  return data;
}

function loading(msg = "Loading…") {
  return `<div class="loading"><div class="spinner"></div>${esc(msg)}</div>`;
}
function emptyState(icn, text, cta = "") {
  return `<div class="empty-state"><div class="big">${icon(icn, "ic-2x")}</div><p>${esc(text)}</p>${cta}</div>`;
}

/* ---------------- modal ---------------- */
function openModal(html) {
  $("#modal-card").innerHTML = `<button class="modal-close" id="modal-close" aria-label="Close">${icon("x")}</button>` + html;
  const root = $("#modal-root");
  root.hidden = false;
  root.style.display = "flex";   // inline — cannot be overridden by stale CSS
  $("#modal-close").onclick = closeModal;
}
function closeModal() {
  const root = $("#modal-root");
  root.hidden = true;
  root.style.display = "none";   // belt-and-braces alongside the [hidden] CSS rule
  $("#modal-card").innerHTML = "";
}
$("#modal-backdrop").addEventListener("click", closeModal);

/* ---------------- auth ---------------- */
function openAuthModal(note = "") {
  openModal(`
    <h3 class="mb">${esc(note) || "Welcome to Brother'sTrust Travel"}</h3>
    <div class="auth-tabs">
      <button id="tab-login" class="active">Sign in</button>
      <button id="tab-register">Create account</button>
    </div>
    <form id="auth-form" class="grid" style="gap:.8rem">
      <div class="field" id="f-name" hidden><label>Full name</label><input name="full_name" required minlength="2" placeholder="Ada Obi"></div>
      <div class="field"><label>Email</label><input name="email" type="email" required placeholder="you@email.com"></div>
      <div class="field" id="f-phone" hidden><label>Phone</label><input name="phone" placeholder="+234 801 234 5678"></div>
      <input name="website" type="text" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0">
      <div class="field"><label>Password</label><input name="password" type="password" required minlength="6"></div>
      <button class="btn btn-primary btn-block" id="auth-submit">Sign in</button>
      <div class="center" id="forgot-wrap"><a href="#" id="link-forgot" class="small">Forgot password?</a></div>
    </form>
    <div id="google-wrap" class="hidden">
      <div class="center" style="margin:.7rem 0 .5rem;color:var(--muted)"><span style="border-top:1px solid var(--line);width:70px;display:inline-block;vertical-align:middle;margin-right:.6rem"></span>or<span style="border-top:1px solid var(--line);width:70px;display:inline-block;vertical-align:middle;margin-left:.6rem"></span></div>
      <button class="btn btn-outline btn-block" id="google-btn"><span class="g-logo">G</span> Continue with Google</button>
    </div>
    <div id="forgot-view" class="hidden">
      <p class="muted small mb">Enter your account email and we'll send you a reset link (valid for 1 hour).</p>
      <form id="forgot-form" class="grid" style="gap:.8rem">
        <div class="field"><label>Email</label><input name="email" type="email" required placeholder="you@email.com"></div>
        <button class="btn btn-primary btn-block">Send reset link</button>
      </form>
      <div id="forgot-result" class="hidden mt"></div>
      <div class="center mt"><a href="#" id="link-back-login" class="small">← Back to sign in</a></div>
    </div>`);
  let mode = "login";
  const swap = m => {
    mode = m;
    $("#tab-login").classList.toggle("active", m === "login");
    $("#tab-register").classList.toggle("active", m === "register");
    $("#f-name").hidden = $("#f-phone").hidden = m === "login";
    $("#auth-submit").textContent = m === "login" ? "Sign in" : "Create account";
  };
  $("#tab-login").onclick = () => swap("login");
  $("#tab-register").onclick = () => swap("register");
  $("#link-forgot").onclick = e => { e.preventDefault(); showForgot(); };
  $("#link-back-login").onclick = e => { e.preventDefault(); $("#auth-form").classList.remove("hidden"); $("#forgot-wrap").classList.remove("hidden"); $("#forgot-view").classList.add("hidden"); };
  const showForgot = () => { $("#auth-form").classList.add("hidden"); $("#forgot-wrap").classList.add("hidden"); $("#forgot-view").classList.remove("hidden"); };
  api("/auth/firebase-config").then(() => { $("#google-wrap").classList.remove("hidden");
    $("#google-btn").onclick = signInWithGoogle; }).catch(() => {});
  $("#forgot-form").onsubmit = async e => {
    e.preventDefault();
    const btn = e.target.querySelector("button");
    btn.disabled = true; btn.textContent = "Sending…";
    try {
      const r = await api("/auth/forgot-password", { method: "POST", body: { email: new FormData(e.target).get("email") } });
      $("#forgot-result").classList.remove("hidden");
      $("#forgot-result").innerHTML = r.dev_reset_link
        ? `<div class="card card-pad" style="background:var(--gold-soft)"><b>Demo mode</b> (no email service configured). Use this link:<br>
           <a class="small" href="${r.dev_reset_link.replace(location.origin, "")}">${r.dev_reset_link}</a>
           <div class="mt"><a class="btn btn-primary btn-sm" href="${r.dev_reset_link.replace(location.origin, "")}">Open reset page</a></div></div>`
        : `<p class="small" style="color:var(--green)">${esc(r.detail)}</p>`;
      e.target.reset();
    } catch (err) { toast(err.message, "error"); }
    btn.disabled = false; btn.textContent = "Send reset link";
  };
  $("#auth-form").onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    const btn = $("#auth-submit");
    btn.disabled = true;
    try {
      const r = await api("/auth/" + (mode === "login" ? "login" : "register"), { method: "POST", body });
      if (!r.access_token) { toast("Registration could not be completed", "error"); btn.disabled = false; return; }
      state.token = r.access_token;
      localStorage.setItem("dt_token", r.access_token);
      state.user = r.user;
      closeModal(); renderChrome();
      toast(`Welcome${mode === "register" ? "" : " back"}, ${r.user.full_name.split(" ")[0]}!`, "success");
      route();
    } catch (err) { toast(err.message, "error"); }
    btn.disabled = false;
  };
}

function renderChrome() {
  const loggedIn = !!state.user;
  $("#btn-auth").hidden = loggedIn;
  $("#user-chip").hidden = !loggedIn;
  $("#nav-admin").hidden = !(loggedIn && state.user.role === "admin");
  $("#menu-admin").hidden = !(loggedIn && state.user.role === "admin");
  if (loggedIn) {
    $("#user-avatar").textContent = (state.user.full_name || "U")[0].toUpperCase();
    $("#user-menu-name").textContent = state.user.full_name;
  }
}
$("#btn-auth").onclick = () => openAuthModal();
$("#user-avatar").onclick = e => { e.stopPropagation(); $("#user-menu").hidden = !$("#user-menu").hidden; };
document.addEventListener("click", () => { const m = $("#user-menu"); if (m) m.hidden = true; });
$("#user-menu").addEventListener("click", e => e.stopPropagation());
$("#btn-logout").onclick = () => {
  state.token = ""; state.user = null;
  localStorage.removeItem("dt_token");
  renderChrome(); location.hash = "#/"; route();
  toast("Signed out");
};

async function loadMe() {
  if (!state.token) return;
  try { state.user = await api("/auth/me"); }
  catch { state.token = ""; localStorage.removeItem("dt_token"); }
  renderChrome();
}

/* ---------------- meta ---------------- */
async function loadMeta() {
  const [fm, hm, cm, vm] = await Promise.all([
    api("/meta/flights").catch(() => null),
    api("/meta/hotels").catch(() => null),
    api("/meta/cars").catch(() => null),
    api("/meta/visa").catch(() => null),
  ]);
  if (fm) { state.meta.airports = fm.airports || []; state.meta.cabins = fm.cabins || []; }
  if (hm) state.meta.hotelCities = hm.cities || [];
  if (cm) { state.meta.carCities = cm.cities || []; state.meta.carCats = cm.categories || []; }
  if (vm) state.meta.visaCountries = vm.countries || [];
}
const airportDatalist = () => {
  const base = state.meta.airports
    .map(a => `<option value="${a.code}">${esc(a.city)}, ${esc(a.country)}</option>`).join("");
  const seen = new Set();
  const countries = state.meta.airports
    .filter(a => a.country && !seen.has(a.country) && seen.add(a.country))
    .map(a => `<option value="${esc(a.country)}">All ${esc(a.country)} airports (${a.code} ${esc(a.city)})</option>`).join("");
  return base + countries;
};
const cityDatalist = () => state.meta.hotelCities.map(c => `<option value="${esc(c)}">`).join("");
const airportOpts = sel => state.meta.airports
  .map(a => `<option value="${a.code}" ${a.code === sel ? "selected" : ""}>${a.city} (${a.code})</option>`).join("");
const cityOpts = (cities, sel) => cities
  .map(c => `<option ${c === sel ? "selected" : ""}>${c}</option>`).join("");

/* =====================================================================
   HOME
   ===================================================================== */
function viewHome() {
  $("#app").innerHTML = `
  <section class="hero"><div class="hero-inner">
    <h1>Book flights, hotels, cars & visas — all in one place</h1>
    <p class="lead">Brother'sTrust Travel gets you moving: instant flight deals, handpicked hotels, reliable car rentals and expert visa processing for Ghanaians.</p>
    <div style="margin-top:1.4rem"><button class="btn btn-gold" style="padding:.85rem 2.4rem;font-size:1.05rem" onclick="document.querySelector('.search-shell').scrollIntoView({behavior:'smooth'})">Plan your trip →</button></div>
    <div class="hero-badges">
      <span>${icon("plane","ic-sm")} 14 flight routes</span><span>${icon("hotel","ic-sm")} 26 partner hotels</span>
      <span>${icon("car","ic-sm")} 7 rental cities</span><span>${icon("passport","ic-sm")} 13 visa destinations</span><span>${icon("users","ic-sm")} 15,000+ recruited</span><span>${icon("lock","ic-sm")} Secure payments</span>
    </div>
  </div></section>

  <div class="search-shell"><div class="search-card">
    <div class="search-tabs" id="home-tabs">
      <button data-t="flights" class="active">${icon("plane","ic-sm")} Flights</button>
      <button data-t="hotels">${icon("hotel","ic-sm")} Hotels</button>
      <button data-t="cars">${icon("car","ic-sm")} Cars</button>
      <button data-t="visa">${icon("passport","ic-sm")} Visa</button>
    </div>
    <div id="home-form"></div>
  </div></div>

  <div class="wrap mt-2">
    <h2 class="section-title">Popular right now</h2>
    <p class="section-sub">Deals our travellers love this week</p>
    <div class="grid grid-3" id="popular"></div>
  </div>`;

  const renderForm = t => {
    $$("#home-tabs button").forEach(b => b.classList.toggle("active", b.dataset.t === t));
    const box = $("#home-form");
    if (t === "flights") box.innerHTML = flightSearchForm({ compact: true });
    if (t === "hotels") box.innerHTML = hotelSearchForm({ compact: true });
    if (t === "cars") box.innerHTML = carSearchForm({ compact: true });
    if (t === "visa") box.innerHTML = visaSearchForm({ compact: true });
    wireFlightForm(box); wireHotelForm(box); wireCarForm(box); wireVisaForm(box);
  };
  $$("#home-tabs button").forEach(b => b.onclick = () => renderForm(b.dataset.t));
  renderForm("flights");

  $("#popular").innerHTML = [
    ["Lagos → London", "From GH¢5,950", "Round-trip deals on British Airways & Qatar", "#/flights?origin=LOS&dest=LHR", "plane"],
    ["Dubai escape", "Hotels from GH¢1,650/night", "Burj views, desert safaris, shopping festivals", "#/hotels?city=Dubai", "hotel"],
    ["Nigeria by road & air", "Visa-free (ECOWAS)", "Lagos hotels + weekend car rentals", "#/visa?code=NG", "passport"],
    ["Abuja weekend", "Flights from GH¢470", "Late-morning departures, business cabins", "#/flights?origin=LOS&dest=ABV", "plane"],
    ["Work abroad", "UAE \u00b7 Saudi \u00b7 Qatar \u00b7 Europe", "Direct employment visas \u2014 15,000+ candidates placed", "#/visa", "users"],
    ["Luxury SUV hire", "From GH¢1,500/day", "Airport pickup in Lagos, Abuja & Dubai", "#/cars?city=Lagos", "car"],
  ].map(([t, p, d, href, icn]) => `
    <a class="card card-pad" href="${href}" style="display:block;color:inherit">
      <div class="pop-ic">${icon(icn, "ic-2x")}</div>
      <h3 style="margin:.4rem 0 .2rem">${t}</h3>
      <div style="color:var(--green);font-weight:800">${p}</div>
      <p class="muted small mt">${d}</p>
    </a>`).join("");
}

/* =====================================================================
   FLIGHTS
   ===================================================================== */
function flightSearchForm(p = {}) {
  return `
  <form id="flight-form" class="grid" style="gap:.9rem">
    <div class="row">
      <label class="small"><input type="radio" name="trip" value="one_way" ${p.trip !== "round_trip" ? "checked" : ""}> One way</label>
      <label class="small"><input type="radio" name="trip" value="round_trip" ${p.trip === "round_trip" ? "checked" : ""}> Round trip</label>
    </div>
    <div class="form-grid">
      <div class="field"><label>From</label><input name="origin" list="dl-airports" maxlength="3" required style="text-transform:uppercase" placeholder="Type city or code" value="${esc(p.origin || "ACC")}"></div>
      <div class="field"><label>To</label><input name="dest" list="dl-airports" maxlength="3" required style="text-transform:uppercase" placeholder="Type city or code" value="${esc(p.dest || "LOS")}"></div>
      <datalist id="dl-airports">${airportDatalist()}</datalist>
      <div class="field"><label>Departure</label><input type="date" name="date" value="${p.date || addDaysISO(todayISO(), 7)}" min="${todayISO()}"></div>
      <div class="field" id="f-ret" ${p.trip === "round_trip" ? "" : "hidden"}><label>Return</label><input type="date" name="ret" value="${p.ret || addDaysISO(todayISO(), 10)}" min="${todayISO()}"></div>
      <div class="field"><label>Cabin</label><select name="cabin">${state.meta.cabins.map(c => `<option value="${c.id}" ${c.id === (p.cabin || "economy") ? "selected" : ""}>${c.label}</option>`).join("")}</select></div>
      <div class="field"><label>Bags (per traveler)</label><select name="bags">${[0,1,2,3].map(n => `<option value="${n}" ${n === (p.bags || 0) ? "selected" : ""}>${n === 0 ? "No bags" : n + " bag" + (n > 1 ? "s" : "")}</option>`).join("")}</select></div>
      <div class="field"><label>Adults</label><input type="number" name="adults" min="1" max="9" value="${p.adults || 1}"></div>
      <div class="field"><label>Children</label><input type="number" name="children" min="0" max="8" value="${p.children || 0}"></div>
      <div class="field"><label>Infants</label><input type="number" name="infants" min="0" max="4" value="${p.infants || 0}"></div>
    </div>
    <div class="row">
      <button class="btn btn-gold btn-lg" style="padding:.8rem 2.2rem">${icon("search","ic-sm")} Search flights</button>
      <button type="button" class="btn btn-outline btn-sm" id="airport-codes-btn">${icon("info","ic-sm")} All airport codes</button>
    </div>
  </form>`;
}

function wireFlightForm(root) {
  const form = $("#flight-form", root);
  if (!form) return;
  form.trip.forEach(r => r.onchange = () => { $("#f-ret", form).hidden = form.trip.value !== "round_trip"; });
  const codesBtn = $("#airport-codes-btn", form);
  if (codesBtn) codesBtn.onclick = e => { e.preventDefault(); openModal(airportCodesHtml()); wireAirportCodes(); };
  form.onsubmit = e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(form).entries());
    const resolveAirport = (raw) => {
      const q = (raw || "").trim().toLowerCase();
      if (!q) return "";
      const ap = state.meta.airports;
      const byCode = ap.find(a => a.code.toLowerCase() === q);
      if (byCode) return byCode.code;
      const byCity = ap.find(a => a.city.toLowerCase() === q) || ap.find(a => a.city.toLowerCase().includes(q));
      if (byCity) return byCity.code;
      const byCountry = ap.find(a => (a.country || "").toLowerCase() === q) || ap.find(a => (a.country || "").toLowerCase().includes(q));
      if (byCountry) return byCountry.code;
      return "";
    };
    f.origin = resolveAirport(f.origin);
    f.dest = resolveAirport(f.dest);
    form.origin.value = f.origin;   // show the converted code
    form.dest.value = f.dest;
    if (!f.origin || !f.dest) return toast("Enter a city or country (e.g. Accra, Ghana, Dubai) or pick from the suggestions", "error");
    if (f.origin === f.dest) return toast("Origin and destination must differ", "error");
    if (f.trip === "round_trip" && f.ret < f.date) return toast("Return date can't be before departure", "error");
    location.hash = `#/flights?origin=${f.origin}&dest=${f.dest}&date=${f.date}&ret=${f.ret || ""}&trip=${f.trip}&cabin=${f.cabin}&bags=${f.bags || 0}&adults=${f.adults}&children=${f.children}&infants=${f.infants}`;
  };
}

function legRow(f) {
  return `
    <div class="flight-main">
      <div class="airline-badge" style="background:${f.airline_color}">${f.airline_code}</div>
      <div>
        <div style="font-weight:700">${f.airline} · ${f.flight_no}</div>
        <div class="muted small">${f.aircraft} · ${f.cabin}</div>
      </div>
      <div class="flight-times">
        <div><div class="t">${fmtTime(f.departure)}</div><div class="muted small">${f.origin}</div></div>
        <div class="flight-leg-line"><span class="dur">${durFmt(f.duration_min)}</span><span class="bar">${icon("plane")}</span>
          <span class="stops-tag ${f.stops ? "stop" : "direct"}">${f.stops ? f.stops + " stop" : "Direct"}</span></div>
        <div><div class="t">${fmtTime(f.arrival)}${f.arrives_next_day ? " ⁺¹" : ""}</div><div class="muted small">${f.dest}</div></div>
      </div>
      <div style="margin-left:auto" class="flight-price">
        <div class="amount">${GHS(f.total)}</div>
        <div class="muted small">per traveller</div>
      </div>
      <button class="btn btn-primary btn-sm" data-key="${f.flight_key}" data-leg="${f.origin === state.flightSel.out?.origin ? "ret" : "out"}">Select</button>
    </div>`;
}

function viewFlights(params) {
  const p = {
    origin: params.get("origin") || "ACC", dest: params.get("dest") || "LOS",
    date: params.get("date") || addDaysISO(todayISO(), 7),
    ret: params.get("ret") || "", trip: params.get("trip") || "one_way",
    cabin: params.get("cabin") || "economy", bags: +(params.get("bags") || 0),
    adults: +(params.get("adults") || 1), children: +(params.get("children") || 0), infants: +(params.get("infants") || 0),
  };
  state.flightSel = {};
  const app = $("#app");
  app.innerHTML = `<div class="wrap">
    <div class="card card-pad mb">${flightSearchForm(p)}</div>
    <div id="flight-results">${loading("Searching flights…")}</div>
    <div id="pax-form"></div>
  </div>`;
  wireFlightForm(app);

  const renderResults = async () => {
    const box = $("#flight-results");
    box.innerHTML = loading("Searching flights…");
    try {
      const out = await api(`/flights/search?origin=${p.origin}&dest=${p.dest}&date=${p.date}&cabin=${p.cabin}`);
      let html = `<div class="result-head">
        <div class="route-line"><span class="code">${p.origin}</span> → <span class="code">${p.dest}</span>
          <span class="muted" style="font-weight:500">${fmtDate(p.date)} · ${out.flights.length} flights · ${p.adults + p.children} traveller(s) · ${out.flights[0].cabin}</span></div>
      </div>
      <div class="row" id="carrier-filter" style="margin:.7rem 0 .2rem"></div>
      <div class="search-tabs" id="ftabs" style="margin-bottom:.6rem">
        ${[["cheap", "Cheapest"], ["fast", "Fastest"], ["early", "Earliest"]].map(([k, label], i) =>
          `<button type="button" data-tab="${k}" class="${i === 0 ? "active" : ""}">${label}</button>`).join("")}
      </div>
      <div class="grid" style="gap:.7rem" id="out-list"></div>
      <div id="ret-wrap"></div><div id="sel-actions" class="mt"></div>`;
      const sortFns = { cheap: (a, b) => a.total - b.total,
                        fast: (a, b) => a.duration_min - b.duration_min,
                        early: (a, b) => a.departure.localeCompare(b.departure) };
      const renderTab = (key) => {
        const flights = [...out.flights].sort(sortFns[key]);
        $("#out-list").innerHTML = flights.map(f => `<div class="card flight-card" data-carrier="${f.airline}">${legRow(f)}</div>`).join("");
        $$("#out-list [data-key]").forEach(b => b.onclick = () => pickLeg(flights.find(f => f.flight_key === b.dataset.key), "out", p));
      };
      box.innerHTML = html;
      $$("#ftabs button").forEach(tb => tb.onclick = () => {
        $$("#ftabs button").forEach(x => x.classList.toggle("active", x === tb));
        renderTab(tb.dataset.tab);
      });
      renderTab("cheap");
      const carriers = [...new Set(out.flights.map(f => f.airline))].sort();
      const cf = $("#carrier-filter");
      cf.innerHTML = `<button class="slot-chip sel" data-car="" style="padding:.32rem .75rem">All airlines (${out.flights.length})</button>` +
        carriers.map(c => `<button class="slot-chip" data-car="${esc(c)}" style="padding:.32rem .75rem">${esc(c)}</button>`).join("");
      $$("#carrier-filter .slot-chip").forEach(ch => ch.onclick = () => {
        $$("#carrier-filter .slot-chip").forEach(x => x.classList.toggle("sel", x === ch));
        const v = ch.dataset.car;
        $$("#flight-results .flight-card").forEach(card => {
          card.style.display = (!v || card.dataset.carrier === v) ? "" : "none";
        });
      });
      // (outbound list wiring now lives in renderTab, called above)
    } catch (err) {
      box.innerHTML = emptyState("plane", err.message);
    }
  };

  const pickLeg = (f, leg, p) => {
    state.flightSel[leg] = f;
    toast(`${leg === "out" ? "Outbound" : "Return"} added to cart: ${f.airline} ${f.flight_no}`, "success");
    renderSelection(p);
  };

  const renderSelection = async p => {
    const acts = $("#sel-actions");
    if (!state.flightSel.out) { acts.innerHTML = ""; return; }
    // selection → floating cart (appears with outbound, updates with return)
    const legs = [state.flightSel.out, state.flightSel.ret].filter(Boolean);
    const mult = p.adults + 0.75 * p.children + 0.1 * p.infants;
    const fare = legs.reduce((s, l) => s + l.fare, 0);
    const taxes = legs.reduce((s, l) => s + l.taxes, 0);
    const paxCount = p.adults + p.children + p.infants;
    const bagsCost = (p.bags || 0) * paxCount * 150;
    const total = Math.round(fare * mult) + Math.round(taxes * mult) + SERVICE_FEE + bagsCost;
    const ready = p.trip !== "round_trip" || !!state.flightSel.ret;
    showCart({
      icon: "plane",
      title: legs.map(l => `${l.origin} → ${l.dest}`).join(" · "),
      sub: `${legs.map(l => `${l.airline} ${l.flight_no}`).join("  +  ")} · ${fmtDate(legs[0].date)}${legs.length > 1 ? " · round trip" : ""}${(p.bags || 0) ? ` · ${p.bags} bag(s)/traveler` : ""}${ready ? "" : " · pick your return below"}`,
      amount: total,
      cta: ready ? "Enter traveler details →" : "Select your return flight…",
      onContinue: () => {
        if (!ready) { toast("Pick your return flight below to continue"); return; }
        openModal(flightFormHtml(p, legs, total));
        bindFlightForm($("#flight-pax-form"), p, legs);
      },
    });
    acts.innerHTML = "";
    $("#pax-form").innerHTML = "";
    if (!ready) {
      acts.innerHTML = `<div class="card card-pad"><b>${icon("check-circle","ic-sm")} Outbound added to your cart.</b> <span class="muted">Now pick your return flight below:</span></div>`;
      try {
        const ret = await api(`/flights/search?origin=${p.dest}&dest=${p.origin}&date=${p.ret || p.date}&cabin=${p.cabin}`);
        $("#ret-wrap").innerHTML = `<div class="return-pick"><h4>Return · ${fmtDate(p.ret || p.date)}</h4>
          <div class="grid" style="gap:.7rem">${ret.flights.map(f => `<div class="card flight-card" data-carrier="${f.airline}">${legRow(f)}</div>`).join("")}</div></div>`;
        $$("#ret-wrap [data-key]").forEach(b => b.onclick = () => pickLeg(ret.flights.find(f => f.flight_key === b.dataset.key), "ret", p));
      } catch (err) { $("#ret-wrap").innerHTML = emptyState("plane", err.message); }
    } else {
      $("#ret-wrap").innerHTML = "";
    }
  };
  renderResults();
}

/* =====================================================================
   HOTELS
   ===================================================================== */
function hotelSearchForm(p = {}) {
  return `
  <form id="hotel-form" class="grid" style="gap:.9rem">
    <div class="form-grid">
      <div class="field"><label>Destination</label><input name="city" list="dl-cities" required placeholder="Type any city" value="${esc(p.city || "Accra")}"></div>
      <datalist id="dl-cities">${cityDatalist()}</datalist>
      <div class="field"><label>Check-in</label><input type="date" name="checkin" value="${p.checkin || addDaysISO(todayISO(), 7)}" min="${todayISO()}"></div>
      <div class="field"><label>Check-out</label><input type="date" name="checkout" value="${p.checkout || addDaysISO(todayISO(), 9)}" min="${todayISO()}"></div>
      <div class="field"><label>Rooms</label><input type="number" name="rooms" min="1" max="5" value="${p.rooms || 1}"></div>
      <div class="field"><label>Guests</label><input type="number" name="guests" min="1" max="10" value="${p.guests || 2}"></div>
    </div>
    <div><button class="btn btn-gold" style="padding:.8rem 2.2rem">${icon("search","ic-sm")} Search hotels</button></div>
  </form>`;
}
function wireHotelForm(root) {
  const form = $("#hotel-form", root);
  if (!form) return;
  form.onsubmit = e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(form).entries());
    if (f.checkout <= f.checkin) return toast("Check-out must be after check-in", "error");
    location.hash = `#/hotels?city=${encodeURIComponent(f.city)}&checkin=${f.checkin}&checkout=${f.checkout}&rooms=${f.rooms}&guests=${f.guests}`;
  };
}

function viewHotels(params) {
  const p = {
    city: params.get("city") || "Lagos",
    checkin: params.get("checkin") || addDaysISO(todayISO(), 7),
    checkout: params.get("checkout") || addDaysISO(todayISO(), 9),
    rooms: +(params.get("rooms") || 1), guests: +(params.get("guests") || 2),
  };
  const app = $("#app");
  app.innerHTML = `<div class="wrap">
    <div class="card card-pad mb">${hotelSearchForm(p)}</div>
    <div id="hotel-results">${loading("Finding hotels…")}</div>
    <div id="hotel-form-box"></div>
  </div>`;
  wireHotelForm(app);

  (async () => {
    const box = $("#hotel-results");
    try {
      const r = await api(`/hotels/search?city=${encodeURIComponent(p.city)}&checkin=${p.checkin}&checkout=${p.checkout}&rooms=${p.rooms}&guests=${p.guests}`);
      box.innerHTML = `<div class="result-head"><div class="route-line">${icon("hotel","ic-md")} ${esc(r.city)}
        <span class="muted" style="font-weight:500">${fmtDate(r.checkin)} → ${fmtDate(r.checkout)} · ${r.nights} night(s) · ${r.rooms} room(s) · ${r.guests} guest(s)</span></div></div>
        <div class="grid grid-2">${r.hotels.map(h => `
        <div class="card">
          <div class="hotel-cover cover-${h.cover}"><span class="stars">${icon("star").repeat(h.stars)}</span><h3>${esc(h.name)}</h3></div>
          <div class="card-pad">
            <div class="muted small">${icon("pin","ic-xs")} ${esc(h.area)}, ${esc(h.city)} · <span class="stars">${icon("star")}</span> ${h.rating} (${h.reviews.toLocaleString()} reviews)</div>
            ${h.room_options.map(room => `
              <div class="room-row ${room.sold_out ? "soldout" : ""}">
                <div>
                  <b>${esc(room.type)}</b> <span class="muted small">· ${room.size} · sleeps ${room.occupancy}</span>
                  <div class="perk">${room.perks.join(" · ")}</div>
                  <div class="small" style="color:${room.available <= 2 ? "var(--red)" : "var(--green)"};font-weight:700">
                    ${room.sold_out ? "Sold out for these dates" : room.available + " left at this price"}</div>
                </div>
                <div class="right">
                  <div class="price-lg">${GHS(room.pricing.total)}</div>
                  <div class="muted small">for ${r.nights} night(s), ${r.rooms} room(s) incl. VAT</div>
                  ${room.sold_out ? "" : `<button class="btn btn-primary btn-sm mt" data-h="${h.id}" data-r="${esc(room.type)}">Book</button>`}
                </div>
              </div>`).join("")}
          </div>
        </div>`).join("")}</div>`;
      $$("#hotel-results [data-h]").forEach(b => b.onclick = () => {
        const hotel = r.hotels.find(h => h.id === b.dataset.h);
        const room = hotel.room_options.find(x => x.type === b.dataset.r);
        renderHotelBooking(hotel, room, p, r.nights);
      });
    } catch (err) { box.innerHTML = emptyState("hotel", err.message); }
  })();
}

function renderHotelBooking(hotel, room, p, nights) {
  $("#hotel-results").innerHTML = "";
  $("#hotel-form-box").innerHTML = `
  <div class="grid" style="grid-template-columns:1.6fr 1fr;align-items:start" id="hotel-grid">
    <div class="card card-pad">
      <h3 class="section-title" style="font-size:1.2rem">Guest & payment details</h3>
      <p class="muted small mb">${icon("pin","ic-sm")} ${esc(hotel.name)} · ${esc(room.type)} · ${fmtDate(p.checkin)} → ${fmtDate(p.checkout)}</p>
      <form id="hotel-book-form" class="grid" style="gap:.8rem">
        <div class="field"><label>Lead guest name</label><input name="guest_name" required value="${esc(state.user?.full_name || "")}"></div>
        <div class="field-row">
          <div class="field"><label>Email</label><input name="contact_email" type="email" required value="${esc(state.user?.email || "")}"></div>
          <div class="field"><label>Phone</label><input name="contact_phone" required pattern="[+0-9][0-9\-\s]{6,19}" title="Enter a valid phone number (7+ digits)" value="${esc(state.user?.phone || "")}"></div>
        </div>
        <div class="field"><label>Special requests (optional)</label><textarea name="special_requests" rows="2" placeholder="Early check-in, airport shuttle…"></textarea></div>
        <button class="btn btn-primary btn-block">Continue to payment · ${GHS(room.pricing.total)}</button>
      </form>
    </div>
    <div class="summary-card">
      <h4 class="mb">Price summary</h4>
      <div class="sum-row"><span>${GHS(room.price)} × ${nights} night(s) × ${p.rooms} room(s)</span><span>${GHS(room.pricing.subtotal)}</span></div>
      <div class="sum-row"><span>VAT (15%)</span><span>${GHS(room.pricing.vat)}</span></div>
      <div class="sum-row total"><span>Total</span><span>${GHS(room.pricing.total)}</span></div>
      <p class="muted small mt">Free cancellation up to 48h before check-in (90% refund).</p>
    </div>
  </div>
  <style>@media(max-width:860px){#hotel-grid{grid-template-columns:1fr !important}}</style>`;
  $("#hotel-book-form").onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const btn = e.target.querySelector("button");
    btn.disabled = true;
    try {
      const r = await api("/bookings/hotel", { method: "POST", body: {
        hotel_id: hotel.id, room_type: room.type, room_key: room.rate_key || null, checkin: p.checkin, checkout: p.checkout,
        rooms: p.rooms, guests: p.guests, guest_name: fd.get("guest_name"),
        contact_email: fd.get("contact_email"), contact_phone: fd.get("contact_phone"),
        special_requests: fd.get("special_requests"),
      }});
      toast("Reservation created — complete payment to confirm", "success");
      location.hash = `#/pay/${r.reference}`;
    } catch (err) { toast(err.message, "error"); btn.disabled = false; }
  };
}

/* =====================================================================
   CARS
   ===================================================================== */
function carSearchForm(p = {}) {
  return `
  <form id="car-form" class="grid" style="gap:.9rem">
    <div class="form-grid">
      <div class="field"><label>Pickup city</label><select name="city">${cityOpts(state.meta.carCities.map(c => c.city), p.city || "Lagos")}</select></div>
      <div class="field"><label>Pickup date</label><input type="date" name="pickup_date" value="${p.pickup_date || addDaysISO(todayISO(), 7)}" min="${todayISO()}"></div>
      <div class="field"><label>Return date</label><input type="date" name="return_date" value="${p.return_date || addDaysISO(todayISO(), 9)}" min="${addDaysISO(todayISO(), 1)}"></div>
    </div>
    <div><button class="btn btn-gold" style="padding:.8rem 2.2rem">${icon("search","ic-sm")} Search cars</button></div>
  </form>`;
}
function wireCarForm(root) {
  const form = $("#car-form", root);
  if (!form) return;
  form.onsubmit = e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(form).entries());
    if (f.return_date <= f.pickup_date) return toast("Return date must be after pickup", "error");
    location.hash = `#/cars?city=${encodeURIComponent(f.city)}&pickup_date=${f.pickup_date}&return_date=${f.return_date}`;
  };
}

const CAR_ICON = { economy: "car", compact_suv: "car", premium: "car", luxury_suv: "car", van: "van", convertible: "car" };

function viewCars(params) {
  const p = {
    city: params.get("city") || "Lagos",
    pickup_date: params.get("pickup_date") || addDaysISO(todayISO(), 7),
    return_date: params.get("return_date") || addDaysISO(todayISO(), 9),
  };
  const app = $("#app");
  app.innerHTML = `<div class="wrap">
    <div class="card card-pad mb">${carSearchForm(p)}</div>
    <div id="car-results">${loading("Checking fleets…")}</div>
    <div id="car-form-box"></div>
  </div>`;
  wireCarForm(app);

  (async () => {
    const box = $("#car-results");
    try {
      const r = await api(`/cars/search?city=${encodeURIComponent(p.city)}&pickup_date=${p.pickup_date}&return_date=${p.return_date}`);
      box.innerHTML = `<div class="result-head"><div class="route-line">${icon("car","ic-md")} ${esc(r.city)}
        <span class="muted" style="font-weight:500">${fmtDate(r.pickup_date)} → ${fmtDate(r.return_date)} · ${r.days} day(s) · supplied by ${esc(r.supplier)}</span></div></div>
        <div class="grid grid-2">${r.cars.map(c => `
        <div class="card card-pad ${c.sold_out ? "soldout" : ""}">
          <div class="row">
            <div class="car-emoji">${icon(CAR_ICON[c.code] || "car", "ic-lg")}</div>
            <div style="flex:1">
              <h3>${esc(c.name)}</h3>
              <div class="muted small">${esc(c.examples)}</div>
              <div class="car-specs"><span>${icon("user","ic-xs")} ${c.seats} seats</span><span>${icon("bag","ic-xs")} ${c.bags} bags</span><span>${icon("gear","ic-xs")} ${c.transmission}</span></div>
              <div class="small mt" style="color:${c.available <= 1 ? "var(--red)" : "var(--green)"};font-weight:700">
                ${c.sold_out ? "Sold out for these dates" : c.available + " vehicle(s) available"}</div>
            </div>
            <div class="right">
              <div class="price-lg">${GHS(c.daily_rate)}</div>
              <div class="muted small">per day</div>
              <div class="small"><b>${GHS(c.pricing.total)}</b> total</div>
              ${c.sold_out ? "" : `<button class="btn btn-primary btn-sm mt" data-cat="${c.code}">Book</button>`}
            </div>
          </div>
        </div>`).join("")}</div>`;
      $$("#car-results [data-cat]").forEach(b => b.onclick = () => {
        const car = r.cars.find(c => c.code === b.dataset.cat);
        renderCarBooking(car, p);
      });
    } catch (err) { box.innerHTML = emptyState("car", err.message); }
  })();
}

function renderCarBooking(car, p) {
  $("#car-results").innerHTML = "";
  $("#car-form-box").innerHTML = `
  <div class="grid" style="grid-template-columns:1.6fr 1fr;align-items:start" id="car-grid">
    <div class="card card-pad">
      <h3 class="section-title" style="font-size:1.2rem">Driver details</h3>
      <p class="muted small mb">${icon(CAR_ICON[car.code] || "car", "ic-md")} ${esc(car.name)} · ${esc(p.city)} · ${fmtDate(p.pickup_date)} → ${fmtDate(p.return_date)}</p>
      <form id="car-book-form" class="grid" style="gap:.8rem">
        <div class="field-row">
          <div class="field"><label>Driver name</label><input name="driver_name" required value="${esc(state.user?.full_name || "")}"></div>
          <div class="field"><label>Driver age</label><input name="driver_age" type="number" min="18" max="90" value="30" required></div>
        </div>
        <div class="field"><label>Pickup location</label>
          <select name="pickup_location"><option>Airport</option><option>City centre office</option><option>Hotel delivery</option></select></div>
        <div class="field-row">
          <div class="field"><label>Email</label><input name="contact_email" type="email" required value="${esc(state.user?.email || "")}"></div>
          <div class="field"><label>Phone</label><input name="contact_phone" required pattern="[+0-9][0-9\-\s]{6,19}" title="Enter a valid phone number (7+ digits)" value="${esc(state.user?.phone || "")}"></div>
        </div>
        <p class="muted small">${icon("id","ic-sm")} A valid driving licence is required at pickup. Free cancellation up to 24h before pickup (85% refund).</p>
        <button class="btn btn-primary btn-block">Continue to payment · ${GHS(car.pricing.total)}</button>
      </form>
    </div>
    <div class="summary-card">
      <h4 class="mb">Price summary</h4>
      <div class="sum-row"><span>${GHS(car.daily_rate)} × ${car.pricing.days} day(s)</span><span>${GHS(car.pricing.subtotal)}</span></div>
      <div class="sum-row"><span>VAT (15%)</span><span>${GHS(car.pricing.vat)}</span></div>
      <div class="sum-row total"><span>Total</span><span>${GHS(car.pricing.total)}</span></div>
    </div>
  </div>
  <style>@media(max-width:860px){#car-grid{grid-template-columns:1fr !important}}</style>`;
  $("#car-book-form").onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const btn = e.target.querySelector("button");
    btn.disabled = true;
    try {
      const r = await api("/bookings/car", { method: "POST", body: {
        city: p.city, category: car.code, pickup_date: p.pickup_date, return_date: p.return_date,
        pickup_location: fd.get("pickup_location"), driver_name: fd.get("driver_name"),
        driver_age: +fd.get("driver_age"), contact_email: fd.get("contact_email"),
        contact_phone: fd.get("contact_phone"),
      }});
      toast("Car booking created — complete payment to confirm", "success");
      location.hash = `#/pay/${r.reference}`;
    } catch (err) { toast(err.message, "error"); btn.disabled = false; }
  };
}

/* =====================================================================
   VISA
   ===================================================================== */

function visaCatLabel(cat) {
  if (cat === "visa_free") return "Visa-free";
  if (cat === "evisa") return "eVisa (1-14 days)";
  return "Sticker Visa - Embassy required";
}
function visaSearchForm(p = {}) {
  return `
  <form id="visa-form" class="grid" style="gap:.9rem">
    <div class="form-grid">
      <div class="field"><label>Destination</label><select name="code">${state.meta.visaCountries.length
        ? state.meta.visaCountries.map(c => `<option value="${c.code}" ${c.code === p.code ? "selected" : ""}>${c.code} — ${esc(c.name)}</option>`).join("")
        : `<option value="">Destinations loading… refresh if this stays empty</option>`}</select></div>
    </div>
    <div><button class="btn btn-gold" style="padding:.8rem 2.2rem">Check requirements →</button></div>
  </form>`;
}
function wireVisaForm(root) {
  const form = $("#visa-form", root);
  if (!form) return;
  form.onsubmit = e => {
    e.preventDefault();
    location.hash = `#/visa?code=${new FormData(form).get("code")}`;
  };
}

function viewVisa(params) {
  const code = (params.get("code") || "").toUpperCase();
  const app = $("#app");
  if (!code) {
    app.innerHTML = `<div class="wrap">
      <h2 class="section-title">${icon("passport","ic-md")} Work, Visit & Business Visas</h2>
      <div class="card card-pad mb" style="background:var(--gold-soft);box-shadow:none;border:1px dashed var(--gold)">
        <b>Consultation fee: GH\u00a2500 per applicant — applicable to ALL countries.</b>
        <span class="small">Covers document review, application processing and scheduling. Categories: <b>eVisa (1-14 days)</b> or <b>Sticker Visa - Embassy required</b>.</span>
      </div>
      <p class="section-sub">Over 15,000 candidates recruited to the UAE, Europe and North America. Pick a destination to see requirements and start your application.</p>
      <div class="card card-pad mb">${visaSearchForm({})}</div>
      <div class="grid grid-3">${state.meta.visaCountries.map(c => `
        <a class="card card-pad" href="#/visa?code=${c.code}" style="color:inherit">
          <div class="row"><span class="cc">${c.code}</span><div><b>${esc(c.name)}</b>
          <div class="small muted">${visaCatLabel(c.category)} · ${c.fee ? GHS(c.fee) + " consultation" : "No fee"}</div></div></div>
        </a>`).join("")}</div>
    </div>`;
    wireVisaForm(app);
    return;
  }
  const c = state.meta.visaCountries.find(x => x.code === code);
  if (!c) { app.innerHTML = emptyState("passport", "Unknown country"); return; }
  const needsAppt = ["embassy", "vfs"].includes(c.category);
  app.innerHTML = `<div class="wrap">
    <div class="card card-pad mb">${visaSearchForm({ code })}</div>
    <div class="grid" style="grid-template-columns:1.2fr 1.6fr;align-items:start" id="visa-grid">
      <div class="card card-pad">
        <div class="row mb"><span class="cc">${c.code}</span><h3>${esc(c.name)}</h3>
          <span class="visa-cat">${visaCatLabel(c.category)}</span></div>
        ${c.types ? '<div class="row" style="margin:.5rem 0">' + c.types.map(tp => `<span class="visa-cat" style="background:#EAF4FB;color:#1F2D54">${esc(tp)}</span>`).join("") + "</div>" : ""}
        <div class="sum-row"><span>Consultation fee (per applicant, all countries)</span><b>${c.fee ? GHS(c.fee) : "Free"}</b></div>
        <div class="sum-row"><span>Processing</span><b>${esc(c.processing)}</b></div>
        <div class="sum-row"><span>Validity</span><b>${esc(c.validity)}</b></div>
        <div class="sum-row"><span>Max stay</span><b>${esc(c.stay)}</b></div>
        <h4 class="mt mb" style="font-size:.85rem;text-transform:uppercase;color:var(--muted)">Required documents</h4>
        <ul class="doc-list">${c.docs.map(d => `<li>${esc(d)}</li>`).join("")}</ul>
        <p class="muted small mt">${icon("info","ic-sm")} ${esc(c.note)}</p>
      </div>
      <div class="card card-pad" id="visa-book-box">${loading("Loading…")}</div>
    </div>
    <style>@media(max-width:860px){#visa-grid{grid-template-columns:1fr !important}}</style>
  </div>`;
  wireVisaForm(app);

  const box = $("#visa-book-box");
  let slotState = { center: "", slots: [], sel: null };

  const renderApplicants = () => {
    const service = c.category === "visa_free" ? 0 : SERVICE_FEE;
    const n = Math.max(1, $$("#visa-book-form [data-applicant]").length || 1);
    const total = c.fee * n + service;
    $("#visa-total").innerHTML = GHS(total);
    $("#visa-pay-btn").textContent = `Pay registration fee · ${GHS(total)}`;
  };

  const applicantRow = i => `
    <div class="pax-card" data-applicant>
      <h4>Applicant ${i} <button type="button" class="btn btn-danger btn-sm" style="float:right" data-del ${i === 1 ? "disabled" : ""}>Remove</button></h4>
      <div class="field-row">
        <div class="field"><label>Full name (as in passport)</label><input name="a_name" required></div>
        <div class="field"><label>Passport no.</label><input name="a_passport" required placeholder="A12345678"></div>
        <div class="field"><label>Date of birth</label><input name="a_dob" type="date" required max="${todayISO()}"></div>
      </div>
    </div>`;

  const renderForm = () => {
    box.innerHTML = `
      <h3 class="section-title" style="font-size:1.2rem">Start your application</h3>
      <div class="card card-pad mt" style="background:var(--gold-soft);box-shadow:none;border:1px dashed var(--gold)">
        <b>How it works</b>
        <p class="small" style="margin:.3rem 0 0">1. Pay the <b>${c.fee ? GHS(c.fee) : "Free"} consultation fee</b> per applicant now.<br>
        2. Our consultants contact you on WhatsApp/phone.<br>
        3. Your <b>interview date</b> is scheduled and sent to you.</p>
      </div>
      <form id="visa-book-form" class="grid mt" style="gap:.8rem">
        <div id="applicants">${applicantRow(1)}</div>
        <button type="button" class="btn btn-outline btn-sm" id="add-applicant">${icon("plus","ic-sm")} Add applicant</button>
        <div class="pax-card"><h4>Contact</h4><div class="field-row">
          <div class="field"><label>Email</label><input name="contact_email" type="email" required value="${esc(state.user?.email || "")}"></div>
          <div class="field"><label>Phone</label><input name="contact_phone" required pattern="[+0-9][0-9\-\s]{6,19}" title="Enter a valid phone number (7+ digits)" value="${esc(state.user?.phone || "")}"></div>
        </div></div>
        <div class="sum-row total"><span>Total registration fee</span><span id="visa-total"></span></div>
        <button class="btn btn-primary btn-block" id="visa-pay-btn">Submit application</button>
      </form>`;
    $("#add-applicant").onclick = () => {
      const n = $$("#visa-book-form [data-applicant]").length;
      if (n >= 6) return toast("Maximum 6 applicants per application", "error");
      $("#applicants").insertAdjacentHTML("beforeend", applicantRow(n + 1));
      bindApplicantRows(); renderApplicants();
    };
    const bindApplicantRows = () => $$("#visa-book-form [data-del]").forEach(b => b.onclick = () => {
      if ($$("#visa-book-form [data-applicant]").length > 1) { b.closest("[data-applicant]").remove(); renderApplicants(); }
    });
    bindApplicantRows(); renderApplicants();

    $("#visa-book-form").onsubmit = async e => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const names = fd.getAll("a_name"), passes = fd.getAll("a_passport"), dobs = fd.getAll("a_dob");
      const applicants = names.map((full_name, i) => ({ full_name, passport_no: passes[i], dob: dobs[i] }));
      const btn = $("#visa-pay-btn");
      btn.disabled = true;
      try {
        const r = await api("/bookings/visa", { method: "POST", body: {
          country_code: c.code,
          applicants, contact_email: fd.get("contact_email"), contact_phone: fd.get("contact_phone"),
        }});
        toast("Visa application created", "success");
        location.hash = `#/pay/${r.reference}`;
      } catch (err) { toast(err.message, "error"); btn.disabled = false; }
    };
  };

  const loadSlots = async () => {
    const sb = $("#slot-box");
    sb.innerHTML = loading("Loading slots…");
    try {
      const r = await api(`/visa/${c.code}/slots?center=${encodeURIComponent(slotState.center)}`);
      if (!r.slots.length) { sb.innerHTML = `<p class="muted small">No open slots in the next 3 weeks — try another centre.</p>`; return; }
      const byDate = {};
      r.slots.forEach(s => { (byDate[s.date] = byDate[s.date] || []).push(s); });
      sb.innerHTML = Object.entries(byDate).map(([d, slots]) => `
        <div class="small" style="font-weight:700;margin:.7rem 0 .3rem">${fmtDate(d)}</div>
        <div class="slot-grid">${slots.map(s => `
          <button type="button" class="slot-chip" data-date="${s.date}" data-time="${s.time}">
            ${fmtTime(s.time)}<small>${s.available} spot(s) left</small></button>`).join("")}</div>`).join("");
      $$("#slot-box .slot-chip").forEach(ch => ch.onclick = () => {
        $$("#slot-box .slot-chip").forEach(x => x.classList.remove("sel"));
        ch.classList.add("sel");
        slotState.sel = { date: ch.dataset.date, time: ch.dataset.time };
        toast(`Appointment: ${fmtDate(ch.dataset.date)} ${fmtTime(ch.dataset.time)}`, "success");
      });
    } catch (err) { sb.innerHTML = emptyState("passport", err.message); }
  };
  renderForm();
}

/* =====================================================================
   CHECKOUT (mock gateway)
   ===================================================================== */
async function viewPay(ref) {
  const app = $("#app");
  app.innerHTML = `<div class="wrap">${loading("Preparing checkout…")}</div>`;
  let b;
  try { b = await api(`/bookings/${ref}`); }
  catch (err) { app.innerHTML = emptyState("card", err.message); return; }
  if (b.status === "cancelled") { app.innerHTML = emptyState("ban", "This booking was cancelled.", `<a class="btn btn-outline mt" href="#/">Back home</a>`); return; }
  if (b.status === "confirmed") { renderSuccess(b); return; }

  let method = "card";
  const methodBlurb = { card: "Visa · Mastercard · Verve", bank_transfer: "We show transfer details instantly", ussd: "Dial from any Ghanaian bank", qr: "Scan with your bank app",
    momo: "MTN · Telecel · AT Money — approve with your PIN", office: "Reserve now, pay cash/POS at our Accra office",
    partpay: "Pay 30% now — balance within 4 working days" };
  app.innerHTML = `<div class="wrap" style="max-width:620px">
    <div class="gateway-frame">
      <div class="gateway-head">
        <span class="brand-name">BT<em>Pay</em></span>${icon("lock","ic-sm")}
        <span class="small">Secure checkout</span>
      </div>
      <div class="gateway-body">
        <div class="spread mb">
          <div><div class="muted small">Amount payable</div><div class="gateway-amount">${GHS(b.amount)}</div></div>
          <div class="right"><div class="muted small">Booking reference</div><b>${esc(b.reference)}</b></div>
        </div>
        ${bookingSummaryHtml(b)}
        <div class="pay-methods" id="plan-pick">
          <div class="pay-method sel" data-plan="full"><span class="pm-icon">${icon("card")}</span><div><b>Pay in full</b><div class="muted small">One payment of ${GHS(b.amount)} — instant confirmation</div></div></div>
          <div class="pay-method" data-plan="part"><span class="pm-icon">${icon("calendar")}</span><div><b>Pay small small</b><div class="muted small">30% now (${GHS(Math.round(b.amount * 0.3))}) — balance ${GHS(b.amount - Math.round(b.amount * 0.3))} within 4 working days (policy)</div></div></div>
        </div>
        <div class="pay-methods" id="pay-methods">
          ${[["card", "card", "Pay with Card"], ["momo", "mobile", "MoMo"], ["bank_transfer", "bank", "Bank Transfer"], ["ussd", "mobile", "USSD"], ["office", "pin", "Pay at Our Office"]]
            .map(([k, ic, lb]) => `<div class="pay-method ${k === "card" ? "sel" : ""}" data-m="${k}"><span class="pm-icon">${icon(ic)}</span><div><b>${lb}</b><div class="muted small">${methodBlurb[k]}</div></div></div>`).join("")}
        </div>
        <div id="momo-fields" class="grid hidden" style="gap:.7rem">
          <div class="field"><label>Mobile money number</label><input id="momo-no" placeholder="055 123 4567" inputmode="tel"></div>
          <p class="muted small">A prompt will be sent to your phone — approve with your MoMo PIN.</p>
        </div>
        <div id="card-fields" class="grid" style="gap:.7rem">
          <div class="field"><label>Card number</label><input id="card-no" placeholder="4242 4242 4242 4242" maxlength="19"></div>
          <div class="field-row">
            <div class="field"><label>Expiry</label><input id="card-exp" placeholder="12/28" maxlength="5"></div>
            <div class="field"><label>CVV</label><input id="card-cvv" placeholder="123" maxlength="4" type="password"></div>
          </div>
        </div>
        <button class="btn btn-primary btn-block mt" id="pay-btn">Pay ${GHS(b.amount)}</button>
        <p class="muted small center mt">${icon("lock","ic-xs")} Demo gateway — no real money moves. Swap in Paystack/Flutterwave in <code>routers/payments.py</code>.</p>
      </div>
    </div>
  </div>`;
  let plan = "full";
  const syncPlan = () => {
    $$("#plan-pick .pay-method").forEach(x => x.classList.toggle("sel", x.dataset.plan === plan));
    $("#pay-methods").style.display = plan === "part" ? "none" : "";
    $("#card-fields").style.display = plan === "full" && method === "card" ? "" : "none";
    $("#momo-fields").style.display = plan === "full" && method === "momo" ? "" : "none";
    $("#pay-btn").textContent = plan === "part" ? `Pay 30% now — ${GHS(Math.round(b.amount * 0.3))}`
      : (method === "office" ? `Reserve — pay ${GHS(b.amount)} at office` : `Pay ${GHS(b.amount)}`);
  };
  $$("#plan-pick .pay-method").forEach(m => m.onclick = () => { plan = m.dataset.plan; syncPlan(); });
  syncPlan();
  $$("#pay-methods .pay-method").forEach(m => m.onclick = () => {
    method = m.dataset.m;
    $$("#pay-methods .pay-method").forEach(x => x.classList.toggle("sel", x === m));
    syncPlan();
  });
  $("#pay-btn").onclick = async () => {
    const btn = $("#pay-btn");
    if (method === "office") {
      btn.disabled = true; btn.textContent = "Reserving…";
      try {
        const r = await api("/payments/office", { method: "POST", body: { reference: ref } });
        renderOfficeReserved(r);
      } catch (err) { toast(err.message, "error"); btn.disabled = false; btn.textContent = `Reserve — pay ${GHS(b.amount)} at office`; }
      return;
    }
    if (method === "momo") {
      const no = ($("#momo-no")?.value || "").replace(/\D/g, "");
      if (no.length < 9) { toast("Enter a valid mobile money number", "error"); return; }
    }
    if (plan === "part") {
      btn.disabled = true; btn.textContent = "Processing…";
      try {
        const r = await api("/payments/installment", { method: "POST", body: { reference: ref } });
        if (r.live && r.authorization_url) { location.href = r.authorization_url; return; }
        renderInstallment(r);
      } catch (err) { toast(err.message, "error"); btn.disabled = false; syncPlan(); }
      return;
    }
    btn.disabled = true; btn.textContent = method === "momo" ? "Check your phone…" : "Processing…";
    try {
      await api("/payments/confirm", { method: "POST", body: { reference: ref, method } });
      const fresh = await api(`/bookings/${ref}`);
      renderSuccess(fresh);
    } catch (err) { toast(err.message, "error"); btn.disabled = false; btn.textContent = `Pay ${GHS(b.amount)}`; }
  };
}

function renderInstallment(r) {
  const waText = encodeURIComponent(`Hello Brother'sTrust Travel! I paid the first installment for ${r.reference}. I will complete GH¢${r.balance} before ${r.deadline}.`);
  $("#app").innerHTML = `<div class="wrap" style="max-width:640px">
    <div class="card card-pad center mt">
      <div class="success-check">${icon("calendar")}</div>
      <h2 class="section-title">First payment received!</h2>
      <p class="muted">Pay-small-small plan started (policy: <b>30% first payment</b>, balance within <b>4 working days</b>). Your booking confirms automatically once the balance is paid.</p>
      <div class="mt"><span class="ref-pill">${esc(r.reference)}</span></div>
      <div class="mt left" style="max-width:420px;margin-left:auto;margin-right:auto">
        <div class="card card-pad" style="box-shadow:none;border:1px solid var(--line)">
          <div class="sum-row"><span>Paid today (30%)</span><b>${GHS(r.first)}</b></div>
          <div class="sum-row"><span>Balance due</span><b>${GHS(r.balance)}</b></div>
          <div class="sum-row"><span>Pay balance by</span><b>${fmtDate(r.deadline)}</b></div>
          <div class="sum-row total"><span>Total</span><span>${GHS(r.first + r.balance)}</span></div>
        </div>
      </div>
      <div class="row mt" style="justify-content:center">
        <a class="btn btn-primary" href="https://wa.me/233551934922?text=${waText}" target="_blank" rel="noopener">${icon("whatsapp","ic-sm")} Discuss on WhatsApp</a>
        <a class="btn btn-outline" href="#/bookings">My bookings</a>
      </div>
      <p class="muted small mt">Find "Pay balance" next to this booking in My Bookings anytime before the deadline. Cancellation policy: <b>30% of payments are refunded</b>.</p>
    </div>
  </div>`;
}

function renderOfficeReserved(r) {
  const waText = encodeURIComponent(`Hello Brother'sTrust Travel! I want to pay for booking ${r.reference} (${GHS(r.amount)}) at your office.`);
  $("#app").innerHTML = `<div class="wrap" style="max-width:640px">
    <div class="card card-pad center mt">
      <div class="success-check">${icon("pin")}</div>
      <h2 class="section-title">Booking reserved!</h2>
      <p class="muted">Pay at our office within 48 hours to confirm. Bring your reference number.</p>
      <div class="mt"><span class="ref-pill">${esc(r.reference)}</span></div>
      <div class="mt left" style="max-width:420px;margin-left:auto;margin-right:auto">
        <div class="card card-pad" style="box-shadow:none;border:1px solid var(--line)">
          <div class="sum-row"><span>Amount due</span><b>${GHS(r.amount)}</b></div>
          <div class="sum-row"><span>Office</span><span>${esc(r.office.name)}</span></div>
          <div class="sum-row"><span>Address</span><span>${esc(r.office.address)}</span></div>
          <div class="sum-row"><span>Hours</span><span>${esc(r.office.hours)}</span></div>
        </div>
      </div>
      <div class="row mt" style="justify-content:center">
        <a class="btn btn-primary" href="${r.office.whatsapp}?text=${waText}" target="_blank" rel="noopener">${icon("whatsapp","ic-sm")} Confirm on WhatsApp</a>
        <a class="btn btn-outline" href="#/bookings">My bookings</a>
      </div>
    </div>
  </div>`;
}

function renderSuccess(b) {
  trackEvent("payment_confirmed", "/pay/" + (b.reference || ""));
  $("#app").innerHTML = `<div class="wrap" style="max-width:640px">
    <div class="card card-pad center mt">
      <div class="success-check">${icon("check-circle")}</div>
      <h2 class="section-title">Payment successful!</h2>
      <p class="muted">Your booking is confirmed. A confirmation has been sent to your email.</p>
      <div class="mt"><span class="ref-pill">${esc(b.reference)}</span></div>
      <div class="mt left" style="max-width:420px;margin-left:auto;margin-right:auto">${bookingSummaryHtml(b)}</div>
      <div class="row mt" style="justify-content:center">
        <a class="btn btn-outline" href="#/bookings">My bookings</a>
        <a class="btn btn-primary" href="#/">Book another trip</a>
      </div>
    </div>
  </div>`;
}

function bookingSummaryHtml(b) {
  const d = b.details;
  let rows = "";
  if (b.type === "flight") {
    rows = (d.legs || []).map(l => `<div class="sum-row"><span>${icon("plane","ic-sm")} ${l.origin} → ${l.dest}</span><span>${l.airline} ${l.flight_no} · ${fmtDate(l.date)}</span></div>`).join("");
    if (d.fare != null) rows += `<div class="sum-row"><span>Base fare (${b.travelers.length} traveller(s))</span><span>${GHS(d.fare)}</span></div>`;
    if (d.taxes != null) rows += `<div class="sum-row"><span>Taxes & surcharges</span><span>${GHS(d.taxes)}</span></div>`;
    if (d.service_fee != null) rows += `<div class="sum-row"><span>Service fee</span><span>${GHS(d.service_fee)}</span></div>`;
  } else if (b.type === "hotel") {
    const p = d.pricing || {};
    rows = `<div class="sum-row"><span>${icon("hotel","ic-sm")} ${esc(d.hotel_name)}</span><span>${d.stars ? "★".repeat(d.stars) : ""}</span></div>
      <div class="sum-row"><span>${esc(d.room_type)} × ${d.rooms}</span><span>${fmtDate(d.checkin)} → ${fmtDate(d.checkout)}</span></div>`;
    if (p.rate_per_night) rows += `<div class="sum-row"><span>${GHS(p.rate_per_night)} × ${p.nights} night(s) × ${p.rooms} room(s)</span><span>${GHS(p.subtotal)}</span></div>`;
    if (p.vat) rows += `<div class="sum-row"><span>VAT (15%)</span><span>${GHS(p.vat)}</span></div>`;
  } else if (b.type === "car") {
    const p = d.pricing || {};
    rows = `<div class="sum-row"><span>${icon("car","ic-sm")} ${esc(d.category_name)}</span><span>${esc(d.city)}</span></div>
      <div class="sum-row"><span>${fmtDate(d.pickup_date)} → ${fmtDate(d.return_date)}</span><span>${esc(d.pickup_location || "")}</span></div>`;
    if (p.daily_rate) rows += `<div class="sum-row"><span>${GHS(p.daily_rate)} × ${p.days} day(s)</span><span>${GHS(p.subtotal)}</span></div>`;
    if (p.vat) rows += `<div class="sum-row"><span>VAT (15%)</span><span>${GHS(p.vat)}</span></div>`;
  } else if (b.type === "visa") {
    const regFee = (d.price && d.price.registration_fee != null) ? d.price.registration_fee : null;
    const n = (d.price && d.price.applicants) || b.travelers.length;
    rows = `<div class="sum-row"><span>${icon("passport","ic-sm")} <span class="cc">${d.country_code || ""}</span> ${esc(d.country)}</span><span>${visaCatLabel(d.category || "")}</span></div>
      ${regFee != null ? `<div class="sum-row"><span>Registration fee${n > 1 ? ` × ${n} applicants` : ""}</span><span>${GHS(regFee * n)}</span></div>` : ""}
      ${d.interview ? `<div class="sum-row"><span>Interview</span><span>${esc(typeof d.interview === "string" ? d.interview : ((d.interview.date || "") + " " + (d.interview.time || "")))}</span></div>` : ""}
      <div class="sum-row"><span>Applicants</span><span>${b.travelers.join(", ")}</span></div>`;
  }
  return `<div class="card card-pad" style="box-shadow:none;border:1px solid var(--line)">
    ${rows}<div class="sum-row total"><span>Total</span><span>${GHS(b.amount)}</span></div></div>`;
}

/* =====================================================================
   MY BOOKINGS / DETAIL / NOTIFICATIONS
   ===================================================================== */
const TYPE_META = {
  flight: { icon: icon("plane"), cls: "bi-flight", label: "Flight" },
  hotel:  { icon: icon("hotel"), cls: "bi-hotel",  label: "Hotel" },
  car:    { icon: icon("car"),   cls: "bi-car",    label: "Car rental" },
  visa:   { icon: icon("passport"), cls: "bi-visa", label: "Visa" },
};
const bookingTitle = b => {
  const d = b.details;
  if (b.type === "flight") return (d.legs || []).map(l => `${l.origin} → ${l.dest}`).join(" · ");
  if (b.type === "hotel") return d.hotel_name;
  if (b.type === "car") return `${d.category_name} · ${d.city}`;
  return `${d.flag || ""} ${d.country} visa`.trim();
};
const bookingWhen = b => {
  const d = b.details;
  if (b.type === "flight") return fmtDate(d.legs[0].date);
  if (b.type === "hotel") return `${fmtDate(d.checkin)} → ${fmtDate(d.checkout)}`;
  if (b.type === "car") return `${fmtDate(d.pickup_date)} → ${fmtDate(d.return_date)}`;
  return d.date && d.time ? `${fmtDate(d.date)} ${d.time}` : (d.processing || "");
};

async function viewBookings() {
  const app = $("#app");
  if (!state.user) { openAuthModal("Sign in to view your bookings"); app.innerHTML = emptyState("ticket", "Sign in to view your bookings."); return; }
  app.innerHTML = `<div class="wrap"><h2 class="section-title">My bookings</h2><p class="section-sub">Everything you've booked with Brother'sTrust Travel</p><div id="blist">${loading()}</div></div>`;
  try {
    const list = await api("/bookings/mine");
    if (!list.length) { $("#blist").innerHTML = emptyState("ticket", "No bookings yet — time to plan a trip!", `<a class="btn btn-primary mt" href="#/">Start searching</a>`); return; }
    $("#blist").innerHTML = `<div class="grid" style="gap:.7rem">${list.map(b => {
      const m = TYPE_META[b.type];
      return `<div class="card booking-item">
        <div class="booking-icon ${m.cls}">${m.icon}</div>
        <div style="flex:1;min-width:220px">
          <b>${esc(bookingTitle(b))}</b>
          <div class="muted small">${m.label} · ${esc(bookingWhen(b))} · ${esc(b.reference)}</div>
        </div>
        <div class="right">
          <b>${GHS(b.amount)}</b>
          <div><span class="status-pill ${b.status}">${b.status}</span></div>
        </div>
        <div class="row">
          ${b.status === "pending" && b.details?.installments?.balance > 0 ? `<span class="status-pill pending">Balance ${GHS(b.details.installments.balance)} due ${fmtDate(b.details.installments.deadline)}</span><button class="btn btn-gold btn-sm" data-balance="${b.reference}">Pay balance</button>` : ""}
          ${b.status === "pending" ? `<a class="btn btn-primary btn-sm" href="#/pay/${b.reference}">Pay now</a>` : ""}
          <a class="btn btn-outline btn-sm" href="#/booking/${b.reference}">View</a>
          ${["pending", "confirmed"].includes(b.status) ? `<button class="btn btn-danger btn-sm" data-cancel="${b.reference}">Cancel</button>` : ""}
        </div>
      </div>`; }).join("")}</div>`;
    bindCancelButtons($("#blist"));
    $$("#blist [data-balance]").forEach(btn => btn.onclick = async () => {
      btn.disabled = true;
      try {
        const r = await api("/payments/balance", { method: "POST", body: { reference: btn.dataset.balance, method: "card" } });
        if (r.live && r.authorization_url) { location.href = r.authorization_url; return; }
        toast("Balance paid — booking confirmed!", "success");
        route();
      } catch (err) { toast(err.message, "error"); btn.disabled = false; }
    });
  } catch (err) { $("#blist").innerHTML = emptyState("alert", err.message); }
}

function bindCancelButtons(root) {
  $$("[data-cancel]", root).forEach(btn => btn.onclick = async () => {
    if (!confirm(`Cancel booking ${btn.dataset.cancel}? Refund rules apply.`)) return;
    try {
      const r = await api(`/bookings/${btn.dataset.cancel}/cancel`, { method: "POST" });
      toast(`Cancelled — ${GHS(r.refund_amount)} refund initiated`, "success");
      route();
    } catch (err) { toast(err.message, "error"); }
  });
}

async function viewBooking(ref) {
  const app = $("#app");
  app.innerHTML = `<div class="wrap">${loading()}</div>`;
  let b;
  try { b = await api(`/bookings/${ref}`); }
  catch (err) { app.innerHTML = emptyState("alert", err.message); return; }
  const m = TYPE_META[b.type];
  app.innerHTML = `<div class="wrap" style="max-width:720px">
    <div class="spread mb">
      <h2 class="section-title">${m.icon} ${esc(bookingTitle(b))}</h2>
      <span class="status-pill ${b.status}">${b.status}</span>
    </div>
    ${bookingSummaryHtml(b)}
    <div class="card card-pad mt">
      <div class="sum-row"><span>Reference</span><b>${esc(b.reference)}</b></div>
      <div class="sum-row"><span>Booked on</span><span>${esc(b.created_at)}</span></div>
      ${b.travelers?.length ? `<div class="sum-row"><span>${b.type === "visa" ? "Applicants" : "Travellers"}</span><span>${b.travelers.map(esc).join(", ")}</span></div>` : ""}
      ${b.refund_amount != null ? `<div class="sum-row"><span>Refund</span><b>${GHS(b.refund_amount)}</b></div>` : ""}
    </div>
    <div class="row mt">
      ${b.status === "pending" ? `<a class="btn btn-primary" href="#/pay/${b.reference}">Complete payment</a>` : ""}
      ${["pending", "confirmed"].includes(b.status) ? `<button class="btn btn-danger" data-cancel="${b.reference}">Cancel booking</button>` : ""}
      <a class="btn btn-outline" href="#/bookings">All bookings</a>
    </div>
  </div>`;
  bindCancelButtons(app);
}

async function viewNotifications() {
  const app = $("#app");
  app.innerHTML = `<div class="wrap"><h2 class="section-title">${icon("bell","ic-md")} Notifications</h2><div id="nlist">${loading()}</div></div>`;
  try {
    const list = await api("/notifications");
    if (!list.length) { $("#nlist").innerHTML = emptyState("bell", "Nothing yet — your updates will land here."); return; }
    $("#nlist").innerHTML = `<div class="grid" style="gap:.6rem">${list.map(n => `
      <div class="card card-pad" style="${n.read ? "opacity:.65" : ""}">
        <b>${n.read ? "" : '<span class="dot"></span>'}${esc(n.title)}</b>
        <p class="small">${esc(n.body)}</p>
        <div class="muted small">${esc(n.created_at)}</div>
      </div>`).join("")}</div>
      <button class="btn btn-outline mt" id="mark-read">Mark all as read</button>`;
    $("#mark-read").onclick = async () => { await api("/notifications/read", { method: "POST" }); route(); };
  } catch (err) { $("#nlist").innerHTML = emptyState("alert", err.message); }
}

/* =====================================================================
   ADMIN
   ===================================================================== */
async function viewAdmin() {
  const app = $("#app");
  if (!state.user || state.user.role !== "admin") { app.innerHTML = emptyState("lock", "Admin access required."); return; }
  app.innerHTML = `<div class="wrap"><h2 class="section-title">${icon("sliders","ic-md")} Admin dashboard</h2><div id="admin-body">${loading()}</div></div>`;
  try {
    const [s, bookings, users] = await Promise.all([
      api("/admin/stats"), api("/admin/bookings"), api("/admin/users"),
    ]);
    $("#admin-body").innerHTML = `
      <div class="grid grid-3 mb">
        <div class="card stat-card"><div class="num">${s.users.toLocaleString()}</div><div class="lbl">Registered users</div></div>
        <div class="card stat-card"><div class="num">${s.bookings.toLocaleString()}</div><div class="lbl">Total bookings</div></div>
        <div class="card stat-card"><div class="num">${GHS(s.revenue_confirmed)}</div><div class="lbl">Confirmed revenue</div></div>
        <div class="card stat-card"><div class="num">${GHS(s.revenue_pending)}</div><div class="lbl">Pending payment</div></div>
        <div class="card stat-card"><div class="num">${(s.by_type.flight || 0) + (s.by_type.hotel || 0) + (s.by_type.car || 0) + (s.by_type.visa || 0)}</div><div class="lbl">${icon("plane","ic-xs")} ${s.by_type.flight || 0} · ${icon("hotel","ic-xs")} ${s.by_type.hotel || 0} · ${icon("car","ic-xs")} ${s.by_type.car || 0} · ${icon("passport","ic-xs")} ${s.by_type.visa || 0}</div></div>
        <div class="card stat-card"><div class="num">${s.by_status.pending || 0}/${s.by_status.confirmed || 0}/${s.by_status.cancelled || 0}</div><div class="lbl">Pending / Confirmed / Cancelled</div></div>
      </div>
      <h3 class="section-title" style="font-size:1.15rem">Recent confirmed revenue</h3>
      <div class="card table-scroll mb"><table class="table"><tr><th>Date</th><th>Bookings</th><th>Revenue</th></tr>
        ${s.daily.map(d => `<tr><td>${d.date}</td><td>${d.bookings}</td><td>${GHS(d.revenue)}</td></tr>`).join("")}</table></div>
      <h3 class="section-title" style="font-size:1.15rem">Latest bookings</h3>
      <div class="card table-scroll mb"><table class="table"><tr><th>Reference</th><th>Type</th><th>Status</th><th>Amount</th><th>Customer</th><th>Travellers</th><th>Action</th></tr>
        ${bookings.map(b => `<tr><td>${b.reference}</td><td>${TYPE_META[b.type]?.icon || ""} ${b.type}</td>
          <td><span class="status-pill ${b.status}">${b.status}</span></td><td>${GHS(b.amount)}</td>
          <td>${esc(b.email)}</td><td>${b.travelers.map(esc).join(", ")}</td>
          <td>${b.status === "pending" ? `<button class="btn btn-primary btn-sm" data-confirm="${b.reference}">Confirm pay</button>` : ""}${b.type === "visa" && b.status === "confirmed" ? ` <button class="btn btn-outline btn-sm" data-schedule="${b.reference}">Schedule interview</button>` : ""}</td></tr>`).join("")}</table></div>
      <h3 class="section-title" style="font-size:1.15rem">Users</h3>
      <div class="card table-scroll"><table class="table"><tr><th>Name</th><th>Email</th><th>Role</th><th>Joined</th></tr>
        ${users.map(u => `<tr><td>${esc(u.full_name)}</td><td>${esc(u.email)}</td><td>${u.role}</td><td>${esc(u.created_at)}</td></tr>`).join("")}</table></div>`;
    $$("#admin-body [data-confirm]").forEach(btn => btn.onclick = async () => {
      btn.disabled = true;
      try {
        await api(`/admin/bookings/${btn.dataset.confirm}/confirm`, { method: "POST" });
        toast(`Booking ${btn.dataset.confirm} confirmed — ticket issued`, "success");
        viewAdmin();
      } catch (err) { toast(err.message, "error"); btn.disabled = false; }
    });
  } catch (err) { $("#admin-body").innerHTML = emptyState("alert", err.message); }
}

/* =====================================================================
   ROUTER + BOOT
   ===================================================================== */
function setActiveNav(seg) {
  $$("#mainnav a").forEach(a => a.classList.toggle("active", a.dataset.nav === seg));
}
function route() {
  const raw = (location.hash || "#/").slice(1);
  const [path, query] = raw.split("?");
  const params = new URLSearchParams(query || "");
  const seg = path.split("/")[1] || "home";
  setActiveNav(seg);
  window.scrollTo(0, 0);
  if (seg === "home" || seg === "") viewHome();
  else if (seg === "flights") viewFlights(params);
  else if (seg === "hotels") viewHotels(params);
  else if (seg === "cars") viewCars(params);
  else if (seg === "visa") viewVisa(params);
  else if (seg === "pay") viewPay(path.split("/")[2]);
  else if (seg === "booking") viewBooking(path.split("/")[2]);
  else if (seg === "bookings") viewBookings();
  else if (seg === "notifications") viewNotifications();
  else if (seg === "admin") viewAdmin();
  else viewHome();
}

(async function boot() {
  try {
    await loadMe();
    await loadMeta();
  } catch (err) {
    toast("Couldn't reach the API — is the backend running?", "error");
  }
  route();
})();
window.addEventListener("hashchange", route);

/* =====================================================================
   v3 — legal pages, custom 404, cookie consent, per-route meta,
   first-party analytics, mobile nav, enhanced admin (traffic + users)
   ===================================================================== */
function trackEvent(kind, page) {
  // first-party, anonymous usage counters — no third-party trackers
  try {
    const payload = JSON.stringify({ kind, page });
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/analytics", new Blob([payload], { type: "application/json" }));
    } else {
      fetch("/api/analytics", { method: "POST", headers: { "Content-Type": "application/json" },
                                body: payload, keepalive: true });
    }
  } catch (e) { /* analytics must never break the app */ }
}

const burger = $("#burger");
if (burger) burger.onclick = () => $("#mainnav").classList.toggle("open");
$$("#mainnav a").forEach(a => a.addEventListener("click", () => $("#mainnav").classList.remove("open")));

const ROUTE_META = {
  home:     ["Brother'sTrust Travel — Flights, Hotels, Cars & Visa", "Book flights, hotels, car rentals and visa appointments with Brother'sTrust Travel. Secure payments, instant confirmation."],
  flights:  ["Cheap Flights in Nigeria & Worldwide — Brother'sTrust Travel", "Search and book flights from Accra, Lagos and Abuja to Africa, Europe, the US and the Middle East."],
  hotels:   ["Hotels & Accommodation — Brother'sTrust Travel", "Handpicked hotels in Lagos, Abuja, Accra, Dubai, London, New York, Paris and Nairobi."],
  cars:     ["Car Rentals with Airport Pickup — Brother'sTrust Travel", "Reliable car rentals in Lagos, Abuja, Accra, Dubai, London, Johannesburg and Nairobi."],
  visa:     ["Work, Visit & Business Visas — Brother'sTrust Travel", "Visas to the UAE, Saudi Arabia, Kuwait, Qatar, Europe, the US & Canada. Over 15,000 candidates recruited."],
  bookings: ["My Bookings — Brother'sTrust Travel", "View, pay for and manage your Brother'sTrust Travel bookings."],
  about:    ["About Us — Brother'sTrust Travel", "Who we are: a trusted Ghanaian travel agency handling flights, hotels, cars and visas end-to-end."],
  contact:  ["Contact Us — Brother'sTrust Travel", "Reach Brother'sTrust Travel by phone, email or at our Accra and Kumasi, Ghana offices."],
  privacy:  ["Privacy Policy — Brother'sTrust Travel", "How Brother'sTrust Travel collects, uses and protects your personal data, cookies and payment information."],
  terms:    ["Terms & Conditions — Brother'sTrust Travel", "The terms governing bookings, payments, cancellations, refunds and visa services at Brother'sTrust Travel."],
  admin:    ["Admin Dashboard — Brother'sTrust Travel", "Bookings, revenue, users and traffic analytics."],
};

function staticPage(title, updated, bodyHtml) {
  return `<div class="wrap" style="max-width:820px">
    <h1 class="section-title">${title}</h1>
    <p class="updated">Last updated: ${updated}</p>
    <div class="card card-pad prose mt">${bodyHtml}</div>
    <p class="mt"><a href="#/">← Back to booking</a></p>
  </div>`;
}

function viewPrivacy() {
  $("#app").innerHTML = staticPage(`${icon("shield","ic-md")} Privacy Policy`, "October 2026", `
    <p>Brother'sTrust Travel ("we", "us") respects your privacy. This policy explains what we collect, why, and the choices you have.</p>
    <h3>1. Information we collect</h3>
    <ul>
      <li><b>Account data</b> — name, email and phone number you give us at registration.</li>
      <li><b>Booking data</b> — traveller names, passport numbers (for visa applications), travel dates and preferences.</li>
      <li><b>Contact data</b> — messages you send us.</li>
      <li><b>Usage data</b> — pages visited, anonymised by consent only (see Cookies).</li>
    </ul>
    <h3>2. Payments</h3>
    <p>Card payments are processed by <b>Paystack</b>. We never see or store your full card number, CVV or banking credentials — only the transaction reference and amount.</p>
    <h3>3. How we use your information</h3>
    <ul>
      <li>To fulfil your bookings (flights, hotels, cars, visa appointments).</li>
      <li>To send confirmations and updates by email (SendGrid) and SMS (Africa's Talking).</li>
      <li>To improve our services using aggregated, consented analytics.</li>
    </ul>
    <h3>4. Third-party processors</h3>
    <p>Paystack (payments), SendGrid (email), Africa's Talking (SMS). Each processes data on our behalf under its own privacy terms.</p>
    <h3>5. Cookies & local storage</h3>
    <ul>
      <li><b>Sign-in session</b> — a token stored in your browser to keep you signed in.</li>
      <li><b>Anonymous analytics</b> — first-party page-view counters with no third-party trackers. You can clear these anytime via your browser settings.</li>
    </ul>
    <h3>6. Retention & security</h3>
    <p>We keep booking records as required for accounting and travel regulations, encrypt passwords (PBKDF2), sign sessions (JWT), force HTTPS in production and rate-limit abuse-prone endpoints.</p>
    <h3>7. Your rights</h3>
    <p>You may request access, correction or deletion of your data at any time: <b>hello@brotherstrusttravel.com</b>. We respond within 30 days.</p>
    <h3>8. Children</h3>
    <p>Our services are not directed at children under 13, and we do not knowingly collect their data.</p>
    <h3>9. Changes</h3>
    <p>If we change this policy, the updated version will be posted here with a new "Last updated" date.</p>
    <p><b>Contact:</b> hello@brotherstrusttravel.com · +233 55 193 4922 · Accra, Ghana.</p>`);
}

function viewTerms() {
  $("#app").innerHTML = staticPage(`${icon("file","ic-md")} Terms & Conditions`, "October 2026", `
    <p>By using Brother'sTrust Travel you agree to these terms. Please read them carefully.</p>
    <h3>1. Bookings</h3>
    <p>All bookings are subject to availability and confirmation. A booking is only confirmed once payment is completed; until then it remains "pending" and may expire.</p>
    <h3>2. Prices & payment</h3>
    <p>Prices are shown in Ghanaian cedis (GH¢) and include stated taxes and our service fee. Payment is collected securely via Paystack. We never store card details.</p>
    <h3>3. Pay small small (installment policy)</h3>
    <p>Where offered, our installment plan requires a <b>first payment of 30% of the total</b> at booking. The <b>balance is due within 4 working days</b>. Your booking is confirmed — and tickets/reservations are issued — only when payment is complete. Unpaid balances after the deadline may result in cancellation. <b>Cancellation of a pay-small-small booking refunds 30% of amounts paid.</b></p>
    <h3>4. Cancellations & refunds</h3>
    <ul>
      <li><b>Flights</b> — cancel up to 24h before departure: <b>80% refund</b>.</li>
      <li><b>Hotels</b> — cancel up to 48h before check-in: <b>90% refund</b>.</li>
      <li><b>Cars</b> — cancel up to 24h before pickup: <b>85% refund</b>.</li>
      <li><b>Visa services</b> — cancel up to 24h before your appointment: <b>90% refund</b>.</li>
    </ul>
    <p>Refunds are returned to your original payment method within 5–7 working days.</p>
    <h3>5. Visa services</h3>
    <p>Visa services are offered for a <b>GH\u00a2500 registration fee per applicant</b>, covering processing and consultation. After payment, our consultants contact you and your <b>interview date is scheduled and sent to you</b>. Visa issuance is solely at the discretion of the relevant embassy. The registration fee is non-refundable once processing has started. You are responsible for the accuracy of your documents.</p>
    <h3>6. Travel documents</h3>
    <p>You are responsible for holding a valid passport, required visas, vaccinations and transit documents. We are not liable for denied boarding or entry caused by incomplete documents.</p>
    <h3>7. Liability</h3>
    <p>Our liability for any claim is capped at the amount you paid for the affected booking. We are not liable for airline/hotel/supplier schedule changes beyond our control, but we will assist with rebooking.</p>
    <h3>8. Acceptable use</h3>
    <p>You must not misuse the platform (fraud, scraping, spam, probing). We may suspend accounts that do.</p>
    <h3>9. Intellectual property</h3>
    <p>The Brother'sTrust Travel brand, design and content belong to us. You may not copy them without permission.</p>
    <h3>10. Governing law</h3>
    <p>These terms are governed by the laws of the Republic of Ghana, with the courts of Accra having jurisdiction.</p>
    <p><b>Contact:</b> hello@brotherstrusttravel.com · +233 55 193 4922.</p>`);
}

function viewAbout() {
  $("#app").innerHTML = `<div class="wrap" style="max-width:820px">
    <h1 class="section-title">${icon("plane","ic-md")} About Brother'sTrust Travel</h1>
    <div class="card card-pad prose mt">
      <p>Brother'sTrust Travel is a Ghanaian travel agency built on a simple promise: <b>handle everything — flights, hotels, cars and visas — so you can focus on the journey.</b></p>
      <p>From our offices in Accra, Lagos and Abuja we serve thousands of travellers booking domestic routes like Lagos–Abuja, regional escapes to Accra and Nairobi, and long-haul trips to London, Dubai and New York.</p>
      <h3>Why travellers trust us</h3>
      <ul>
        <li>${icon("target","ic-sm")} <b>One platform</b> — search, book and pay for everything in a single checkout.</li>
        <li>${icon("lock","ic-sm")} <b>Secure payments</b> — PCI-DSS compliant processing via Paystack.</li>
        <li>${icon("users","ic-sm")} <b>15,000+ candidates recruited</b> — direct employment to the UAE, Saudi Arabia, Kuwait, Qatar and Europe, plus US & Canada work routes.</li>
        <li>${icon("passport","ic-sm")} <b>Real visa expertise</b> — document checklists, appointment slots and consultant follow-up for 13 destinations.</li>
        <li>${icon("message","ic-sm")} <b>Human support</b> — phone, email and SMS updates at every step (SendGrid + Africa's Talking).</li>
      </ul>
      <div class="row mt">
        <a class="btn btn-primary" href="#/flights">Start booking →</a>
        <a class="btn btn-outline" href="#/contact">Talk to us</a>
      </div>
    </div></div>`;
}

function viewContact() {
  $("#app").innerHTML = `<div class="wrap" style="max-width:820px">
    <h1 class="section-title">${icon("phone","ic-md")} Contact Us</h1>
    <p class="section-sub">We reply within 24 hours — usually much faster.</p>
    <div class="grid grid-2">
      <div class="card card-pad">
        <h3 class="mb">Get in touch</h3>
        <p class="fcontact">${icon("phone","ic-sm")} <b>+233 55 193 4922</b> (Mon–Sat, 8:00–20:00 GMT)</p>
        <p class="fcontact">${icon("mail","ic-sm")} <a href="mailto:hello@brotherstrusttravel.com">hello@brotherstrusttravel.com</a></p>
        <p class="fcontact">${icon("whatsapp","ic-sm")} <a href="https://wa.me/233551934922" target="_blank" rel="noopener">+233 55 193 4922 (WhatsApp)</a></p>
        <p class="mt fcontact">${icon("pin","ic-sm")} <b>Accra</b> — Airport Residential<br><span class="fcontact">${icon("pin","ic-sm")} <b>Lagos</b> — Victoria Island</span><br><span class="fcontact">${icon("pin","ic-sm")} <b>Abuja</b> — Wuse II</span></p>
      </div>
      <div class="card card-pad">
        <h3 class="mb">Send a message</h3>
        <form id="contact-form" class="grid" style="gap:.7rem">
          <div class="field"><label>Your name</label><input name="name" required minlength="2"></div>
          <div class="field"><label>Email</label><input name="email" type="email" required></div>
          <div class="field"><label>Message</label><textarea name="msg" rows="4" required minlength="10"></textarea></div>
          <button class="btn btn-primary btn-block">Send via email →</button>
        </form>
      </div>
    </div></div>`;
  $("#contact-form").onsubmit = e => {
    e.preventDefault();
    const f = new FormData(e.target);
    location.href = `mailto:hello@brotherstrusttravel.com?subject=${encodeURIComponent("Enquiry from " + f.get("name"))}&body=${encodeURIComponent(f.get("msg") + "\n\n— " + f.get("name") + " (" + f.get("email") + ")")}`;
    toast("Opening your email app…", "success");
  };
}

function viewNotFound() {
  $("#app").innerHTML = `<div class="wrap center" style="max-width:640px;padding-top:3rem">
    <div class="notfound-code">404</div>
    <h2 class="section-title">This page took a different flight ${icon("plane","ic-md")}</h2>
    <p class="muted mt">The page you're looking for doesn't exist or was moved. Let's get you back on track.</p>
    <div class="row mt" style="justify-content:center">
      <a class="btn btn-primary" href="#/">Back to home</a>
      <a class="btn btn-outline" href="#/flights">Search flights</a>
    </div>
  </div>`;
}

/* --- enhanced admin: adds Traffic + richer Users table (overrides part-2 version) --- */
async function viewAdmin() {
  const app = $("#app");
  if (!state.user || state.user.role !== "admin") { app.innerHTML = emptyState("lock", "Admin access required."); return; }
  app.innerHTML = `<div class="wrap"><h2 class="section-title">${icon("sliders","ic-md")} Admin dashboard</h2><div id="admin-body">${loading()}</div></div>`;
  try {
    const [s, a, bookings, users] = await Promise.all([
      api("/admin/stats"), api("/admin/analytics"), api("/admin/bookings"), api("/admin/users"),
    ]);
    const bar = n => `<div style="background:var(--green);height:12px;border-radius:6px;width:${Math.max(3, Math.round(100 * n / (a.max_daily || 1)))}%"></div>`;
    app.querySelector("#admin-body").innerHTML = `
      <div class="grid grid-3 mb">
        <div class="card stat-card"><div class="num">${s.users.toLocaleString()}</div><div class="lbl">Registered users</div></div>
        <div class="card stat-card"><div class="num">${s.bookings.toLocaleString()}</div><div class="lbl">Total bookings</div></div>
        <div class="card stat-card"><div class="num">${GHS(s.revenue_confirmed)}</div><div class="lbl">Confirmed revenue</div></div>
        <div class="card stat-card"><div class="num">${GHS(s.revenue_pending)}</div><div class="lbl">Pending payment</div></div>
        <div class="card stat-card"><div class="num">${a.pageviews.toLocaleString()}</div><div class="lbl">Page views (consented)</div></div>
        <div class="card stat-card"><div class="num">${s.by_status.pending || 0}/${s.by_status.confirmed || 0}/${s.by_status.cancelled || 0}</div><div class="lbl">Pending / Confirmed / Cancelled</div></div>
      </div>
      <h3 class="section-title" style="font-size:1.15rem">${icon("chart","ic-md")} Traffic — last 14 days</h3>
      <div class="card table-scroll mb"><table class="table"><tr><th>Date</th><th style="width:60%">Page views</th><th>${a.pageviews ? "total" : ""}</th></tr>
        ${a.daily.map(d => `<tr><td>${d.date}</td><td>${bar(d.views)}</td><td>${d.views}</td></tr>`).join("") || "<tr><td colspan=3 class='muted'>No traffic yet</td></tr>"}</table></div>
      <div class="grid grid-2 mb">
        <div><h3 class="section-title" style="font-size:1.15rem">Top pages</h3>
          <div class="card table-scroll"><table class="table"><tr><th>Page</th><th>Views</th></tr>
          ${a.top_pages.map(p => `<tr><td>${esc(p.page)}</td><td>${p.views}</td></tr>`).join("") || "<tr><td colspan=2 class='muted'>No data</td></tr>"}</table></div></div>
        <div><h3 class="section-title" style="font-size:1.15rem">Events</h3>
          <div class="card table-scroll"><table class="table"><tr><th>Event</th><th>Count</th></tr>
          ${Object.entries(a.events).map(([k, n]) => `<tr><td>${esc(k)}</td><td>${n}</td></tr>`).join("") || "<tr><td colspan=2 class='muted'>No events yet</td></tr>"}</table></div></div>
      </div>
      <h3 class="section-title" style="font-size:1.15rem">Recent confirmed revenue</h3>
      <div class="card table-scroll mb"><table class="table"><tr><th>Date</th><th>Bookings</th><th>Revenue</th></tr>
        ${s.daily.map(d => `<tr><td>${d.date}</td><td>${d.bookings}</td><td>${GHS(d.revenue)}</td></tr>`).join("")}</table></div>
      <h3 class="section-title" style="font-size:1.15rem">Latest bookings</h3>
      <div class="card table-scroll mb"><table class="table"><tr><th>Reference</th><th>Type</th><th>Status</th><th>Amount</th><th>Customer</th><th>Travellers</th><th>Action</th></tr>
        ${bookings.map(b => `<tr><td>${b.reference}</td><td>${TYPE_META[b.type]?.icon || ""} ${b.type}</td>
          <td><span class="status-pill ${b.status}">${b.status}</span></td><td>${GHS(b.amount)}</td>
          <td>${esc(b.email)}</td><td>${b.travelers.map(esc).join(", ")}</td>
          <td>${b.status === "pending" ? `<button class="btn btn-primary btn-sm" data-confirm="${b.reference}">Confirm pay</button>` : ""}${b.type === "visa" && b.status === "confirmed" ? ` <button class="btn btn-outline btn-sm" data-schedule="${b.reference}">Schedule interview</button>` : ""}</td></tr>`).join("")}</table></div>
      <h3 class="section-title" style="font-size:1.15rem">Users</h3>
      <div class="card table-scroll"><table class="table"><tr><th>Name</th><th>Email</th><th>Role</th><th>Bookings</th><th>Total spent</th><th>Joined</th></tr>
        ${users.map(u => `<tr><td>${esc(u.full_name)}</td><td>${esc(u.email)}</td><td>${u.role}</td>
          <td>${u.bookings}</td><td>${GHS(u.spent)}</td><td>${esc(u.created_at)}</td></tr>`).join("")}</table></div>`;
    $$("#admin-body [data-confirm]").forEach(btn => btn.onclick = async () => {
      btn.disabled = true;
      try {
        await api(`/admin/bookings/${btn.dataset.confirm}/confirm`, { method: "POST" });
        toast(`Booking ${btn.dataset.confirm} confirmed — ticket issued`, "success");
        viewAdmin();
      } catch (err) { toast(err.message, "error"); btn.disabled = false; }
    });
  } catch (err) { $("#admin-body").innerHTML = emptyState("alert", err.message); }
}

/* --- router v3: adds legal pages + custom 404 + per-route meta + analytics beacon ---
   (function hoisting makes this the effective route() for the whole app) --- */
function route() {
  const raw = (location.hash || "#/").slice(1);
  const [path, query] = raw.split("?");
  const params = new URLSearchParams(query || "");
  const seg = path.split("/")[1] || "home";
  const meta = ROUTE_META[seg] || ROUTE_META.home;
  document.title = meta[0];
  const md = document.querySelector('meta[name="description"]');
  if (md) md.setAttribute("content", meta[1]);
  trackEvent("page_view", "/" + (raw || ""));
  setActiveNav(seg);
  window.scrollTo(0, 0);
  const nav = $("#mainnav"); if (nav) nav.classList.remove("open");
  if (seg === "home" || seg === "") viewHome();
  else if (seg === "flights") viewFlights(params);
  else if (seg === "hotels") viewHotels(params);
  else if (seg === "cars") viewCars(params);
  else if (seg === "visa") viewVisa(params);
  else if (seg === "pay") viewPay(path.split("/")[2]);
  else if (seg === "booking") viewBooking(path.split("/")[2]);
  else if (seg === "bookings") viewBookings();
  else if (seg === "notifications") viewNotifications();
  else if (seg === "admin") viewAdmin();
  else if (seg === "privacy") viewPrivacy();
  else if (seg === "terms") viewTerms();
  else if (seg === "about") viewAbout();
  else if (seg === "contact") viewContact();
  else viewNotFound();
}

/* =====================================================================
   v4 — SVG icon helper (symbols are defined in index.html sprite)
   ===================================================================== */
function icon(name, cls = "") {
  return `<svg class="ic ${cls}" aria-hidden="true" focusable="false"><use href="#i-${name}"></use></svg>`;
}

/* =====================================================================
   v5 — password reset page + account deletion
   ===================================================================== */
function viewReset(params) {
  const token = params.get("token") || "";
  $("#app").innerHTML = `<div class="wrap" style="max-width:480px">
    <div class="card card-pad mt">
      <h2 class="section-title" style="font-size:1.3rem">${icon("lock","ic-md")} Choose a new password</h2>
      ${token ? `
      <form id="reset-form" class="grid mt" style="gap:.8rem">
        <div class="field"><label>New password</label><input name="new_password" type="password" required minlength="6" autocomplete="new-password"></div>
        <div class="field"><label>Confirm password</label><input name="confirm" type="password" required minlength="6" autocomplete="new-password"></div>
        <button class="btn btn-primary btn-block">Update password</button>
      </form>` : `<p class="muted mt">This reset link is missing its token. <a href="#/" onclick="setTimeout(()=>openAuthModal('Sign in'),50)">Request a new one</a>.</p>`}
    </div></div>`;
  const form = $("#reset-form");
  if (!form) return;
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    if (fd.get("new_password") !== fd.get("confirm")) return toast("Passwords don't match", "error");
    const btn = form.querySelector("button");
    btn.disabled = true;
    try {
      await api("/auth/reset-password", { method: "POST", body: { token, new_password: fd.get("new_password") } });
      toast("Password updated — sign in with your new password", "success");
      location.hash = "#/";
      openAuthModal("Password updated — sign in");
    } catch (err) { toast(err.message, "error"); btn.disabled = false; }
  };
}

function openDeleteAccount() {
  if (!state.user) return;
  openModal(`
    <h3 class="mb" style="color:var(--red)">Delete your account?</h3>
    <p class="small muted mb">This permanently anonymises your profile, cancels unpaid bookings and removes your notifications. Confirmed booking history is kept for records. This cannot be undone.</p>
    <form id="delete-form" class="grid" style="gap:.8rem">
      <div class="field"><label>Enter your password to confirm</label><input name="password" type="password" required autocomplete="current-password"></div>
      <div class="row">
        <button type="button" class="btn btn-outline" id="delete-cancel">Keep my account</button>
        <button class="btn btn-danger" id="delete-confirm">Delete permanently</button>
      </div>
    </form>`);
  $("#delete-cancel").onclick = closeModal;
  $("#delete-form").onsubmit = async e => {
    e.preventDefault();
    const btn = $("#delete-confirm");
    btn.disabled = true;
    try {
      await api("/auth/account", { method: "DELETE", body: { password: new FormData(e.target).get("password") } });
      closeModal();
      state.token = ""; state.user = null;
      localStorage.removeItem("dt_token");
      renderChrome(); location.hash = "#/"; route();
      toast("Your account has been deleted. Sorry to see you go.", "success");
    } catch (err) { toast(err.message, "error"); btn.disabled = false; }
  };
}

// wire the user-menu delete entry + extend router (hoisting: this route() wins)
const _delBtn = $("#btn-delete-account");
if (_delBtn) _delBtn.onclick = openDeleteAccount;

function route() {
  const raw = (location.hash || "#/").slice(1);
  const [path, query] = raw.split("?");
  const params = new URLSearchParams(query || "");
  const seg = path.split("/")[1] || "home";
  const meta = ROUTE_META[seg] || ROUTE_META.home;
  document.title = meta[0];
  const md = document.querySelector('meta[name="description"]');
  if (md) md.setAttribute("content", meta[1]);
  trackEvent("page_view", "/" + (raw || ""));
  setActiveNav(seg);
  window.scrollTo(0, 0);
  const nav = $("#mainnav"); if (nav) nav.classList.remove("open");
  if (seg === "home" || seg === "") viewHome();
  else if (seg === "flights") viewFlights(params);
  else if (seg === "hotels") viewHotels(params);
  else if (seg === "cars") viewCars(params);
  else if (seg === "visa") viewVisa(params);
  else if (seg === "pay") viewPay(path.split("/")[2]);
  else if (seg === "booking") viewBooking(path.split("/")[2]);
  else if (seg === "bookings") viewBookings();
  else if (seg === "notifications") viewNotifications();
  else if (seg === "admin") viewAdmin();
  else if (seg === "reset") viewReset(params);
  else if (seg === "privacy") viewPrivacy();
  else if (seg === "terms") viewTerms();
  else if (seg === "about") viewAbout();
  else if (seg === "contact") viewContact();
  else viewNotFound();
}

/* =====================================================================
   v6 — Firebase Authentication (Google sign-in via popup)
   ===================================================================== */
let _fbPromise = null;

async function ensureFirebase() {
  if (!_fbPromise) {
    _fbPromise = (async () => {
      const cfg = await api("/auth/firebase-config");
      const app = await import("https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js");
      const auth = await import("https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js");
      return { app: app.initializeApp(cfg), auth };
    })();
  }
  return _fbPromise;
}

async function signInWithGoogle() {
  const btn = $("#google-btn");
  btn.disabled = true;
  try {
    console.log("[google-auth] 1/5 fetching firebase config from backend...");
    const fb = await ensureFirebase();
    console.log("[google-auth] 2/5 firebase initialized OK, opening Google popup...");
    const provider = new fb.auth.GoogleAuthProvider();
    provider.addScope("email");
    const cred = await fb.auth.signInWithPopup(fb.auth.getAuth(), provider);
    console.log("[google-auth] 3/5 popup returned Google account:", cred.user.email);
    const idToken = await cred.user.getIdToken();
    console.log("[google-auth] 4/5 ID token obtained, verifying with our backend...");
    const r = await api("/auth/firebase", { method: "POST", body: { id_token: idToken } });
    console.log("[google-auth] 5/5 backend accepted:", r.user.email);
    state.token = r.access_token;
    localStorage.setItem("dt_token", r.access_token);
    state.user = r.user;
    closeModal(); renderChrome();
    toast(`Welcome, ${r.user.full_name.split(" ")[0]}!`, "success");
    route();
  } catch (err) {
    console.error("[google-auth] FAILED at step:", err && (err.code || err.message), err);
    if (err && (err.code === "auth/popup-closed-by-user" || err.code === "auth/cancelled-popup-request")) {
      toast("Sign-in popup closed");
    } else {
      toast((err.code ? err.code + " — " : "") + (err.message || "Google sign-in failed"), "error");
    }
  }
  btn.disabled = false;
}

/* =====================================================================
   v7 — on-screen selection cart + modal checkout forms
   ===================================================================== */
let _selCart = null;
function dismissCart() { if (_selCart) { _selCart.remove(); _selCart = null; } }

function showCart({ icon: icn, title, sub, amount, cta, onContinue }) {
  dismissCart();
  const el = document.createElement("div");
  el.className = "sel-cart";
  el.innerHTML = `
    <button class="sel-cart-x" aria-label="Dismiss">${icon("x")}</button>
    <h4>${icon(icn, "ic-sm")} ${esc(title)}</h4>
    <div class="sc-sub">${esc(sub)}</div>
    <div class="sc-amount">${GHS(amount)}</div>
    <button class="btn btn-primary btn-sm" id="sel-cart-go">${esc(cta)}</button>`;
  document.body.appendChild(el);
  _selCart = el;
  el.querySelector(".sel-cart-x").onclick = dismissCart;
  el.querySelector("#sel-cart-go").onclick = onContinue;
}

function flightFormHtml(p, legs, total) {
  const paxCount = p.adults + p.children + p.infants;
  return `
    <h3 class="section-title" style="font-size:1.15rem">Traveller details</h3>
    <form id="flight-pax-form" class="grid mt" style="gap:.8rem">
      ${Array.from({ length: paxCount }, (_, i) => {
        const type = i < p.adults ? "adult" : (i < p.adults + p.children ? "child" : "infant");
        return `<div class="pax-card"><h4>${type} ${i + 1}</h4><div class="field-row">
          <div class="field"><label>Title</label><select name="p${i}_title"><option>Mr</option><option>Mrs</option><option>Ms</option><option>Miss</option><option>Dr</option><option>Chief</option></select></div>
          <div class="field"><label>First name</label><input name="p${i}_first" required></div>
          <div class="field"><label>Last name</label><input name="p${i}_last" required></div>
          <input type="hidden" name="p${i}_type" value="${type}">
        </div></div>`; }).join("")}
      <div class="pax-card"><h4>Contact</h4><div class="field-row">
        <div class="field"><label>Email</label><input name="contact_email" type="email" required value="${esc(state.user?.email || "")}"></div>
        <div class="field"><label>Phone</label><input name="contact_phone" required value="${esc(state.user?.phone || "")}"></div>
      </div></div>
      ${(p.bags || 0) ? `<div class="sum-row"><span>Checked bags — ${p.bags} × ${p.adults + p.children + p.infants} traveler(s)</span><span>${GHS((p.bags || 0) * (p.adults + p.children + p.infants) * 150)}</span></div>` : ""}
      <div class="sum-row total"><span>Total (incl. service fee & bags)</span><span>${GHS(total)}</span></div>
      <button class="btn btn-primary btn-block">Create booking & pay</button>
    </form>`;
}
function bindFlightForm(form, p, legs) {
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const paxCount = p.adults + p.children + p.infants;
    const passengers = Array.from({ length: paxCount }, (_, i) => ({
      type: fd.get(`p${i}_type`), title: fd.get(`p${i}_title`),
      first_name: fd.get(`p${i}_first`), last_name: fd.get(`p${i}_last`),
    }));
    const btn = form.querySelector("button");
    btn.disabled = true;
    try {
      const r = await api("/bookings/flight", { method: "POST", body: {
        trip_type: p.trip, cabin: p.cabin,
        legs: legs.map(l => ({ origin: l.origin, dest: l.dest, date: l.date, flight_key: l.flight_key })),
        passengers, contact_email: fd.get("contact_email"), contact_phone: fd.get("contact_phone"),
        bags: p.bags || 0,
      }});
      closeModal(); dismissCart();
      toast("Booking created — complete payment to confirm", "success");
      location.hash = `#/pay/${r.reference}`;
    } catch (err) { toast(err.message, "error"); btn.disabled = false; }
  };
}

function renderHotelBooking(hotel, room, p, nights) {
  showCart({ icon: "hotel", title: hotel.name,
    sub: `${room.type} · ${fmtDate(p.checkin)} → ${fmtDate(p.checkout)} · ${p.rooms} room(s)`,
    amount: room.pricing.total, cta: "Enter guest details →",
    onContinue: () => {
      openModal(`
        <h3 class="section-title" style="font-size:1.15rem">Guest & payment details</h3>
        <p class="muted small mb">${esc(hotel.name)} · ${esc(room.type)} · ${fmtDate(p.checkin)} → ${fmtDate(p.checkout)}</p>
        <form id="hotel-book-form" class="grid" style="gap:.8rem">
          <div class="field"><label>Lead guest name</label><input name="guest_name" required value="${esc(state.user?.full_name || "")}"></div>
          <div class="field-row">
            <div class="field"><label>Email</label><input name="contact_email" type="email" required value="${esc(state.user?.email || "")}"></div>
            <div class="field"><label>Phone</label><input name="contact_phone" required value="${esc(state.user?.phone || "")}"></div>
          </div>
          <div class="field"><label>Special requests (optional)</label><textarea name="special_requests" rows="2"></textarea></div>
          <div class="sum-row total"><span>Total incl. VAT</span><span>${GHS(room.pricing.total)}</span></div>
          <button class="btn btn-primary btn-block">Create reservation & pay</button>
        </form>`);
      bindHotelForm($("#hotel-book-form"), hotel, room, p);
    } });
}
function bindHotelForm(form, hotel, room, p) {
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const btn = form.querySelector("button");
    btn.disabled = true;
    try {
      const r = await api("/bookings/hotel", { method: "POST", body: {
        hotel_id: hotel.id, room_type: room.type, room_key: room.rate_key || null, hotel_name: hotel.name,
        checkin: p.checkin, checkout: p.checkout, rooms: p.rooms, guests: p.guests,
        guest_name: fd.get("guest_name"), contact_email: fd.get("contact_email"),
        contact_phone: fd.get("contact_phone"), special_requests: fd.get("special_requests"),
      }});
      closeModal(); dismissCart();
      toast("Reservation created — complete payment to confirm", "success");
      location.hash = `#/pay/${r.reference}`;
    } catch (err) { toast(err.message, "error"); btn.disabled = false; }
  };
}

function renderCarBooking(car, p) {
  showCart({ icon: "car", title: `${car.name}`,
    sub: `${p.city} · ${fmtDate(p.pickup_date)} → ${fmtDate(p.return_date)} · ${car.pricing.days} day(s)`,
    amount: car.pricing.total, cta: "Enter driver details →",
    onContinue: () => {
      openModal(`
        <h3 class="section-title" style="font-size:1.15rem">Driver details</h3>
        <p class="muted small mb">${esc(car.name)} · ${esc(p.city)} · ${fmtDate(p.pickup_date)} → ${fmtDate(p.return_date)}</p>
        <form id="car-book-form" class="grid" style="gap:.8rem">
          <div class="field-row">
            <div class="field"><label>Driver name</label><input name="driver_name" required value="${esc(state.user?.full_name || "")}"></div>
            <div class="field"><label>Driver age</label><input name="driver_age" type="number" min="18" max="90" value="30" required></div>
          </div>
          <div class="field"><label>Pickup location</label>
            <select name="pickup_location"><option>Airport</option><option>City centre office</option><option>Hotel delivery</option></select></div>
          <div class="field-row">
            <div class="field"><label>Email</label><input name="contact_email" type="email" required value="${esc(state.user?.email || "")}"></div>
            <div class="field"><label>Phone</label><input name="contact_phone" required value="${esc(state.user?.phone || "")}"></div>
          </div>
          <div class="sum-row total"><span>Total incl. VAT</span><span>${GHS(car.pricing.total)}</span></div>
          <button class="btn btn-primary btn-block">Create booking & pay</button>
        </form>`);
      bindCarForm($("#car-book-form"), car, p);
    } });
}
function bindCarForm(form, car, p) {
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const btn = form.querySelector("button");
    btn.disabled = true;
    try {
      const r = await api("/bookings/car", { method: "POST", body: {
        city: p.city, category: car.code, pickup_date: p.pickup_date, return_date: p.return_date,
        pickup_location: fd.get("pickup_location"), driver_name: fd.get("driver_name"),
        driver_age: +fd.get("driver_age"), contact_email: fd.get("contact_email"),
        contact_phone: fd.get("contact_phone"),
      }});
      closeModal(); dismissCart();
      toast("Car booking created — complete payment to confirm", "success");
      location.hash = `#/pay/${r.reference}`;
    } catch (err) { toast(err.message, "error"); btn.disabled = false; }
  };
}

document.addEventListener("click", async e => {
  const btn = e.target.closest("[data-schedule]");
  if (!btn) return;
  const date = prompt("Interview date (YYYY-MM-DD):", todayISO());
  if (!date) return;
  const time = prompt("Interview time (e.g. 10:00):", "10:00") || "";
  const center = prompt("Centre/location:", "Brother'sTrust HQ - Accra") || "";
  try {
    await api(`/admin/bookings/${btn.dataset.schedule}/schedule`, { method: "POST", body: { date, time, center } });
    toast("Interview scheduled — customer notified", "success");
    viewAdmin();
  } catch (err) { toast(err.message, "error"); }
});

/* =====================================================================
   v8 — airport codes reference modal
   ===================================================================== */
function airportCodesHtml() {
  const groups = {};
  (state.meta.airports || []).forEach(a => {
    const c = a.country || "Other";
    (groups[c] = groups[c] || []).push(a);
  });
  const list = Object.entries(groups).sort().map(([country, arr]) => `
    <div class="small" style="font-weight:700;margin:.6rem 0 .3rem">${esc(country)}</div>
    <div class="row" style="gap:.3rem">${arr.map(a =>
      `<button type="button" class="slot-chip ac-item" style="padding:.28rem .5rem;font-size:.78rem" data-s="${(a.code + " " + a.city + " " + country).toLowerCase()}"><b>${a.code}</b>&nbsp;${esc(a.city)}</button>`).join("")}</div>`).join("");
  return `
    <h3 class="section-title" style="font-size:1.2rem">${icon("plane","ic-md")} Airport codes</h3>
    <div class="field mt mb"><input id="ac-filter" placeholder="Filter by city, country or code…" autocomplete="off"></div>
    <div id="ac-list" style="max-height:52vh;overflow:auto">${list}</div>`;
}
function wireAirportCodes() {
  const input = $("#ac-filter");
  if (!input) return;
  input.oninput = () => {
    const q = input.value.trim().toLowerCase();
    $$(".ac-item").forEach(el => { el.style.display = !q || el.dataset.s.includes(q) ? "" : "none"; });
    $$("#ac-list > div.small").forEach(h => {
      let el = h.nextElementSibling, any = false;
      while (el && !el.classList.contains("small")) {
        if (el.style.display !== "none") any = true;
        el = el.nextElementSibling;
      }
      h.style.display = any ? "" : "none";
    });
  };
  setTimeout(() => input.focus(), 50);
}
