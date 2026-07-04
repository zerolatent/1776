# 1776

1776 is the working implementation of the Tribune product concept: an AI
accountability agent for public rulemaking.

It answers the question citizens, reporters, advocates, and small businesses
should be able to ask of any government rule:

```text
How did this rule get made, and did public input matter?
```

1776 reads real regulatory records, turns them into short citizen-facing briefs,
links every claim back to source receipts, ranks rules by a user's persona and
interests, and lets users follow agencies or topics, receive source-backed
alerts, and submit play-money civic forecasts.

The product thesis is simple:

```text
Everyone is building AI for government efficiency.
1776 is AI for government legitimacy.
```

As agencies and regulated institutions gain AI-speed capacity to analyze,
rewrite, and enforce rules, the public needs AI-speed capacity to see what
happened in the record. 1776 is not an accusation engine and not a partisan
scorecard. It is a receipt machine.

The current implementation is a FastAPI backend with SQLite, LangGraph,
LangChain, OpenAI-compatible model access, and a no-build static web app served
directly by FastAPI.

The first working source adapter targets the Texas Register because it provides a
public, structured rulemaking record. The product and architecture are intended
to be jurisdiction-agnostic: additional adapters can ingest other state,
federal, municipal, or agency rulemaking sources using the same core workflow.

## Why This Matters

Rules are where laws become lived reality. They shape who qualifies for benefits,
how agencies enforce requirements, what businesses must do, how schools,
utilities, health care, energy, housing, licensing, and permitting work day to
day.

But the public record is hard to follow. A proposed rule appears. Comments may be
submitted. Months later, an adopted rule is published. Somewhere inside the
preamble, the agency may summarize what the public said and explain whether it
changed anything. Most people do not have the time, legal training, or
institutional memory to connect those dots.

AI raises the stakes. If government and regulated institutions move at machine
speed while citizens remain stuck reading dense notices one PDF at a time, the
democratic balance gets worse. The public does not just need summaries. It needs
visibility.

1776 turns the record into a usable accountability layer:

- **What changed?**
- **Who is affected?**
- **What did the public say?**
- **How did the agency respond?**
- **Did the final rule reflect that response?**
- **What primary source supports each claim?**

The goal is not to replace the official record or offer legal advice. The goal is
to make civic oversight practical: people can follow the agencies and topics they
care about, see concise source-backed alerts, inspect evidence when needed, and
track whether proposed rules become adopted rules over time.

## Product Promise

1776 is deliberately narrow in the MVP: one jurisdiction, one primary source,
one citizen-facing accountability workflow.

The core experience is:

1. A user describes who they are or what they care about.
2. 1776 ranks official rule actions by personal relevance.
3. Opening a rule automatically generates a plain-English brief.
4. The brief shows the rule status, affected groups, source receipts, and public
   voice state.
5. Proposed rules can become prediction-market style civic forecasts.
6. Every claim points back to an official record.

The flagship accountability panel is **Public voice**. For proposed rules, it
explains that the Comment/Response record is still pending. For adopted rules,
it looks for agency responses and public-heard findings. It avoids unsupported
accusations and distinguishes between evidence found, evidence pending, and
evidence not found.

## Demo Narrative

A strong demo follows one real rule from feed to receipt:

1. Select a Texas Register rule that affects a recognizable persona.
2. Show the plain-language brief: what changed, who may be affected, and where
   the rule is in the process.
3. Show the Public voice panel: whether comments are pending, whether an agency
   response was found, or whether the record does not establish a comment
   response.
4. Open source receipts to show that the app does not ask users to trust the
   model.
5. Use forecast markets to ask citizen-readable questions such as whether the
   proposed rule will be adopted or changed.

This is the accountability analysis a statehouse reporter used to spend days
reconstructing. 1776 makes it available from the public record, with receipts.

## Current Status

Implemented:

- Static customer web app at `http://127.0.0.1:8000`.
- Generic pre-login landing page with pitch narrative and profile onboarding.
- Persona-aware feed ranking for logged-in users.
- AI-powered rule search that accepts natural-language interests such as
  `retiree`, `data centers`, or `crypto`.
- FastAPI API for rules, briefs, source receipts, forecasts, watchlists, alerts,
  and local login sessions.
- SQLite schema for the P1 product surface.
- Real source ingestion from the first supported adapter, the Texas Register,
  with no demo fallback.
- Attribute-aware source parser for agency, topic, rule citation, action type,
  and source URL.
