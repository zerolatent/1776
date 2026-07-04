const storedSession = safeJson(localStorage.getItem("1776_session"));

const state = {
  token: localStorage.getItem("1776_token") || storedSession?.token || "",
  session: storedSession || null,
  rules: [],
  selectedRule: null,
  selectedSources: [],
  selectedForecasts: [],
  rulesRequestId: 0,
  detailRequestId: 0,
  briefRequestId: 0,
  feedStatus: "",
};

const $ = (id) => document.getElementById(id);

function safeJson(value) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers["X-Session-Token"] = state.token;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    let message = text || response.statusText;
    try {
      const payload = JSON.parse(text);
      message = payload.detail || message;
    } catch {
      // Keep the raw response text when the API does not return JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function setBusy(button, busy, label) {
  if (!button) return;
  button.disabled = busy;
  if (label) button.textContent = label;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function pluralize(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function statusClass(value) {
  return escapeHtml(String(value || "").replaceAll(" ", ""));
}

function profileText() {
  return [state.session?.persona, state.session?.interests].filter(Boolean).join(" - ");
}

function setAppMode() {
  const loggedIn = Boolean(state.token);
  document.body.classList.toggle("logged-in", loggedIn);
  document.body.classList.toggle("logged-out", !loggedIn);
  $("profileBadge").textContent = loggedIn ? profileText() || state.session?.name || "Signed in" : "";
  $("settingsProfile").textContent = loggedIn ? profileText() || state.session?.email || "Signed in" : "";
  $("profileSummary").textContent = loggedIn
    ? `Ranked for ${profileText() || state.session?.name || "your profile"}.`
    : "Your feed is ranked by the persona and topics in your profile.";
}

function publicVoiceForRule(rule, brief = null) {
  const signal = String(brief?.public_heard_signal || rule?.heard_signal || "").trim();
  const findings = rule?.findings || [];
  const concerns = rule?.top_concerns || [];
  const lowered = signal.toLowerCase();
  if (findings.length && !lowered.includes("unclear")) {
    return {
      label: signal || findings[0].label || "Public response found",
      body: findings[0].summary || "The official record includes a public-comment finding.",
    };
  }
  if (concerns.length) {
    return {
      label: "Agency response found",
      body: "The official record includes public comments and an agency response.",
    };
  }
  if (rule?.action_type === "Proposed" || lowered.includes("not yet")) {
    return {
      label: "Comment record pending",
      body: "This rule is still proposed. Agencies usually summarize public comments later, when they adopt or withdraw the rule.",
    };
  }
  if (["Changed", "Unchanged", "Partially addressed"].includes(signal)) {
    return {
      label: signal,
      body: "The official record includes an agency response to public comments.",
    };
  }
  return {
    label: "No comment record found",
    body: "1776 did not find a Comment/Response section in the official notice for this rule.",
  };
}

function humanizeBriefBody(body, rule, brief) {
  const voice = publicVoiceForRule(rule, brief);
  return String(body || brief?.status_text || "")
    .replace("Were people heard? Unclear from record.", `Public voice: ${voice.label}.`)
    .replace("1776 did not find enough public Comment/Response evidence to say more.", voice.body)
    .replace("Tribune did not find enough public Comment/Response evidence to say more.", voice.body);
}

function renderMetrics() {
  const counts = state.rules.reduce(
    (memo, rule) => {
      memo.total += 1;
      memo[rule.action_type] = (memo[rule.action_type] || 0) + 1;
      if (rule.forecast_count > 0) memo.forecasts += 1;
      if (rule.watched) memo.watched += 1;
      return memo;
    },
    { total: 0, Proposed: 0, Adopted: 0, Emergency: 0, Withdrawn: 0, forecasts: 0, watched: 0 },
  );
  $("feedMetrics").textContent = `${counts.total} actions, ${counts.Proposed} proposed, ${counts.Adopted} adopted`;
}

function renderFeed() {
  const feed = $("ruleFeed");
  const selectedId = state.selectedRule?.id;
  renderMetrics();
  if (!state.rules.length) {
    feed.innerHTML = "";
    $("feedStatus").textContent = state.feedStatus || "No matching rules.";
    return;
  }
  $("feedStatus").textContent = state.feedStatus || `${state.rules.length} relevant rule actions`;
  feed.innerHTML = state.rules
    .map((rule) => {
      const body = rule.match_reason || rule.why_matters || rule.summary;
      const publicVoice = publicVoiceForRule(rule);
      return `
        <button
          class="rule-card ${selectedId === rule.id ? "active" : ""}"
          data-rule-id="${rule.id}"
          type="button"
          aria-pressed="${selectedId === rule.id ? "true" : "false"}"
        >
          <div class="card-meta">
            <span class="pill ${statusClass(rule.action_type)}">${escapeHtml(rule.action_type)}</span>
            <span>${escapeHtml(rule.tac_citation)}</span>
          </div>
          <strong>${escapeHtml(rule.title)}</strong>
          <span class="agency-line">${escapeHtml(rule.agency)}</span>
          <p class="${rule.match_reason ? "match-reason" : ""}">${escapeHtml(body)}</p>
          <div class="card-signals">
            <span>${escapeHtml(publicVoice.label)}</span>
            ${
              rule.forecast_count
                ? `<span>${escapeHtml(pluralize(rule.forecast_count, "market"))}</span>`
                : ""
            }
            ${rule.watched ? `<span>Watched</span>` : ""}
          </div>
        </button>
      `;
    })
    .join("");
  feed.querySelectorAll("[data-rule-id]").forEach((button) => {
    button.addEventListener("click", () => selectRule(Number(button.dataset.ruleId)).catch(showError));
  });
}

async function loadRules() {
  if (!state.token) return;
  const requestId = ++state.rulesRequestId;
  const query = new URLSearchParams();
  if ($("typeFilter").value) query.set("action_type", $("typeFilter").value);
  state.feedStatus = profileText() ? `Ranking rules for ${profileText()}.` : "Loading current rule actions.";
  $("feedStatus").textContent = state.feedStatus;
  const nextRules = await api(`/api/rules?${query.toString()}`);
  if (requestId !== state.rulesRequestId) return;
  state.rules = nextRules;
  state.feedStatus = nextRules.length
    ? profileText()
      ? `${nextRules.length} rule actions ranked for your profile.`
      : `${nextRules.length} current rule actions.`
    : "No live rules loaded yet.";
  renderFeed();
  if (!state.rules.length) {
    showEmptyState("No rules loaded", "Refresh official data to load the latest rule actions.");
    return;
  }
  const currentVisible = state.rules.some((rule) => rule.id === state.selectedRule?.id);
  if (state.rules[0] && (!state.selectedRule || !currentVisible)) await selectRule(state.rules[0].id);
}

async function runAISearch() {
  if (!state.token) throw new Error("Create a profile before searching.");
  const queryText = $("searchInput").value.trim();
  if (!queryText) {
    await loadRules();
    return;
  }
  const requestId = ++state.rulesRequestId;
  const button = $("aiSearchButton");
  setBusy(button, true, "Searching...");
  state.feedStatus = `AI is matching "${queryText}" to official rule records.`;
  $("feedStatus").textContent = state.feedStatus;
  try {
    const nextRules = await api("/api/rules/ai-search", {
      method: "POST",
      body: JSON.stringify({ query: queryText, action_type: $("typeFilter").value || null }),
    });
    if (requestId !== state.rulesRequestId) return;
    state.rules = nextRules;
    state.feedStatus = nextRules.length
      ? `AI found ${pluralize(nextRules.length, "relevant rule action")}.`
      : `AI found no official rule actions for "${queryText}".`;
    renderFeed();
    if (!state.rules.length) {
      showEmptyState("No AI matches", "Try a broader phrase such as retiree, data centers, or crypto.");
      return;
    }
    await selectRule(state.rules[0].id);
  } finally {
    setBusy(button, false, "Ask AI");
  }
}

function showEmptyState(title, body) {
  state.selectedRule = null;
  state.selectedSources = [];
  state.selectedForecasts = [];
  $("ruleDetail").classList.add("hidden");
  $("emptyState").classList.remove("hidden");
  $("emptyState").querySelector("h2").textContent = title;
  $("emptyState").querySelector("p").textContent = body;
  $("detailAgency").textContent = "";
  $("detailTitle").textContent = "";
  $("detailStatus").textContent = "";
}

async function selectRule(ruleId) {
  const requestId = ++state.detailRequestId;
  const [rule, sources, forecasts] = await Promise.all([
    api(`/api/rules/${ruleId}`),
    api(`/api/rules/${ruleId}/sources`),
    api(`/api/forecasts?rule_id=${ruleId}`),
  ]);
  if (requestId !== state.detailRequestId) return;
  state.selectedRule = rule;
  state.selectedSources = sources;
  state.selectedForecasts = forecasts;
  $("emptyState").classList.add("hidden");
  $("ruleDetail").classList.remove("hidden");
  $("detailAgency").textContent = `${rule.agency} | ${rule.tac_citation}`;
  $("detailTitle").textContent = rule.title;
  $("detailStatus").textContent = rule.status;
  $("detailStatus").className = `pill ${statusClass(rule.action_type)}`;
  $("detailSummary").textContent = rule.summary;
  $("detailWhy").textContent = rule.why_matters;
  $("heardSignal").textContent = publicVoiceForRule(rule).label;
  $("briefStatus").textContent = "Checking AI brief...";
  $("sourceLink").href = rule.source_url;
  $("watchInput").value = rule.agency;
  renderFacts(rule, sources, forecasts);
  renderConcerns(rule);
  renderAuthority(rule.authority_links || []);
  renderSources(sources);
  renderForecasts(forecasts);
  renderFeed();
  ensureBrief(ruleId).catch(showError);
}

function renderFacts(rule, sources, forecasts) {
  $("detailFacts").innerHTML = [
    ["Status", rule.status],
    ["Citation", rule.tac_citation],
    ["Receipts", sources.length ? pluralize(sources.length, "source") : "None stored"],
    ["Markets", forecasts.length ? pluralize(forecasts.length, "open market") : "None open"],
  ]
    .map(
      ([label, value]) => `
        <div class="fact">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `,
    )
    .join("");
}

function renderBrief(brief) {
  const publicVoice = publicVoiceForRule(state.selectedRule, brief);
  $("detailSummary").textContent = brief.plain_summary;
  $("detailWhy").textContent = humanizeBriefBody(brief.body, state.selectedRule, brief);
  $("heardSignal").textContent = publicVoice.label;
  $("briefStatus").textContent = `${brief.status_text} (${pluralize(brief.source_ids.length, "source")})`;
}

async function ensureBrief(ruleId) {
  const requestId = ++state.briefRequestId;
  const button = $("investigateButton");
  setBusy(button, true, "AI brief running...");
  try {
    let brief;
    try {
      brief = await api(`/api/rules/${ruleId}/brief`);
    } catch (error) {
      if (!String(error.message).includes("Brief not found")) throw error;
      $("briefStatus").textContent = "Running AI brief from the official record...";
      const result = await api(`/api/rules/${ruleId}/investigate`, { method: "POST" });
      brief = result.brief;
      const forecasts = await api(`/api/forecasts?rule_id=${ruleId}`);
      if (requestId === state.briefRequestId && state.selectedRule?.id === ruleId) {
        state.selectedForecasts = forecasts;
        renderForecasts(forecasts);
        renderFacts(state.selectedRule, state.selectedSources, forecasts);
      }
    }
    if (requestId !== state.briefRequestId || state.selectedRule?.id !== ruleId) return;
    renderBrief(brief);
  } catch (error) {
    if (requestId === state.briefRequestId && state.selectedRule?.id === ruleId) {
      $("briefStatus").textContent = `AI brief unavailable: ${error.message}`;
    }
    throw error;
  } finally {
    if (requestId === state.briefRequestId && state.selectedRule?.id === ruleId) {
      setBusy(button, false, "Refresh AI brief");
    }
  }
}

function renderConcerns(rule) {
  const concerns = $("concernsList");
  const topConcerns = rule.top_concerns || [];
  const findings = rule.findings || [];
  if (!topConcerns.length && !findings.length) {
    const publicVoice = publicVoiceForRule(rule);
    concerns.innerHTML = `
      <div class="concern empty">
        <strong>${escapeHtml(publicVoice.label)}</strong>
        <p>${escapeHtml(publicVoice.body)}</p>
      </div>
    `;
    return;
  }
  const findingItems = findings.map((item) => ({
    title: item.label || "Record note",
    body: item.summary || "",
    response: "",
  }));
  const concernItems = topConcerns.map((item) => ({
    title: item.disposition || "Comment/Response",
    body: item.concern || "",
    response: item.agency_response || "",
  }));
  concerns.innerHTML = [...findingItems, ...concernItems]
    .slice(0, 4)
    .map(
      (item) => `
        <div class="concern">
          <strong>${escapeHtml(item.title)}</strong>
          <p>${escapeHtml(item.body)}</p>
          ${item.response ? `<small>Agency response</small><p>${escapeHtml(item.response)}</p>` : ""}
        </div>
      `,
    )
    .join("");
}

function renderAuthority(links) {
  if (!links.length) {
    $("authorityBlock").classList.add("hidden");
    $("authorityList").innerHTML = "";
    return;
  }
  $("authorityBlock").classList.remove("hidden");
  $("authorityList").innerHTML = links
    .map(
      (link) => `
        <a class="authority-item" href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer">
          <strong>${escapeHtml(link.citation)}</strong>
          <span>${escapeHtml(link.summary)}</span>
        </a>
      `,
    )
    .join("");
}

function renderSources(sources) {
  $("sourceList").innerHTML = sources.length
    ? sources
        .map(
          (source) => `
            <div class="source-item">
              <div class="source-item-head">
                <strong>${escapeHtml(source.label)}</strong>
                <span>Receipt ${escapeHtml(source.id)}</span>
              </div>
              <p>${escapeHtml(source.snippet)}</p>
              <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">Open receipt</a>
            </div>
          `,
        )
        .join("")
    : `<div class="source-item"><p>No source receipts are stored for this rule.</p></div>`;
}

function renderForecasts(forecasts) {
  $("forecastHint").textContent = forecasts.length ? `${forecasts.length} open` : "none open";
  $("forecastList").innerHTML = forecasts.length
    ? forecasts
        .map((forecast) => {
          const marketProbability = Math.round(forecast.aggregate_probability * 100);
          const userProbability = Math.round((forecast.user_probability ?? forecast.aggregate_probability) * 100);
          const marketTitle = forecast.display_question || forecast.question;
          return `
            <div class="forecast-card market-card" data-forecast-id="${forecast.id}" style="--yes:${marketProbability}%">
              <div class="market-top">
                <span class="market-label">${escapeHtml(forecast.status)}</span>
                <strong>${escapeHtml(marketTitle)}</strong>
              </div>
              <div class="market-prices" aria-label="Market probability">
                <div>
                  <span>Yes</span>
                  <strong class="yes-price">${marketProbability}%</strong>
                </div>
                <div>
                  <span>No</span>
                  <strong>${100 - marketProbability}%</strong>
                </div>
              </div>
              <div class="market-meter" aria-hidden="true">
                <span></span>
              </div>
              <details class="market-resolution">
                <summary>Market rules</summary>
                <p class="market-definition"><strong>Exact market:</strong> ${escapeHtml(forecast.question)}</p>
                <p>${escapeHtml(forecast.resolution_criteria)}</p>
                <small>Source of truth: ${escapeHtml(forecast.source_of_truth)}</small>
              </details>
              <label class="trade-ticket">
                <span>Your forecast <strong class="forecast-probability">${userProbability}% Yes</strong></span>
                <input type="range" min="0" max="100" value="${userProbability}" />
              </label>
              <button type="button">${state.token ? "Submit forecast" : "Sign in to submit"}</button>
            </div>
          `;
        })
        .join("")
    : `<div class="forecast-card empty"><p>No forecast market is open for this rule.</p></div>`;
  $("forecastList").querySelectorAll(".forecast-card").forEach((card) => {
    const slider = card.querySelector("input");
    const label = card.querySelector(".forecast-probability");
    const button = card.querySelector("button");
    if (!slider || !button) return;
    slider.addEventListener("input", () => {
      label.textContent = `${slider.value}% Yes`;
    });
    button.addEventListener("click", async () => {
      try {
        await submitForecast(Number(card.dataset.forecastId), Number(slider.value) / 100);
      } catch (error) {
        showError(error);
      }
    });
  });
}

async function submitForecast(forecastId, probability) {
  if (!state.token) throw new Error("Sign in before submitting a forecast.");
  await api(`/api/forecasts/${forecastId}/position`, {
    method: "POST",
    body: JSON.stringify({ probability, rationale: "" }),
  });
  await selectRule(state.selectedRule.id);
}

async function runInvestigation() {
  if (!state.selectedRule) return;
  const ruleId = state.selectedRule.id;
  const button = $("investigateButton");
  setBusy(button, true, "Refreshing...");
  $("briefStatus").textContent = "Refreshing AI brief...";
  try {
    await api(`/api/rules/${ruleId}/investigate`, { method: "POST" });
    await selectRule(ruleId);
  } finally {
    setBusy(button, false, "Refresh AI brief");
  }
}

async function ingestCurrent() {
  const button = $("ingestButton");
  setBusy(button, true, "Reading register...");
  try {
    await api("/api/ingest/texas-register", { method: "POST" });
    state.selectedRule = null;
    await loadRules();
  } finally {
    setBusy(button, false, "Refresh official data");
    $("settingsMenu").open = false;
  }
}

async function login() {
  const payload = {
    name: $("nameInput").value.trim() || "Citizen",
    email: $("emailInput").value.trim(),
    persona: $("personaSelect").value.trim(),
    interests: $("interestsInput").value.trim(),
  };
  if (!payload.email) throw new Error("Email is required.");
  if (!payload.persona && !payload.interests) throw new Error("Choose a persona or enter one topic.");
  $("landingStatus").textContent = "Creating personalized feed...";
  const session = await api("/api/auth/login", { method: "POST", body: JSON.stringify(payload) });
  state.token = session.token;
  state.session = session;
  localStorage.setItem("1776_token", session.token);
  localStorage.setItem("1776_session", JSON.stringify(session));
  setAppMode();
  await Promise.all([loadRules(), loadAlerts()]);
}

function signOut() {
  state.token = "";
  state.session = null;
  state.rules = [];
  state.selectedRule = null;
  localStorage.removeItem("1776_token");
  localStorage.removeItem("1776_session");
  $("settingsMenu").open = false;
  $("ruleFeed").innerHTML = "";
  $("alertList").innerHTML = "";
  $("landingStatus").textContent = "";
  setAppMode();
  showEmptyState("No rule selected", "Ask AI for a topic or open a personalized rule to read the brief.");
}

async function createWatch() {
  if (!state.token) throw new Error("Sign in before creating a watchlist.");
  const value = $("watchInput").value.trim();
  if (!value) return;
  $("alertList").innerHTML = `<div class="alert"><p>Creating watchlist...</p></div>`;
  await api("/api/watchlists", { method: "POST", body: JSON.stringify({ kind: "topic", value }) });
  await loadAlerts();
}

async function watchSelected() {
  if (!state.selectedRule) return;
  $("watchInput").value = state.selectedRule.agency;
  await createWatch();
}

async function loadAlerts() {
  if (!state.token) {
    $("alertList").innerHTML = "";
    return;
  }
  const alerts = await api("/api/alerts");
  $("alertList").innerHTML = alerts.length
    ? alerts
        .map(
          (alert) => `
            <div class="alert">
              <strong>${escapeHtml(alert.title)}</strong>
              <p>${escapeHtml(alert.body)}</p>
              <a href="${escapeHtml(alert.source_url)}" target="_blank" rel="noreferrer">Open source</a>
            </div>
          `,
        )
        .join("")
    : `<div class="alert"><p>No alerts yet.</p></div>`;
}

function applyPersonaPreset(button) {
  $("personaSelect").value = button.dataset.persona || "";
  $("interestsInput").value = button.dataset.interests || "";
  document.querySelectorAll(".persona-chip").forEach((chip) => chip.classList.remove("active"));
  button.classList.add("active");
}

function wireEvents() {
  $("searchInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runAISearch().catch(showError);
  });
  $("aiSearchButton").addEventListener("click", () => runAISearch().catch(showError));
  $("typeFilter").addEventListener("change", () => {
    if ($("searchInput").value.trim()) {
      runAISearch().catch(showError);
    } else {
      loadRules().catch(showError);
    }
  });
  $("ingestButton").addEventListener("click", () => ingestCurrent().catch(showError));
  $("loginButton").addEventListener("click", () => login().catch(showError));
  $("signOutButton").addEventListener("click", signOut);
  $("investigateButton").addEventListener("click", () => runInvestigation().catch(showError));
  $("createWatchButton").addEventListener("click", () => createWatch().catch(showError));
  $("watchButton").addEventListener("click", () => watchSelected().catch(showError));
  $("alertsButton").addEventListener("click", () => loadAlerts().catch(showError));
  document.querySelectorAll(".persona-chip").forEach((button) => {
    button.addEventListener("click", () => applyPersonaPreset(button));
  });
}

function showError(error) {
  const message = error.message || String(error);
  if (state.token) {
    $("feedStatus").textContent = message;
  } else {
    $("landingStatus").textContent = message;
  }
}

setAppMode();
wireEvents();
if (state.token) {
  loadRules().catch(showError);
  loadAlerts().catch(showError);
}
