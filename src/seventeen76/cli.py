from __future__ import annotations

import argparse

from .ai import CivicAI
from .db import Database
from .ingestion import ingest_current_texas_register


def main() -> None:
    parser = argparse.ArgumentParser(description="1776 backend utilities")
    parser.add_argument("command", nargs="?", default="init", choices=["init", "ingest-current"])
    args = parser.parse_args()

    db = Database()
    db.init_schema()
    if args.command == "init":
        print(f"Initialized 1776 database at {db.path}")
    elif args.command == "ingest-current":
        result = ingest_current_texas_register(db, CivicAI())
        print(f"Ingested {result['rules']} rule actions from the current Texas Register issue.")
