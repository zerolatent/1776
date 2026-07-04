from __future__ import annotations

import json
import sqlite3
from typing import Any, TypedDict

from .ai import AIServiceError, CivicAI
from .db import Database, insert, now_iso


class InvestigationState(TypedDict, total=False):
    rule_id: int
    graph_run_id: int
    rule: dict[str, Any]
    sources: list[dict[str, Any]]
    stages: list[dict[str, Any]]
    comments: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    brief: dict[str, Any]
    forecasts: list[dict[str, Any]]
    missing_evidence: list[str]


class InvestigationWorkflow:
    def __init__(self, db: Database, ai: CivicAI | None = None) -> None:
        self.db = db
        self.ai = ai or CivicAI()
        self.graph = self._build_graph()

    def run(self, rule_id: int) -> dict[str, Any]:
        with self.db.connect() as conn:
            graph_run_id = insert(
                conn,
                "graph_runs",
                {"rule_id": rule_id, "workflow": "investigate_rule", "status": "running", "created_at": now_iso()},
            )
        state: InvestigationState = {"rule_id": rule_id, "graph_run_id": graph_run_id, "missing_evidence": []}
        result = self.graph.invoke(state)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE graph_runs SET status = ?, completed_at = ? WHERE id = ?",
                ("completed", now_iso(), graph_run_id),
            )
        return result

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph

            graph = StateGraph(InvestigationState)
            graph.add_node("gather_sources", self.gather_sources)
            graph.add_node("extract_comments", self.extract_comments)
            graph.add_node("check_people_heard", self.check_people_heard)
            graph.add_node("draft_customer_brief", self.draft_customer_brief)
            graph.add_node("generate_forecasts", self.generate_forecasts)
            graph.add_node("cite_or_cut", self.cite_or_cut)
            graph.add_edge(START, "gather_sources")
            graph.add_edge("gather_sources", "extract_comments")
            graph.add_edge("extract_comments", "check_people_heard")
            graph.add_edge("check_people_heard", "draft_customer_brief")
            graph.add_edge("draft_customer_brief", "generate_forecasts")
            graph.add_edge("generate_forecasts", "cite_or_cut")
            graph.add_edge("cite_or_cut", END)
            return graph.compile()
        except Exception as exc:
            raise RuntimeError("LangGraph is required for 1776 investigations.") from exc

    def snapshot(self, state: InvestigationState, node: str) -> None:
        with self.db.connect() as conn:
            insert(
                conn,
                "graph_state_snapshots",
                {
                    "graph_run_id": state["graph_run_id"],
                    "node": node,
                    "state_json": json.dumps(state, default=str),
                    "created_at": now_iso(),
                },
            )

    def gather_sources(self, state: InvestigationState) -> InvestigationState:
        with self.db.connect() as conn:
            rule = row_to_dict(conn.execute("SELECT * FROM rule_actions WHERE id = ?", (state["rule_id"],)).fetchone())
            sources = [row_to_dict(r) for r in conn.execute("SELECT * FROM sources WHERE rule_id = ?", (state["rule_id"],))]
            stages = [row_to_dict(r) for r in conn.execute("SELECT * FROM rule_stages WHERE rule_id = ?", (state["rule_id"],))]
        state["rule"] = rule
        state["sources"] = sources
        state["stages"] = stages
        if not sources:
            state.setdefault("missing_evidence", []).append("No primary source is stored for this rule.")
        self.snapshot(state, "gather_sources")
        return state

    def extract_comments(self, state: InvestigationState) -> InvestigationState:
        preamble = "\n".join(stage.get("preamble", "") for stage in state.get("stages", []))
        with self.db.connect() as conn:
            existing = [row_to_dict(r) for r in conn.execute("SELECT * FROM comment_responses WHERE rule_id = ?", (state["rule_id"],))]
            source_id = state.get("sources", [{}])[0].get("id") if state.get("sources") else None
            if existing:
                comments = existing
            else:
                try:
                    comments = self.ai.extract_comment_pairs(preamble)
                except AIServiceError:
                    comments = []
                for item in comments:
                    insert(
                        conn,
                        "comment_responses",
                        {
                            "rule_id": state["rule_id"],
                            "concern": item["concern"],
                            "agency_response": item["agency_response"],
                            "disposition": item["disposition"],
                            "evidence_source_id": source_id,
                        },
                    )
            state["comments"] = comments
        self.snapshot(state, "extract_comments")
        return state

    def check_people_heard(self, state: InvestigationState) -> InvestigationState:
        adopted_text = "\n".join(stage.get("text", "") for stage in state.get("stages", []) if stage.get("stage") == "adopted")
        try:
            findings = self.ai.public_heard_findings(state["rule"], state.get("comments", []), adopted_text)
        except AIServiceError:
            findings = []
        source_id = state.get("sources", [{}])[0].get("id") if state.get("sources") else None
        with self.db.connect() as conn:
            conn.execute("DELETE FROM findings WHERE rule_id = ?", (state["rule_id"],))
            for item in findings:
                insert(
                    conn,
                    "findings",
                    {
                        "rule_id": state["rule_id"],
                        "label": item["label"],
                        "summary": item["summary"],
                        "source_id": source_id,
                    },
                )
            if findings:
                conn.execute(
                    "UPDATE rule_actions SET heard_signal = ? WHERE id = ?",
                    (findings[0]["label"], state["rule_id"]),
                )
        state["findings"] = findings
        self.snapshot(state, "check_people_heard")
        return state

    def draft_customer_brief(self, state: InvestigationState) -> InvestigationState:
        source_text = "\n".join(src.get("snippet", "") for src in state.get("sources", []))
        stage_text = "\n".join(stage.get("preamble", "") + "\n" + stage.get("text", "") for stage in state.get("stages", []))
        try:
            summary = self.ai.customer_summary(state["rule"], source_text + "\n" + stage_text)
        except AIServiceError:
            summary = fallback_customer_summary(state["rule"])
        source_ids = [src["id"] for src in state.get("sources", [])]
        body = build_customer_body(state, summary)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO briefs (rule_id, plain_summary, affected_groups, status_text, public_heard_signal, body, source_ids, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    plain_summary = excluded.plain_summary,
                    affected_groups = excluded.affected_groups,
                    status_text = excluded.status_text,
                    public_heard_signal = excluded.public_heard_signal,
                    body = excluded.body,
                    source_ids = excluded.source_ids,
                    updated_at = excluded.updated_at
                """,
                (
                    state["rule_id"],
                    summary["plain_summary"],
                    json.dumps(summary["affected_groups"]),
                    summary["status_text"],
                    state.get("findings", [{"label": state["rule"].get("heard_signal", "Unclear from record")}])[0]["label"],
                    body,
                    json.dumps(source_ids),
                    now_iso(),
                ),
            )
        state["brief"] = {
            "plain_summary": summary["plain_summary"],
            "affected_groups": summary["affected_groups"],
            "status_text": summary["status_text"],
            "body": body,
            "source_ids": source_ids,
        }
        self.snapshot(state, "draft_customer_brief")
        return state

    def generate_forecasts(self, state: InvestigationState) -> InvestigationState:
        try:
            questions = self.ai.forecast_questions(state["rule"])
        except AIServiceError:
            questions = fallback_forecast_questions(state["rule"])
        if not questions:
            state["forecasts"] = []
            self.snapshot(state, "generate_forecasts")
            return state
        with self.db.connect() as conn:
            existing = conn.execute("SELECT COUNT(*) AS c FROM forecast_questions WHERE rule_id = ?", (state["rule_id"],)).fetchone()["c"]
            if existing == 0:
                for item in questions[:3]:
                    insert(
                        conn,
                        "forecast_questions",
                        {
                            "rule_id": state["rule_id"],
                            "question": item["question"],
                            "resolution_criteria": item["resolution_criteria"],
                            "source_of_truth": item["source_of_truth"],
                            "status": "open",
                            "aggregate_probability": item["aggregate_probability"],
                        },
                    )
            state["forecasts"] = [
                row_to_dict(r) for r in conn.execute("SELECT * FROM forecast_questions WHERE rule_id = ?", (state["rule_id"],))
            ]
        self.snapshot(state, "generate_forecasts")
        return state

    def cite_or_cut(self, state: InvestigationState) -> InvestigationState:
        if not state.get("sources"):
            state["brief"]["body"] = "Not established in the record."
        self.snapshot(state, "cite_or_cut")
        return state


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def build_customer_body(state: InvestigationState, summary: dict[str, Any]) -> str:
    findings = state.get("findings", [])
    signal = findings[0]["label"] if findings else state.get("rule", {}).get("heard_signal", "Unclear from record")
    comments = state.get("comments", [])
    if comments:
        concern = comments[0].get("concern", "A public concern was recorded.")
        return f"{summary['plain_summary']} Public voice: agency response found. Top concern: {concern}"
    if state.get("rule", {}).get("action_type") == "Proposed":
        return (
            f"{summary['plain_summary']} Public voice: comment record pending. "
            "This rule is still proposed, so agencies usually summarize public comments later if they adopt or withdraw it."
        )
    if signal in {"Changed", "Unchanged", "Partially addressed"}:
        return f"{summary['plain_summary']} Public voice: {signal}."
    return (
        f"{summary['plain_summary']} Public voice: no comment record found. "
        "1776 did not find a Comment/Response section in the official notice for this rule."
    )


def fallback_customer_summary(rule: dict[str, Any]) -> dict[str, Any]:
    summary = str(rule.get("summary") or "").strip()
    if not summary:
        summary = (
            f"{rule.get('agency', 'The agency')} published a {rule.get('action_type', 'rule')} action "
            f"for {rule.get('title', 'this rule')}."
        )
    return {
        "plain_summary": summary[:700],
        "affected_groups": fallback_affected_groups(rule),
        "status_text": f"Official record status: {rule.get('status', 'Unclear from record')}.",
    }


def fallback_affected_groups(rule: dict[str, Any]) -> list[str]:
    text = f"{rule.get('agency', '')} {rule.get('title', '')} {rule.get('summary', '')} {rule.get('why_matters', '')}".lower()
    groups: list[str] = []
    if any(term in text for term in ("elderly", "senior", "medicaid", "disabilities")):
        groups.extend(["Medicaid applicants", "Elderly people and people with disabilities"])
    if any(term in text for term in ("children", "youth", "families")):
        groups.append("Families, children, and youth")
    if any(term in text for term in ("electric", "utility", "power")):
        groups.extend(["Electric service providers", "Utility customers"])
    if any(term in text for term in ("savings", "mortgage", "credit", "bank", "loan", "investment")):
        groups.extend(["Regulated financial institutions", "Consumers using financial services"])
    if groups:
        return list(dict.fromkeys(groups))[:4]
    agency = rule.get("agency", "the agency")
    return [f"People or organizations regulated by {agency}"]


def fallback_forecast_questions(rule: dict[str, Any]) -> list[dict[str, Any]]:
    if str(rule.get("action_type", "")).lower() != "proposed":
        return []
    citation = rule.get("tac_citation", "this citation")
    return [
        {
            "question": "Will this proposed rule be adopted?",
            "resolution_criteria": (
                f"Resolves Yes if a later Texas Register action adopts the proposed rule for {citation}. "
                "Resolves No if the proposal is withdrawn or no adoption appears within 180 days."
            ),
            "source_of_truth": "Texas Register rule action records",
            "aggregate_probability": 0.55,
        }
    ]