- Compact AI enrichment for feed summaries, why-this-matters copy, and
  public-heard signals.
- LangGraph investigation workflow for rule briefs, Comment/Response extraction,
  public-heard findings, citation enforcement, and forecast generation.
- Automatic AI brief generation when a rule is opened.
- Prediction-market style civic forecasting with user probability submissions
  and aggregate probability updates.
- Watchlists and AI-generated in-app alerts.
- OpenStates key support for future authority-lineage enrichment in the first
  adapter.

Not implemented yet:

- Multi-jurisdiction source adapters beyond the first Texas Register adapter.
- Automated authority-lineage ingestion.
- Forecast resolution jobs and reputation scoring updates after resolution.
- Production authentication, passwordless email, OAuth, or hosted identity.
- Background job queue or scheduler for recurring ingestion.
- Production deployment packaging.

## Product Principles

1776 is intentionally customer-facing. The app should not feel like a dense
regulatory database.

The user experience should:

- Show one primary answer per screen.
- Prefer plain English over legal/regulatory internal terms.
- Put long source text, citations, graph state, and parser details behind
  progressive disclosure.
- Use source receipts as tap-to-open evidence, not inline clutter.
- Label uncertainty plainly and specifically, such as `Comment record pending`,
  `No comment record found`, or `Not established in the current record`.
- Keep prediction-market mechanics play-money/reputation only.

## Architecture

```text
Regulatory source adapter
        |
        v
src/seventeen76/texas_register.py
  - fetch HTML
  - parse official index links and custom attributes
  - extract source snippets
        |
        v
src/seventeen76/ingestion.py
  - hydrate source receipts
  - call AI enrichment in compact batches
  - write issues, rule_actions, sources, rule_stages
        |
        v
SQLite database
        |
        v
FastAPI API in src/seventeen76/api.py
        |
        +--> Static web app in web/
        |
        +--> LangGraph investigation workflow in src/seventeen76/workflow.py
```

AI is used for product-level interpretation:

- Short rule summaries.
- Feed explanation copy.
- Comment/Response extraction.
- Public-heard findings.
- Plain-English customer briefs.
- Forecast question generation.
- Watchlist alert copy.

Deterministic code is used for reliability-critical plumbing:

- Fetching official records.
- Parsing source index metadata.
- SQLite persistence.
- API routing.
- Session lookup.
- Citation/source receipt storage.
- Cite-or-cut enforcement.

## Tech Stack

Backend:

- Python `>=3.12`
- FastAPI
- SQLite
- Pydantic
- BeautifulSoup
- LangGraph
- LangChain
- `langchain-openai`
- OpenAI-compatible chat model provider

Frontend:

- Static HTML/CSS/JavaScript in `web/`
- No npm install and no build step
- Served by FastAPI at `/`

Data:

- Local SQLite database at `data/1776.sqlite3`
- `data/` is ignored by git
- `.env` is ignored by git

## Project Structure

```text
.
├── README.md
├── 1776_PRD.md
├── main.py
├── pyproject.toml
├── .env.example
├── data/
│   └── 1776.sqlite3                 # local runtime DB, gitignored
├── src/seventeen76/
│   ├── ai.py                        # OpenAI/LangChain boundary
│   ├── api.py                       # FastAPI app and REST endpoints
│   ├── cli.py                       # 1776 init / ingest-current
│   ├── config.py                    # .env-backed settings
│   ├── db.py                        # SQLite schema and helpers
│   ├── ingestion.py                 # source ingestion orchestration
│   ├── schemas.py                   # API response/request models
│   ├── texas_register.py            # source fetch and parser utilities
│   └── workflow.py                  # LangGraph investigation runtime
└── web/
    ├── assets/
    │   └── civic-accountability-map.png # generated landing hero asset
    ├── index.html                   # app shell
    ├── styles.css                   # customer-facing UI
    └── app.js                       # API client and interactions
```

There is an older `mobile/` directory from the initial Expo direction. The
active app path is the static web app in `web/`; Expo is not required.

## Environment Variables

Create `.env` from `.env.example` and fill in the keys. Never commit `.env`.

Required:

```bash
OPENAI_API_KEY=...
```

Recommended:

```bash
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-5.5
```

Optional:

```bash
OPENSTATES_API_KEY=...
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=false
```

Notes:

- `OPENAI_API_KEY` is required at app import time. If it is missing, the backend
  fails instead of generating placeholder content.
- `OPENAI_BASE_URL` is optional when using OpenAI directly, but required for an
  OpenAI-compatible provider such as OpenRouter.
