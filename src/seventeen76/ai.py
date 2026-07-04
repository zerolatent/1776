from __future__ import annotations

import json
import re
from typing import Any

from .config import settings


class AIConfigurationError(RuntimeError):
    pass


class AIServiceError(RuntimeError):
    pass


class CivicAI:
    """AI boundary for customer-facing interpretation."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise AIConfigurationError("OPENAI_API_KEY is required for 1776 AI workflows.")
        try:
            from langchain_openai import ChatOpenAI
        except Exception as exc:
            raise AIConfigurationError("langchain-openai must be installed for 1776 AI workflows.") from exc
        model_config: dict[str, Any] = {
            "model": settings.openai_model,
            "api_key": settings.openai_api_key,
            "temperature": 0.2,
            "default_headers": {
                "Authorization": f"Bearer {settings.openai_api_key}",
                "X-Title": "1776",
            },
        }
        if settings.openai_base_url:
            model_config["base_url"] = settings.openai_base_url
        self._model = ChatOpenAI(**model_config)

    @property
    def is_live(self) -> bool:
        return True

    def complete(self, system: str, user: str) -> str:
        try:
            response = self._model.invoke(
                [
                    ("system", system),
                    ("user", user),
                ]
            )
            return getattr(response, "content", str(response))
        except Exception as exc:
            raise AIServiceError("OpenAI request failed; 1776 will not generate alternate content.") from exc

    def customer_summary(self, rule: dict[str, Any], source_text: str) -> dict[str, Any]:
        payload = self.complete_json(
            "Return strict JSON with keys plain_summary, affected_groups, and status_text. "
            "Use plain English, keep plain_summary under 80 words, and do not invent unsupported facts.",
            f"Rule: {json.dumps(rule)}\nSource:\n{source_text[:7000]}",
        )
        return {
            "plain_summary": str(payload["plain_summary"])[:700],
            "affected_groups": ensure_string_list(payload["affected_groups"]),
            "status_text": str(payload["status_text"])[:200],
        }

    def why_matters(self, rule: dict[str, Any], source_text: str) -> str:
        text = self.complete(
            "Write one sentence explaining why this rule may matter to a citizen. Do not speculate.",
            f"Rule: {rule}\nSource:\n{source_text[:3000]}",
        )
        return text.strip().split("\n")[0][:280]

    def rank_rule_matches(self, query: str, persona: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact_candidates = [
            {
                "id": item["id"],
                "agency": item["agency"],
                "title": item["title"],
                "tac_citation": item["tac_citation"],
                "action_type": item["action_type"],
                "summary": item["summary"],
                "why_matters": item["why_matters"],
            }
            for item in candidates[:80]
        ]
        payload = self.complete_json(
            "Rank official rule actions for a citizen-facing search. The query may describe a person, industry, "
            "life situation, or topic. Return strict JSON with key matches. matches must be an array of up to 12 "
            "objects with keys rule_id, score, and reason. Only use rule_id values from the candidate list. "
            "score must be 0 to 1. Do not invent rules or cite facts outside the candidate text.",
            json.dumps({"query": query, "persona": persona, "candidates": compact_candidates}),
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
            raise AIServiceError("AI search did not return ranked matches.")
        candidate_ids = {int(item["id"]) for item in compact_candidates}
        matches: list[dict[str, Any]] = []
        for item in payload["matches"]:
            if not isinstance(item, dict) or "rule_id" not in item:
                continue
            try:
                rule_id = int(item["rule_id"])
                score = clamp_probability(float(item.get("score", 0.0)))
            except (TypeError, ValueError):
                continue
            if rule_id not in candidate_ids:
                continue
            matches.append(
                {
                    "rule_id": rule_id,
                    "score": score,
                    "reason": str(item.get("reason", ""))[:220],
                }
            )
        return matches

    def discover_rules(self, issue_url: str, issue_pages: list[dict[str, str]]) -> list[dict[str, str]]:
        payload = self.complete_json(
            "You are powering a customer-facing civic accountability app. Return strict JSON as an array of rule action "
            "objects with keys agency, title, tac_citation, action_type, status, summary, why_matters, heard_signal, "
            "source_url, and source_snippet. Use Proposed, Adopted, Emergency, or Withdrawn for action_type. "
            "Extract only actions supported by the provided Texas Register page text. Keep summaries short, customer-facing, "
            "and source-backed. Prefer concrete TAC citations. For proposed rules, heard_signal should be Not yet available.",
            json.dumps({"issue_url": issue_url, "pages": issue_pages[:8]}),
        )
        if not isinstance(payload, list):
            raise AIServiceError("Rule discovery did not return a JSON array.")
        rules: list[dict[str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            required = {
                "agency",
                "title",
                "tac_citation",
                "action_type",
                "status",
                "summary",
                "why_matters",
                "heard_signal",
                "source_url",
                "source_snippet",
            }
            if required <= set(item):
                rules.append({key: str(item[key]) for key in required})
        return rules

    def enrich_rule_actions(self, issue_url: str, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        """Turn source-derived rule candidates into customer-facing feed copy."""
        compact_candidates = [
            {
                "source_key": item["source_key"],
                "agency": item["agency"],
                "title": item["title"],
                "tac_citation": item["tac_citation"],
                "action_type": item["action_type"],
            }
            for item in candidates
        ]
        payload = self.complete_json(
            "You are powering a simple customer-facing civic accountability feed. "
            "Return strict JSON with key actions. actions must be an array with one item for each input candidate, "
            "in the same order. Each item must include source_key, status, summary, why_matters, and heard_signal. "
            "Use only the provided official Texas Register index metadata. Keep summary under 35 words and why_matters "
            "under 22 words. For proposed rules use heard_signal 'Not yet available'. If the metadata is not enough, "
            "say 'Unclear from record' instead of guessing.",
            json.dumps({"issue_url": issue_url, "candidates": compact_candidates}),
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("actions"), list):
            raise AIServiceError("Rule enrichment did not return an actions array.")
        enriched_by_key: dict[str, dict[str, str]] = {}
        for item in payload["actions"]:
            if not isinstance(item, dict):
                continue
            required = {"source_key", "status", "summary", "why_matters", "heard_signal"}
            if required <= set(item):
                enriched_by_key[str(item["source_key"])] = {
                    "status": str(item["status"])[:120],
                    "summary": str(item["summary"])[:500],
                    "why_matters": str(item["why_matters"])[:280],
                    "heard_signal": normalize_heard_signal(str(item["heard_signal"])),
                }
        merged: list[dict[str, str]] = []
        for candidate in candidates:
            source_key = candidate["source_key"]
            if source_key not in enriched_by_key:
                raise AIServiceError(f"Rule enrichment omitted candidate {source_key}.")
            merged.append({**candidate, **enriched_by_key[source_key]})
        return merged

    def extract_comment_pairs(self, preamble: str) -> list[dict[str, str]]:
        payload = self.complete_json(
            "Return strict JSON as an array of up to three objects with keys concern, agency_response, and disposition. "
            "Use only what is established in the source. If no Comment/Response record exists, return an empty array.",
            preamble[:6000],
        )
        if not isinstance(payload, list):
            raise AIServiceError("Comment/Response extraction did not return a JSON array.")
        return [
            {
                "concern": str(item["concern"])[:800],
                "agency_response": str(item["agency_response"])[:800],
                "disposition": normalize_disposition(str(item["disposition"])),
            }
            for item in payload
            if isinstance(item, dict) and {"concern", "agency_response", "disposition"} <= set(item)
        ]

    def public_heard_findings(self, rule: dict[str, Any], comments: list[dict[str, str]], adopted_text: str) -> list[dict[str, str]]:
        payload = self.complete_json(
            "Return strict JSON as an array of findings with keys label and summary. "
            "Allowed labels: Changed, Unchanged, Partially addressed, Unclear from record. "
            "Compare the agency response to the adopted text and do not allege motive.",
            f"Rule: {json.dumps(rule)}\nComments: {json.dumps(comments)}\nAdopted text:\n{adopted_text[:7000]}",
        )
        if not isinstance(payload, list):
            raise AIServiceError("Public-heard analysis did not return a JSON array.")
        return [
            {"label": normalize_disposition(str(item["label"])), "summary": str(item["summary"])[:800]}
            for item in payload
            if isinstance(item, dict) and {"label", "summary"} <= set(item)
        ]

    def forecast_questions(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        if rule.get("action_type", "").lower() != "proposed":
            return []
        payload = self.complete_json(
            "Return strict JSON as an array of 2 or 3 forecast questions. Each object must have "
            "question, resolution_criteria, source_of_truth, and aggregate_probability. "
            "Write question as a short public prediction-market title under 90 characters, similar to Polymarket or Kalshi. "
            "Do not put dates, TAC citations, Texas Register mechanics, or source names in question. "
            "Good examples: 'Will this proposed rule be adopted?', 'Will public comments change this rule?', "
            "'Will the final rule be stricter than proposed?'. Put deadlines, citations, and exact adoption criteria only "
            "in resolution_criteria. Only create questions resolvable from public records.",
            json.dumps(rule),
        )
        if not isinstance(payload, list):
            raise AIServiceError("Forecast generation did not return a JSON array.")
        return [
            {
                "question": str(item["question"])[:120],
                "resolution_criteria": str(item["resolution_criteria"])[:800],
                "source_of_truth": str(item["source_of_truth"])[:300],
                "aggregate_probability": clamp_probability(float(item["aggregate_probability"])),
            }
            for item in payload
            if isinstance(item, dict)
            and {"question", "resolution_criteria", "source_of_truth", "aggregate_probability"} <= set(item)
        ]

    def alert_copy(self, rule: dict[str, Any], watch_value: str) -> dict[str, str]:
        payload = self.complete_json(
            "Return strict JSON with title and body for a concise in-app citizen alert. "
            "Do not overstate significance and do not use legal jargon.",
            f"Watch value: {watch_value}\nRule: {rule}",
        )
        return {"title": str(payload["title"])[:120], "body": str(payload["body"])[:500]}

    def complete_json(self, system: str, user: str) -> Any:
        text = self.complete(f"{system}\nReturn only valid JSON. No markdown.", user).strip()
        try:
            return json.loads(strip_json_fence(text))
        except json.JSONDecodeError as exc:
            raise AIServiceError("OpenAI response was not valid JSON; no alternate content was generated.") from exc


def strip_json_fence(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise AIServiceError("Expected affected_groups to be a list.")
    return [str(item)[:120] for item in value]


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_disposition(value: str) -> str:
    lowered = re.sub(r"[^a-z ]", "", value.lower())
    if "partial" in lowered:
        return "Partially addressed"
    if "declin" in lowered or "unchanged" in lowered:
        return "Unchanged"
    if "change" in lowered or "address" in lowered:
        return "Changed"
    return "Unclear from record"


def normalize_heard_signal(value: str) -> str:
    if "not yet" in value.lower():
        return "Not yet available"
    return normalize_disposition(value)
