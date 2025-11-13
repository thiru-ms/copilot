import os, json, requests, time
import logging
import time
from urllib.parse import urlparse
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder, RunStatus, MessageRole, MessageTextContent

from factcheck_llm import classify_with_citations

AZURE_OPENAI_PROJECT_ENDPOINT   = os.getenv("AZURE_OPENAI_PROJECT_ENDPOINT")
AZURE_OPENAI_ASSISTANT_ID    = os.getenv("AZURE_OPENAI_ASSISTANT_ID")

TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.EXPIRED,
    RunStatus.REQUIRES_ACTION
}

def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _snippet_around(text: str, start: int, end: int, pad: int = 120) -> str:
    try:
        left = max(0, start - pad)
        right = min(len(text), end + pad)
        snippet = text[left:right].strip()
        return " ".join(snippet.split())
    except Exception:
        return ""


def _articles_from_text_content(item: MessageTextContent) -> list[dict]:
    """
    Extract articles from a MessageTextContent instance
    by walking item.text.annotations and building
    {title, source, url, snippet}.
    """
    articles: list[dict] = []

    # Defensive guards: item.text can be None in pathological cases
    text_obj = getattr(item, "text", None)
    if not text_obj:
        return articles

    text_value = getattr(text_obj, "value", "") or ""
    annotations = getattr(text_obj, "annotations", None) or []

    for ann in annotations:
        # ann is an SDK object; access attributes directly
        ann_type = getattr(ann, "type", None)
        if ann_type != "url_citation":
            continue

        url_citation = getattr(ann, "url_citation", None)
        if not url_citation:
            continue

        url = getattr(url_citation, "url", None)
        if not url:
            continue

        title = getattr(url_citation, "title", None) or url
        source = _domain_from_url(url)

        # Some SDKs expose indices at annotation root
        start_idx = getattr(ann, "start_index", 0) or 0
        end_idx = getattr(ann, "end_index", 0) or 0
        snippet = _snippet_around(text_value, start_idx, end_idx)

        articles.append({
            "title": title,
            "source": source,
            "url": url,
            "snippet": snippet,
        })

    return articles


def _collect_articles_from_message_sdk(message) -> list[dict]:
    """
    Collect articles from an SDK message object by iterating message.content
    and handling only MessageTextContent items.
    """
    # Only consider assistant/agent messages
    role = getattr(message, "role", None)
    if role not in (MessageRole.AGENT):
        return []

    content_items = getattr(message, "content", None) or []
    all_articles: list[dict] = []

    for item in content_items:
        logging.info(f'item:{item}')
        # Direct SDK-type check: you reported this class name in your env
        if isinstance(item, MessageTextContent):
            all_articles.extend(_articles_from_text_content(item))
        else:
            # You can log the class to see what else appears
            # e.g., MessageImageFileContent, MessageToolCallContent, etc.
            logging.debug(f"Skipping non-text content item: {type(item)}")

    logging.info(f'all:{all_articles}')
    return all_articles


def _dedupe_and_limit(articles: list[dict], max_allowed: int = 4) -> list[dict]:
    seen = set()
    unique = []
    for a in articles:
        u = a.get("url")
        if u and u not in seen:
            seen.add(u)
            unique.append(a)
    # Cap to 4 (your classifier prompt requests 2–4 citations)
    return unique[:max_allowed]


def get_response_and_classify(query: str):
    """
    End-to-end flow using SDK object properties directly (no dict coercion):
      1) Create thread, post user message, run agent.
      2) Iterate messages; for each assistant message, collect citations
         from MessageTextContent annotations.
      3) Dedupe & cap evidence.
      4) Call classify_with_citations(query, articles).
    """
    project = AIProjectClient(
        credential=DefaultAzureCredential(),
        endpoint=AZURE_OPENAI_PROJECT_ENDPOINT
    )

    agent = project.agents.get_agent(AZURE_OPENAI_ASSISTANT_ID)
    thread = project.agents.threads.create()
    logging.info(f"Created thread: {thread.id}")

    project.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content=query
    )

    run = project.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id, instructions="generate annotations as required")
    logging.info(f"Run status: {run.status}")
    counter = 0

    while run.status not in TERMINAL_STATUSES and counter < 10:
        time.sleep(0.8)
        run = project.agents.runs.get(thread_id=thread.id, run_id=run.id)
        logging.info(f"Run status: {run.status}")
        counter+=1

    if run.status == RunStatus.FAILED:
        logging.error(f"Run failed: {run.last_error}")
        return classify_with_citations(query, articles=[])

    # Read messages in ASC order and collect citations
    msg_iter = project.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)

    all_articles: list[dict] = []
    for msg in msg_iter:
        try:
            logging.info(f'msg:{msg}')
            all_articles.extend(_collect_articles_from_message_sdk(msg))
        except Exception as e:
            logging.warning(f"Failed to parse SDK message {getattr(msg, 'id', '')}: {e}")

    articles = _dedupe_and_limit(all_articles, max_allowed=4)

    if len(articles) < 2:
        logging.info("Fewer than 2 citations found; classifier may return 'Unclear' based on evidence.")

    return classify_with_citations(query, articles)