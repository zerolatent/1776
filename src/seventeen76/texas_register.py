from __future__ import annotations

import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


CURRENT_ISSUE_URL = "https://www.sos.state.tx.us/texreg/sos/index.html"


def fetch_html(url: str = CURRENT_ISSUE_URL, timeout: int = 20) -> str:
    request = Request(normalize_url(url), headers={"User-Agent": "1776 accountability app"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/:%"),
            parts.query,
            parts.fragment,
        )
    )


def extract_issue_links(html: str, base_url: str = CURRENT_ISSUE_URL) -> list[dict[str, str]]:
    """Extract index links with Texas Register section context."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[dict[str, str]] = []
    section = ""
    for node in soup.find_all(["h3", "a"]):
        if node.name == "h3":
            section = clean_text(node.get_text(" ", strip=True))
            continue
        href = node.get("href")
        label = clean_text(node.get_text(" ", strip=True))
        if not href or not label:
            continue
        links.append(
            {
                "label": label,
                "url": normalize_url(urljoin(base_url, href)),
                "section": section,
                "agency": clean_text(node.get("partname", "")),
                "chapter": clean_text(node.get("chaptername", "")),
                "division": clean_text(node.get("divisionname", "")),
                "title_name": clean_text(node.get("titlename", "")),
                "register_division": clean_text(node.get("div-name", "")),
            }
        )
    return links


def extract_rule_pages(index_links: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return unique Proposed/Adopted detail pages from the issue index."""
    pages: dict[tuple[str, str], dict[str, str]] = {}
    for link in index_links:
        section = link.get("section", "")
        if section not in {"PROPOSED RULES", "ADOPTED RULES", "EMERGENCY RULES", "WITHDRAWN RULES"}:
            continue
        url_without_fragment = link["url"].split("#", 1)[0]
        key = (section, url_without_fragment)
        pages.setdefault(
            key,
            {
                "section": section,
                "action_type": section_to_action_type(section),
                "url": url_without_fragment,
                "labels": [],
            },
        )
        pages[key]["labels"].append(link["label"])
    return list(pages.values())


def extract_rule_actions(index_links: list[dict[str, str]]) -> list[dict[str, str]]:
    """Parse index links into candidate rule actions from official source labels."""
    actions: list[dict[str, str]] = []
    current_agency = ""
    current_topic = ""
    current_chapter = ""
    for link in index_links:
        section = link.get("section", "")
        if section not in {"PROPOSED RULES", "ADOPTED RULES", "EMERGENCY RULES", "WITHDRAWN RULES"}:
            continue
        label = link["label"]
        link_agency = titlecase_heading(link.get("agency", ""))
        link_chapter = titlecase_heading(link.get("chapter", ""))
        if link_agency and link_agency != current_agency:
            current_agency = link_agency
            current_topic = ""
            current_chapter = link_chapter
            continue
        if link_chapter and link_chapter != current_chapter:
            current_chapter = link_chapter
            current_topic = link_chapter
        if is_tac_citation(label):
            if not current_agency:
                current_agency = titlecase_heading(label.split("TAC", 1)[0].strip()) or "Texas agency"
            title = current_topic or current_chapter or label
            actions.append(
                {
                    "agency": current_agency,
                    "title": titlecase_heading(title),
                    "tac_citation": label,
                    "action_type": section_to_action_type(section),
                    "source_url": link["url"],
                }
            )
            continue
        if is_agency_label(label) and not link_agency:
            current_agency = titlecase_heading(label)
            current_topic = ""
            current_chapter = ""
            continue
        current_topic = titlecase_heading(label)
    return actions


def source_snippet_for(page_text: str, tac_citation: str, window: int = 700) -> str:
    first_citation = tac_citation.split(",")[0].strip()
    idx = page_text.find(first_citation)
    if idx < 0:
        idx = 0
    start = max(0, idx - window // 3)
    if start > 0:
        boundary = page_text.rfind(". ", 0, start)
        start = boundary + 2 if boundary >= 0 else 0
    end = min(len(page_text), idx + window)
    return page_text[start:end].strip()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    return clean_text(text)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def section_to_action_type(section: str) -> str:
    return {
        "PROPOSED RULES": "Proposed",
        "ADOPTED RULES": "Adopted",
        "EMERGENCY RULES": "Emergency",
        "WITHDRAWN RULES": "Withdrawn",
    }.get(section, "Rule")


def is_tac_citation(label: str) -> bool:
    return bool(re.search(r"\b\d+\s+TAC\s+§", label))


def is_agency_label(label: str) -> bool:
    if label != label.upper():
        return False
    return any(
        term in label
        for term in [
            "COMMISSION",
            "DEPARTMENT",
            "BOARD",
            "OFFICE",
            "AGENCY",
            "AUTHORITY",
            "COUNCIL",
            "COMPTROLLER",
            "SECRETARY",
            "RAILROAD",
            "TEXAS ",
        ]
    )


def titlecase_heading(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip().title()
    text = re.sub(r"'S\b", "'s", text)
    text = text.replace("[,]", ",")
    for word in ["And", "Of", "The", "For", "In", "On", "To", "With", "By"]:
        text = re.sub(rf"\b{word}\b", word.lower(), text)
    if text.startswith("Texas "):
        text = "Texas " + text[len("Texas ") :]
    return text[:1].upper() + text[1:]
