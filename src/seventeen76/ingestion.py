from __future__ import annotations

from datetime import date

from .ai import CivicAI
from .db import Database, insert, now_iso
from .texas_register import CURRENT_ISSUE_URL, extract_issue_links, extract_rule_actions, fetch_html, html_to_text, source_snippet_for


AI_BATCH_SIZE = 10


def ingest_current_texas_register(db: Database, ai: CivicAI, url: str = CURRENT_ISSUE_URL) -> dict[str, int]:
    html = fetch_html(url)
    index_links = extract_issue_links(html, url)
    candidates = extract_rule_actions(index_links)
    if not candidates:
        return {"issues": 0, "rules": 0}
    page_cache: dict[str, str] = {}
    hydrated = []
    for idx, candidate in enumerate(candidates, start=1):
        page_url = candidate["source_url"].split("#", 1)[0]
        if page_url not in page_cache:
            page_cache[page_url] = html_to_text(fetch_html(page_url))
        hydrated.append(
            {
                **candidate,
                "source_key": f"rule-{idx}",
                "source_snippet": source_snippet_for(page_cache[page_url], candidate["tac_citation"]),
            }
        )
    rule_actions = []
    for start in range(0, len(hydrated), AI_BATCH_SIZE):
        rule_actions.extend(ai.enrich_rule_actions(url, hydrated[start : start + AI_BATCH_SIZE]))
    with db.connect() as conn:
        issue_id = insert(
            conn,
            "issues",
            {
                "issue_date": date.today().isoformat(),
                "title": "Texas Register current issue",
                "url": url,
                "raw_html": html,
                "created_at": now_iso(),
            },
        )
        inserted = 0
        for item in rule_actions:
            rule_id = insert(
                conn,
                "rule_actions",
                {
                    "issue_id": issue_id,
                    "agency": item["agency"],
                    "title": item["title"],
                    "tac_citation": item["tac_citation"],
                    "action_type": item["action_type"],
                    "status": item["status"],
                    "summary": item["summary"],
                    "why_matters": item["why_matters"],
                    "heard_signal": item["heard_signal"],
                    "source_url": item["source_url"],
                    "created_at": now_iso(),
                },
            )
            source_id = insert(
                conn,
                "sources",
                {
                    "rule_id": rule_id,
                    "label": "Texas Register source",
                    "url": item["source_url"],
                    "snippet": item["source_snippet"],
                    "retrieved_at": now_iso(),
                },
            )
            insert(
                conn,
                "rule_stages",
                {
                    "rule_id": rule_id,
                    "stage": item["action_type"].lower(),
                    "preamble": item["source_snippet"],
                    "text": item["source_snippet"],
                    "source_id": source_id,
                },
            )
            inserted += 1
        return {"issues": 1, "rules": inserted}
