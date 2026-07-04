from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import AIServiceError, CivicAI
from .config import settings
from .db import Database, insert, now_iso
from .ingestion import ingest_current_texas_register
from .schemas import (
    AlertItem,
    AISearchRequest,
    BriefResponse,
    ForecastCard,
    ForecastPositionRequest,
    ForecastPositionResponse,
    InvestigationResponse,
    LoginRequest,
    RuleCard,
    RuleDetail,
    SessionResponse,
    SourceRef,
    WatchlistItem,
    WatchlistRequest,
)
from .workflow import InvestigationWorkflow, row_to_dict


db = Database()
ai = CivicAI()
workflow = InvestigationWorkflow(db=db, ai=ai)

app = FastAPI(title="1776 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.web_dir.exists():
    app.mount("/static", StaticFiles(directory=settings.web_dir), name="static")


@app.on_event("startup")
def startup() -> None:
    db.init_schema()


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    index_path = Path(settings.web_dir) / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Web app not found")
    return FileResponse(index_path)


def current_user(x_session_token: str | None = Header(default=None)) -> dict[str, Any] | None:
    row = db.user_for_token(x_session_token)
    return row_to_dict(row)


def require_user(user: dict[str, Any] | None = Depends(current_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "ai_live": ai.is_live, "app": settings.app_name}


@app.post("/api/ingest/texas-register")
def ingest_texas_register() -> dict[str, int]:
    return ingest_current_texas_register(db, ai)


@app.post("/api/auth/login", response_model=SessionResponse)
def login(payload: LoginRequest) -> dict[str, Any]:
    return db.create_or_get_user(payload.email, payload.name, payload.persona, payload.interests)


@app.get("/api/rules", response_model=list[RuleCard])
def list_rules(
    action_type: str | None = None,
    q: str | None = None,
    user: dict[str, Any] | None = Depends(current_user),
) -> list[RuleCard]:
    clauses: list[str] = []
    params: list[Any] = []
    if action_type:
        clauses.append("action_type = ?")
        params.append(action_type)
    if q:
        clauses.append("(agency LIKE ? OR title LIKE ? OR tac_citation LIKE ? OR summary LIKE ? OR why_matters LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term, term, term, term])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT rule_actions.*,
                   (SELECT COUNT(*) FROM forecast_questions WHERE forecast_questions.rule_id = rule_actions.id) AS forecast_count
            FROM rule_actions
            {where}
            ORDER BY id DESC
            """,
            params,
        ).fetchall()
        if user and not q and user_profile_text(user):
            rows = sorted(rows, key=lambda row: rule_sort_key(row_to_dict(row), user))
        else:
            rows = sorted(rows, key=lambda row: (action_order(row["action_type"]), -row["id"]))
        watched_ids = set()
        if user:
            watches = conn.execute("SELECT kind, value FROM watchlists WHERE user_id = ?", (user["id"],)).fetchall()
            for row in rows:
                if any(watch_matches(row_to_dict(row), w["value"]) for w in watches):
                    watched_ids.add(row["id"])
        return [RuleCard(**row_to_card(row, watched=row["id"] in watched_ids)) for row in rows]


@app.post("/api/rules/ai-search", response_model=list[RuleCard])
def ai_search_rules(
    payload: AISearchRequest,
    user: dict[str, Any] | None = Depends(current_user),
) -> list[RuleCard]:
    search_text = payload.query.strip()
    if not search_text:
        return list_rules(action_type=payload.action_type, q=None, user=user)
    clauses: list[str] = []
    params: list[Any] = []
    if payload.action_type:
        clauses.append("action_type = ?")
        params.append(payload.action_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT rule_actions.*,
                   (SELECT COUNT(*) FROM forecast_questions WHERE forecast_questions.rule_id = rule_actions.id) AS forecast_count
            FROM rule_actions
            {where}
            ORDER BY id DESC
            """,
            params,
        ).fetchall()
        watches = conn.execute("SELECT kind, value FROM watchlists WHERE user_id = ?", (user["id"],)).fetchall() if user else []
    cards = []
    for row in rows:
        row_dict = row_to_dict(row)
        watched = any(watch_matches(row_dict, watch["value"]) for watch in watches)
        cards.append(row_to_card(row, watched=watched))
    profile_text = user_profile_text(user)
    ranked_candidates = sorted(
        cards,
        key=lambda card: (
            -relevance_score(card, search_text),
            -relevance_score(card, profile_text),
            action_order(card["action_type"]),
            -card["id"],
        ),
    )
    try:
        matches = ai.rank_rule_matches(search_text, profile_text, ranked_candidates)
    except AIServiceError:
        matches = [
            {"rule_id": card["id"], "score": relevance_score(card, search_text), "reason": local_match_reason(card, search_text)}
            for card in ranked_candidates
            if relevance_score(card, search_text) > 0
        ][:12]
    cards_by_id = {card["id"]: card for card in cards}
    ranked_cards: list[RuleCard] = []
    for match in matches:
        card = cards_by_id.get(match["rule_id"])
        if not card:
            continue
        ranked_cards.append(RuleCard(**{**card, "match_reason": match["reason"]}))
    return ranked_cards


@app.get("/api/rules/{rule_id}", response_model=RuleDetail)
def get_rule(rule_id: int, user: dict[str, Any] | None = Depends(current_user)) -> RuleDetail:
    with db.connect() as conn:
        rule = conn.execute(
            """
            SELECT rule_actions.*,
                   (SELECT COUNT(*) FROM forecast_questions WHERE forecast_questions.rule_id = rule_actions.id) AS forecast_count
            FROM rule_actions WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        brief = conn.execute("SELECT * FROM briefs WHERE rule_id = ?", (rule_id,)).fetchone()
        comments = conn.execute("SELECT * FROM comment_responses WHERE rule_id = ? LIMIT 3", (rule_id,)).fetchall()
        findings = conn.execute("SELECT * FROM findings WHERE rule_id = ?", (rule_id,)).fetchall()
        links = conn.execute("SELECT * FROM authority_links WHERE rule_id = ?", (rule_id,)).fetchall()
        watched = False
        if user:
            watches = conn.execute("SELECT value FROM watchlists WHERE user_id = ?", (user["id"],)).fetchall()
            watched = any(watch_matches(row_to_dict(rule), watch["value"]) for watch in watches)
        payload = row_to_card(rule, watched=watched)
        payload["affected_groups"] = json.loads(brief["affected_groups"]) if brief else []
        payload["top_concerns"] = [row_to_dict(r) for r in comments]
        payload["findings"] = [row_to_dict(r) for r in findings]
        payload["authority_links"] = [row_to_dict(r) for r in links]
        return RuleDetail(**payload)


@app.post("/api/rules/{rule_id}/investigate", response_model=InvestigationResponse)
def investigate_rule(rule_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM rule_actions WHERE id = ?", (rule_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Rule not found")
    result = workflow.run(rule_id)
    brief = get_brief(rule_id)
    return {"rule_id": rule_id, "graph_run_id": result["graph_run_id"], "status": "completed", "brief": brief.model_dump()}


@app.get("/api/rules/{rule_id}/brief", response_model=BriefResponse)
def get_brief(rule_id: int) -> BriefResponse:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM briefs WHERE rule_id = ?", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Brief not found")
        return BriefResponse(
            rule_id=rule_id,
            plain_summary=row["plain_summary"],
            affected_groups=json.loads(row["affected_groups"]),
            status_text=row["status_text"],
            public_heard_signal=row["public_heard_signal"],
            body=row["body"].replace("Tribune", "1776"),
            source_ids=json.loads(row["source_ids"]),
        )


@app.get("/api/rules/{rule_id}/sources", response_model=list[SourceRef])
def get_sources(rule_id: int) -> list[SourceRef]:
    with db.connect() as conn:
        rows = conn.execute("SELECT id, label, url, snippet FROM sources WHERE rule_id = ?", (rule_id,)).fetchall()
        return [SourceRef(**row_to_dict(row)) for row in rows]


@app.get("/api/forecasts", response_model=list[ForecastCard])
def get_forecasts(
    rule_id: int | None = Query(default=None),
    user: dict[str, Any] | None = Depends(current_user),
) -> list[ForecastCard]:
    params: list[Any] = []
    where = ""
    if rule_id is not None:
        where = "WHERE forecast_questions.rule_id = ?"
        params.append(rule_id)
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT forecast_questions.*,
                   rule_actions.title AS rule_title,
                   rule_actions.agency AS rule_agency
            FROM forecast_questions
            JOIN rule_actions ON rule_actions.id = forecast_questions.rule_id
            {where}
            ORDER BY forecast_questions.id
            """,
            params,
        ).fetchall()
        positions = {}
        if user:
            for row in conn.execute("SELECT forecast_id, probability FROM forecast_positions WHERE user_id = ?", (user["id"],)):
                positions[row["forecast_id"]] = row["probability"]
        return [
            ForecastCard(
                **{
                    **row_to_dict(row),
                    "display_question": friendly_forecast_question(row_to_dict(row)),
                    "user_probability": positions.get(row["id"]),
                }
            )
            for row in rows
        ]


@app.post("/api/forecasts/{forecast_id}/position", response_model=ForecastPositionResponse)
def submit_forecast(
    forecast_id: int,
    payload: ForecastPositionRequest,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    with db.connect() as conn:
        forecast = conn.execute("SELECT * FROM forecast_questions WHERE id = ?", (forecast_id,)).fetchone()
        if not forecast:
            raise HTTPException(status_code=404, detail="Forecast not found")
        if forecast["status"] != "open":
            raise HTTPException(status_code=400, detail="Forecast is closed")
        insert(
            conn,
            "forecast_positions",
            {
                "forecast_id": forecast_id,
                "user_id": user["id"],
                "probability": payload.probability,
                "rationale": payload.rationale,
                "created_at": now_iso(),
            },
        )
        avg = conn.execute("SELECT AVG(probability) AS p FROM forecast_positions WHERE forecast_id = ?", (forecast_id,)).fetchone()["p"]
        aggregate = float(avg if avg is not None else payload.probability)
        conn.execute("UPDATE forecast_questions SET aggregate_probability = ? WHERE id = ?", (aggregate, forecast_id))
        score = conn.execute("SELECT * FROM forecaster_scores WHERE user_id = ?", (user["id"],)).fetchone()
        reputation = score["reputation"] if score else 50.0
        return {
            "forecast_id": forecast_id,
            "user_id": user["id"],
            "probability": payload.probability,
            "aggregate_probability": aggregate,
            "reputation": reputation,
        }


@app.post("/api/watchlists", response_model=WatchlistItem)
def create_watchlist(payload: WatchlistRequest, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db.connect() as conn:
        watch_id = insert(
            conn,
            "watchlists",
            {"user_id": user["id"], "kind": payload.kind, "value": payload.value, "created_at": now_iso()},
        )
        all_rules = conn.execute("SELECT * FROM rule_actions ORDER BY id DESC").fetchall()
        matches = [rule for rule in all_rules if watch_matches(row_to_dict(rule), payload.value)][:3]
        for rule in matches:
            copy = ai.alert_copy(row_to_dict(rule), payload.value)
            insert(
                conn,
                "alerts",
                {
                    "user_id": user["id"],
                    "title": copy["title"],
                    "body": copy["body"],
                    "source_url": rule["source_url"],
                    "read": 0,
                    "created_at": now_iso(),
                },
            )
        return {"id": watch_id, "kind": payload.kind, "value": payload.value}


@app.get("/api/watchlists", response_model=list[WatchlistItem])
def list_watchlists(user: dict[str, Any] = Depends(require_user)) -> list[WatchlistItem]:
    with db.connect() as conn:
        rows = conn.execute("SELECT id, kind, value FROM watchlists WHERE user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
        return [WatchlistItem(**row_to_dict(row)) for row in rows]


@app.get("/api/alerts", response_model=list[AlertItem])
def list_alerts(user: dict[str, Any] = Depends(require_user)) -> list[AlertItem]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM alerts WHERE user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
        return [AlertItem(**{**row_to_dict(row), "read": bool(row["read"])}) for row in rows]


def friendly_forecast_question(forecast: dict[str, Any]) -> str:
    question = str(forecast.get("question", "")).lower()
    topic = friendly_rule_topic(str(forecast.get("rule_title", "") or "this rule"))
    if "public comment" in question or "comments" in question:
        return "Will public comments change this rule?"
    if "differ substantively" in question or "substantive changes" in question or "with changes" in question:
        return "Will the agency change the final rule?"
    if "effective date" in question or "take effect" in question:
        return "Will the final rule take effect quickly?"
    if "withdraw" in question:
        return "Will this proposal be withdrawn?"
    if "adopt" in question or "adopted-rules notice" in question:
        return f"Will the {topic} rule be adopted?"
    return f"Will the {topic} rule happen?"


def friendly_rule_topic(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    cleaned = re.sub(r"^(substantive rules applicable to|rules concerning)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.split(r"[:;,(]", cleaned)[0].strip()
    if len(cleaned) > 46 and " for " in cleaned.lower():
        cleaned = re.split(r"\s+for\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if len(cleaned) > 46:
        cleaned = cleaned[:43].rstrip() + "..."
    return cleaned or "proposed"


def rule_sort_key(rule: dict[str, Any], user: dict[str, Any] | None) -> tuple[float, int, int]:
    score = relevance_score(rule, user_profile_text(user))
    return (-score, action_order(rule.get("action_type", "")), -int(rule.get("id", 0)))


def action_order(action_type: str) -> int:
    return {"Proposed": 0, "Adopted": 1, "Emergency": 2, "Withdrawn": 3}.get(action_type, 4)


def user_profile_text(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    return f"{user.get('persona', '')} {user.get('interests', '')}".strip()


def relevance_score(rule: dict[str, Any], text: str) -> float:
    terms = expanded_terms(text)
    if not terms:
        return 0.0
    fields = {
        "title": str(rule.get("title", "")).lower(),
        "summary": str(rule.get("summary", "")).lower(),
        "why_matters": str(rule.get("why_matters", "")).lower(),
        "agency": str(rule.get("agency", "")).lower(),
        "citation": str(rule.get("tac_citation", "")).lower(),
    }
    weights = {"title": 5.0, "summary": 4.0, "why_matters": 4.0, "agency": 3.0, "citation": 2.0}
    score = 0.0
    for term in terms:
        for field, haystack in fields.items():
            if term in haystack:
                score += weights[field] * (1.6 if " " in term else 1.0)
    return score


def local_match_reason(rule: dict[str, Any], text: str) -> str:
    terms = expanded_terms(text)
    haystack = f"{rule.get('title', '')} {rule.get('summary', '')} {rule.get('why_matters', '')} {rule.get('agency', '')}".lower()
    matched = [term for term in terms if term in haystack][:3]
    if matched:
        return f"Matched official rule text on {', '.join(matched)}."
    return "Matched your profile to this official rule action."


def expanded_terms(text: str) -> list[str]:
    lowered = text.lower()
    tokens = [token for token in re.findall(r"[a-z0-9]+", lowered) if len(token) > 2 and token not in STOP_TERMS]
    terms = set(tokens)
    for trigger, expansions in SEARCH_EXPANSIONS.items():
        if trigger in lowered:
            terms.update(expansions)
    return sorted(terms, key=len, reverse=True)


STOP_TERMS = {
    "about",
    "able",
    "all",
    "and",
    "any",
    "are",
    "for",
    "from",
    "how",
    "i'm",
    "interested",
    "into",
    "rule",
    "rules",
    "the",
    "this",
    "that",
    "want",
    "with",
}


SEARCH_EXPANSIONS = {
    "retiree": ["elderly", "aging", "senior", "retirement", "medicaid", "disabilities", "health", "benefits"],
    "retired": ["elderly", "aging", "senior", "retirement", "medicaid", "disabilities", "health", "benefits"],
    "senior": ["elderly", "aging", "medicaid", "disabilities", "health", "benefits"],
    "data center": ["electric", "utility", "utilities", "power", "energy", "water", "environmental", "construction", "tax"],
    "datacenter": ["electric", "utility", "utilities", "power", "energy", "water", "environmental", "construction", "tax"],
    "crypto": ["consumer credit", "savings", "bank", "financial", "money", "investment", "electric", "utility", "power"],
    "cryptocurrency": ["consumer credit", "savings", "bank", "financial", "money", "investment", "electric", "utility", "power"],
    "bitcoin": ["consumer credit", "savings", "bank", "financial", "money", "investment", "electric", "utility", "power"],
}


def row_to_card(row: Any, watched: bool = False) -> dict[str, Any]:
    return {
        "id": row["id"],
        "agency": row["agency"],
        "title": row["title"],
        "tac_citation": row["tac_citation"],
        "action_type": row["action_type"],
        "status": row["status"],
        "summary": row["summary"],
        "why_matters": row["why_matters"],
        "heard_signal": row["heard_signal"],
        "source_url": row["source_url"],
        "forecast_count": row["forecast_count"] if "forecast_count" in row.keys() else 0,
        "watched": watched,
    }


def watch_matches(rule: dict[str, Any], value: str) -> bool:
    haystack = f"{rule.get('agency', '')} {rule.get('title', '')} {rule.get('tac_citation', '')}".lower()
    needle = value.lower().strip()
    if needle in haystack:
        return True
    aliases = {
        "tceq": "texas commission on environmental quality",
        "hhsc": "health and human services",
        "occc": "office of consumer credit commissioner",
        "rrc": "railroad commission",
        "puc": "public utility commission",
    }
    return aliases.get(needle, "") in haystack
