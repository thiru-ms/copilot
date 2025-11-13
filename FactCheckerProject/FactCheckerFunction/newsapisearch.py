import os
import time
import hashlib
import logging
from typing import List, Dict, Optional, Tuple

try:
    from newsdataapi import NewsDataApiClient  # optional
except ImportError:
    NewsDataApiClient = None  # type: ignore

import requests
from dateutil import parser as dateparser
from urllib.parse import urlparse

# Your existing classifier
from factcheck_llm import classify_with_citations


NEWSDATA_BASE_URL = "https://newsdata.io/api/1/latest"
DEFAULT_MAX_CITATIONS = 4


def classify_with_newsdata(
    query: str,
    *,
    country: str = "in",
    language: str = "en",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page_limit: int = 1,
    max_retries: int = 3,
    retry_backoff_sec: float = 1.5,
    api_key: Optional[str] = None,
    use_sdk: bool = True,
) -> Dict:
    """
    End-to-end:
      1) Search NewsData for `query` with simple filters.
      2) Normalize to [{title, source, url, snippet}].
      3) Dedupe by URL and cap to 4 citations.
      4) Call classify_with_citations(query, citations).
    """
    api_key = api_key or os.getenv("NEWSDATA_API_KEY")
    if not api_key:
        raise ValueError("Missing API key. Set NEWSDATA_API_KEY or pass api_key=...")

    params = {
        "apikey": api_key,
        "q": query,
        "language": language,
        "country": country,
    }
    if from_date:
        params["from_date"] = _to_yyyy_mm_dd(from_date)
    if to_date:
        params["to_date"] = _to_yyyy_mm_dd(to_date)

    sdk_client = NewsDataApiClient(apikey=api_key) if (use_sdk and NewsDataApiClient) else None

    # Accumulate pages
    all_items: List[Dict] = []
    seen_hashes = set()
    next_page_token: Optional[str] = None

    for _ in range(max(1, page_limit)):
        if next_page_token:
            params["page"] = next_page_token

        raw = _fetch_newsdata(params, sdk_client, max_retries, retry_backoff_sec)
        items, next_page_token = _normalize_payload(raw)

        for it in items:
            h = _hash(it.get("url") or it.get("title") or "")
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            all_items.append(it)

        if not next_page_token:
            break

    citations = _dedupe_by_url(all_items)[:DEFAULT_MAX_CITATIONS]
    if len(citations) < 2:
        logging.info("Fewer than 2 citations found; classifier may return 'Unclear'.")

    return classify_with_citations(query, citations)


# -----------------------------
# Internals
# -----------------------------
def _fetch_newsdata(
    params: Dict,
    sdk_client,
    max_retries: int,
    backoff: float,
) -> Dict:
    """
    Fetch once via SDK if available; otherwise via HTTP.
    Retries on 429/RequestException with exponential backoff.
    """
    attempt = 0
    while True:
        try:
            if sdk_client:
                sdk_params = {k: v for k, v in params.items() if k != "apikey"}
                logging.info(f'params:{sdk_params}')
                resp = sdk_client.news_api(**sdk_params)
                logging.info(f'response:{resp}')
                if not isinstance(resp, dict):
                    raise RuntimeError("Unexpected SDK response type.")
                return resp
            else:
                url = NEWSDATA_BASE_URL + f'?apikey=pub_cf12a6fd139c416496d5b562f52c0c4d&q={params["q"]}&country=in&language=en'
                logging.info(f'url:{url}')
                r = requests.get(url, timeout=20)
                if r.status_code == 429:
                    raise requests.RequestException("Rate limited (429)")
                r.raise_for_status()
                return r.json()
        except Exception as ex:
            attempt += 1
            if attempt > max_retries:
                logging.error(f"NewsData call failed after {attempt} attempts: {ex}")
                raise
            time.sleep(backoff ** attempt)


def _normalize_payload(raw: Dict) -> Tuple[List[Dict], Optional[str]]:
    """
    Normalize NewsData response to a simple list of dicts with
    {title, source, url, snippet} and return nextPage token.
    """
    results = raw.get("results") or []
    items: List[Dict] = []

    for r in results:
        title = (r.get("title") or "").strip()
        url = (r.get("link") or r.get("url") or "").strip()
        source_url = (r.get("source_url") or r.get("link") or "").strip()
        source = (r.get("source_id") or _domain(source_url) or "").strip()
        snippet = _truncate((r.get("description") or r.get("content") or "").strip(), 400)

        items.append({
            "title": title or url or "(untitled)",
            "source": source,
            "url": url,
            "snippet": snippet,
        })

    return items, raw.get("nextPage")


# -----------------------------
# Utilities
# -----------------------------
def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url

def _to_yyyy_mm_dd(s: str) -> str:
    try:
        return dateparser.parse(s).date().isoformat()
    except Exception:
        return s

def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else (text[: max_len - 1].rstrip() + "…")

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _dedupe_by_url(items: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for it in items:
        u = it.get("url")
        if u and u not in seen:
            seen.add(u)
            out.append(it)
    return out