- `OPENSTATES_API_KEY` is currently configured for future authority-lineage
  enrichment in the first adapter. It is not required for base source ingestion.
- The current Texas Register source adapter does not require a source API key.
- `EXPO_PUBLIC_API_BASE` may still appear in `.env.example` from the older mobile
  path. The current web app does not use it.

OpenStates API keys can be obtained from:

```text
https://open.pluralpolicy.com/accounts/profile/
```

OpenStates API v3 docs:

```text
https://docs.openstates.org/api-v3/
```

## Local Setup

Use Python 3.12.

```bash
python -m venv .venv312
. .venv312/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env` with real provider keys.

Initialize the database:

```bash
1776 init
```

Start the backend and web app:

```bash
uvicorn seventeen76.api:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Common Commands

Initialize or recreate the schema:

```bash
1776 init
```

Run live source ingestion through the current adapter:

```bash
1776 ingest-current
```

Or through the API:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/texas-register
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

List rules:

```bash
curl http://127.0.0.1:8000/api/rules
```

Run a LangGraph investigation for a rule:

```bash
curl -X POST http://127.0.0.1:8000/api/rules/1/investigate
```

Fetch forecast cards for a rule:

```bash
curl 'http://127.0.0.1:8000/api/forecasts?rule_id=1'
```

## Live Ingestion Details

The ingestion path is intentionally real-source only.

The current source adapter is Texas Register. The core storage, AI enrichment,
briefing, forecasting, watchlist, and alert workflows are generic and can support
additional rulemaking sources once new adapters map those records into the same
rule-action shape.

1. `fetch_html()` loads the current Texas Register index from:

   ```text
   https://www.sos.state.tx.us/texreg/sos/index.html
   ```

2. `extract_issue_links()` reads the official index anchors and Texas Register
   custom attributes such as agency, chapter, register division, and title.

3. `extract_rule_actions()` converts Proposed, Adopted, Emergency, and Withdrawn
   sections into candidate rule actions.

4. Each candidate's detail page is fetched once and cached for the ingestion run.

5. `source_snippet_for()` stores a concise source receipt around the rule
   citation.

6. `CivicAI.enrich_rule_actions()` sends compact metadata batches to the model,
   not full regulatory page text. This keeps AI in the loop for user-facing
   interpretation while reducing data transfer and avoiding large payload issues.

7. Ingestion writes:

   - `issues`
   - `rule_actions`
   - `sources`
   - `rule_stages`

If no rule candidates are found, ingestion returns zero counts. If AI enrichment
fails or returns invalid JSON, the workflow fails visibly and does not invent
substitute demo content.

## LangGraph Investigation Workflow

`InvestigationWorkflow` in `src/seventeen76/workflow.py` builds a required LangGraph
runtime with these nodes:

```text
START
  -> gather_sources
  -> extract_comments
  -> check_people_heard
  -> draft_customer_brief
  -> generate_forecasts
  -> cite_or_cut
  -> END
```

Node responsibilities:

- `gather_sources`: load the rule, source receipts, and stage text.
- `extract_comments`: use AI to extract up to three Comment/Response pairs from
  the stored preamble/source text.
- `check_people_heard`: use AI to classify whether public concerns were changed,
  unchanged, partially addressed, or unclear from the record.
- `draft_customer_brief`: use AI to write a short plain-English brief and
  affected-groups list.
- `generate_forecasts`: use AI to generate 2-3 public-record-resolvable forecast
  questions for proposed rules.
- `cite_or_cut`: remove unsupported brief body content if sources are missing.

Each node stores graph snapshots in `graph_state_snapshots`, and each run is
tracked in `graph_runs`.

## Web App Details

The web app is intentionally simple and customer-facing.

Primary screens and components:

- Pre-login landing page with the public-accountability thesis, visual hero, and
  profile onboarding.
- Personalized feed panel with AI-enriched rule cards.
- Natural-language AI search and action-type filter.
- Rule detail view with status, rule citation, source receipts, and a concise
  "What changed" section.
- Public voice panel with cautious evidence labels.
- Prediction-market style forecast cards with Yes/No prices and probability
  sliders.
- Watchlist entry and in-app alerts.
- Source receipt drawer.
- Settings drawer for operational actions such as refreshing official data.

The frontend uses relative API paths, so it works from the same FastAPI origin:

```text
GET /api/rules
GET /api/rules/{id}
GET /api/rules/{id}/sources
GET /api/forecasts?rule_id={id}
```

There is no Node, npm, bundler, or Expo dependency for the active app.

## API Surface

Public/system endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Serve the web app |
| `GET` | `/api/health` | Health and AI availability |
| `POST` | `/api/ingest/texas-register` | Run live ingestion through the current Texas Register adapter |
| `GET` | `/api/rules` | List rule cards |
| `POST` | `/api/rules/ai-search` | Rank rules from a natural-language person/topic query |
| `GET` | `/api/rules/{id}` | Get rule detail |
| `POST` | `/api/rules/{id}/investigate` | Run LangGraph investigation |
| `GET` | `/api/rules/{id}/brief` | Get generated brief |
| `GET` | `/api/rules/{id}/sources` | Get source receipts |
| `GET` | `/api/forecasts` | List forecast cards |

User endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/login` | Create or reuse a lightweight local user |
| `POST` | `/api/forecasts/{id}/position` | Submit play-money forecast probability |
| `POST` | `/api/watchlists` | Add a watchlist item |
| `GET` | `/api/watchlists` | List watchlist items |
| `GET` | `/api/alerts` | List in-app alerts |

