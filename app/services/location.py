"""Utilities for resolving a pincode to a city and fuzzy-matching addresses.

Strategy:
- Try local SQLite DB (settings.database_url) for common table names.
- If not available and `google_maps_api_key` is set, call Google Geocoding API.
- Fuzzy-match using difflib.SequenceMatcher with adjustable threshold.

The matching logic is conservative to reduce false positives (e.g., Mumbai vs Mumbra).
"""

from __future__ import annotations

import os
import re
import sqlite3
from difflib import SequenceMatcher
from typing import Optional

import httpx

from app.config import settings

ABBREVIATIONS = {
    "bbsr": "bhubaneswar",
}

COMMON_TABLE_CANDIDATES = [
    "pincodes",
    "pincode",
    "postal_codes",
    "post_offices",
    "locations",
    "cities",
]

CITY_COLUMN_CANDIDATES = ["city", "name", "district", "taluk", "place"]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _db_path_from_url(sqlite_url: str) -> Optional[str]:
    if not sqlite_url:
        return None
    if sqlite_url.startswith("sqlite:///"):
        return sqlite_url.replace("sqlite:///", "")
    return None


def get_city_from_pincode(pincode: str) -> Optional[str]:
    """Try to resolve a pincode to a city name.

    Returns the city name if found, otherwise None.
    """
    # try local DB
    db_path = _db_path_from_url(settings.database_url)
    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            # find a candidate table and column
            for table in COMMON_TABLE_CANDIDATES:
                try:
                    cur.execute(f"PRAGMA table_info('{table}')")
                    cols = [r[1].lower() for r in cur.fetchall()]
                    if not cols:
                        continue
                    for city_col in CITY_COLUMN_CANDIDATES:
                        if city_col in cols and ("pincode" in cols or "postal" in cols or "pin" in cols):
                            cur.execute(
                                f"SELECT {city_col} FROM {table} WHERE pincode = ? LIMIT 1",
                                (pincode,),
                            )
                            row = cur.fetchone()
                            if row and row[0]:
                                return str(row[0])
                except sqlite3.Error:
                    continue
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # fallback to Google Geocoding API if key provided
    api_key = settings.google_maps_api_key
    if api_key:
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {"address": pincode, "key": api_key}
            resp = httpx.get(url, params=params, timeout=10.0)
            data = resp.json()
            if data.get("results"):
                for comp in data["results"][0].get("address_components", []):
                    if "locality" in comp.get("types", []) or "postal_town" in comp.get("types", []):
                        return comp.get("long_name")
        except Exception:
            pass

    return None


def address_matches_pincode(address: str, pincode: str) -> bool:
    """Return True if the provided address likely belongs to the given pincode.

    Heuristics:
    - Resolve pincode -> city (best effort).
    - If city found, check for exact substring of normalized city in normalized address.
    - Otherwise, compute fuzzy ratio against address tokens with conservative thresholds.
    - If resolution fails (no city), return True (don't drop by default).
    """
    if not address:
        return True

    target = get_city_from_pincode(pincode)
    if not target:
        return True

    target_norm = _normalize(ABBREVIATIONS.get(target.lower(), target.lower()))
    addr_norm = _normalize(address)

    if target_norm and target_norm in addr_norm:
        return True

    # split address into tokens (commas, spaces)
    tokens = re.split(r"[ ,\-/()]+", address or "")
    tokens = [t for t in tokens if t]

    # conservative fuzzy matching
    for token in tokens:
        tok = _normalize(token)
        if not tok:
            continue
        # exact contains
        if tok == target_norm:
            return True
        # short token: require near exact
        if len(target_norm) < 5 or len(tok) < 5:
            thresh = 0.95
        else:
            thresh = float(settings.location_match_threshold)
        ratio = SequenceMatcher(None, tok, target_norm).ratio()
        if ratio >= thresh:
            return True

    return False