Authentication:

- Login creates a local session token.
- Authenticated API calls pass the token as `X-Session-Token`.
- This is lightweight local-account auth, not production identity.

## SQLite Data Model

Core tables:

- `users`
- `sessions`
- `issues`
- `rule_actions`
- `rule_stages`
- `sources`
- `comment_responses`
- `findings`
- `briefs`
- `authority_links`
- `forecast_questions`
- `forecast_positions`
- `forecast_resolutions`
- `forecaster_scores`
- `watchlists`
- `alerts`
- `graph_runs`
- `graph_state_snapshots`

SQLite is used for more than raw ingestion storage:

- Local user/session state.
- Rule feed data.
- Source receipts.
- AI brief cache.
- Forecast questions and user positions.
- Watchlists and alerts.
- LangGraph run audit trail.
- Future authority lineage.

## AI Failure Policy

1776 does not silently produce demo or placeholder conclusions.

Failures that should be visible:

- Missing `OPENAI_API_KEY`.
- Missing LangGraph dependency.
- Model provider request failure.
- Invalid JSON returned by the model for strict JSON workflows.
- Failed source ingestion.
- Missing evidence for a claim.

Customer-facing fallback language is only used for uncertainty grounded in the
record, such as:

```text
Unclear from record
Not established in the current record
Not yet available
```

That is different from generating substitute content.

## Forecasting Model

Forecasting is play-money/reputation only.

Generated forecast cards include:

- A resolvable public-record question.
- Resolution criteria.
- Source of truth.
- Aggregate probability.
- Optional user probability after login.

Current behavior:

- Proposed rules can generate forecast cards during investigation.
- User submissions update aggregate probability.
- Forecast resolution and reputation scoring tables exist, but resolution jobs
  are not implemented yet.

## Validation Notes

Useful smoke checks:

```bash
python -m compileall main.py src
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/rules
curl 'http://127.0.0.1:8000/api/forecasts?rule_id=1'
```

Recent local validation showed:

- Real source ingestion through the Texas Register adapter inserted 57 rule
  actions.
- 57 source receipts were stored.
- A LangGraph investigation generated a brief, a public-heard finding, and three
  forecast cards for rule 1.
- The browser UI rendered 57 feed cards with no console errors.

These counts depend on the current source record and will change as the official
source changes.

## Operational Notes

- Restart FastAPI after changing `.env`; settings are loaded at import time.
- Keep `.env` and `data/` out of git.
- `OPENSTATES_API_KEY` should stay server-side only.
- Avoid sending full regulatory page text to the model unless there is a clear
  reason. The current ingestion flow intentionally sends compact metadata for
  feed enrichment and stores source receipts locally.
- If the model/provider blocks a request, fix the payload or provider
  configuration; do not add demo fallbacks.

## Known Gaps and Next Improvements

Good next implementation targets:

- Add a source-adapter interface so federal, state, municipal, and agency
  rulemaking sources can be plugged in cleanly.
- Use authority data providers to enrich `authority_links` with bill, statute,
  session, or action data where a source cites legislation.
- Add a background scheduler for recurring source ingestion.
- Add duplicate detection for repeated ingestion runs.
- Add forecast resolution workflow against official source records.
- Add production-grade auth if this moves beyond local/demo usage.
- Add deployment configuration.
- Remove or archive the legacy `mobile/` directory once no longer needed.
