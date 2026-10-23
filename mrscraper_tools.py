"""The three native tool surfaces for MrScraper's direct HTTP API."""

from __future__ import annotations

from typing import Any

from .client import MrScraperClient, MrScraperError
from tools.registry import tool_error, tool_result


def _handler(operation: str):
    def handle(args: dict, **_kwargs: Any) -> str:
        try:
            return tool_result(getattr(MrScraperClient(), operation)(args))
        except MrScraperError as exc:
            status = getattr(exc, "status_code", None)
            return tool_error(str(exc), **({"status_code": status} if status is not None else {}))
    return handle


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object", "properties": properties,
            "required": required, "additionalProperties": False,
        },
    }


_SCRAPER_PROPERTIES = {
    "url": {"type": "string", "description": "Public HTTP or HTTPS page URL."},
    "html": {"type": "boolean", "default": True},
    "markdown": {"type": "boolean", "default": False},
    "timeout": {"type": "integer", "minimum": 1, "maximum": 300, "default": 120,
                "description": "Page deadline in seconds; HTTP allows 30 additional seconds."},
    "geo_code": {"type": "string", "default": "US"},
    "proxy_country": {"type": "string", "description": "Optional compatibility proxy country."},
    "browser_rendering": {"type": "boolean", "description": "Omit for automatic browser fallback."},
    "super": {"type": "boolean", "default": False, "description": "Real-device routing."},
    "use_proxy": {"type": "boolean", "default": True},
    "proxy": {"type": "string", "description": "Optional custom proxy as username:password@host:port."},
    "wait_for_selector": {"type": "string"},
    "home_page": {"type": "boolean", "default": False, "description": "Warm-start at the site's root."},
    "screenshot": {"type": "boolean", "default": False, "description": "Capture a screenshot; forces browser rendering."},
    "block_resources": {"type": "boolean", "default": False},
    "bypass_proxy": {"type": "boolean", "default": False},
    "cookie_jar": {"type": "string"},
    "headers": {"oneOf": [{"type": "object", "additionalProperties": {"type": "string"}}, {"type": "string"}],
                "description": "Target-page headers, not MrScraper authentication."},
    "max_retries": {"type": "integer", "minimum": 0, "default": 3,
                    "description": "Server-side retries; HTTP calls are not retried locally."},
    "token_cap": {"type": "integer", "minimum": 0},
    "stream": {"type": "boolean", "description": "Request server streaming; the complete response is buffered."},
}
_SEARCH_PROPERTIES = {
    "url": {"type": "string", "description": "Google query text or Google search URL containing q."},
    "raw": {"type": "boolean", "default": False, "description": "Request raw HTML; overrides format."},
    "region": {"type": "string"},
    "language": {"type": "string"},
    "page": {"type": "integer", "minimum": 1},
    "format": {"type": "string", "enum": ["json", "html"], "default": "json"},
    "render_js": {"type": "boolean", "default": False},
    "timeout": {"type": "number", "exclusiveMinimum": 0, "default": 600},
}
MRSCRAPER_TOOLS = [
    (
        "mrscraper_scraper_api",
        _schema(
            "mrscraper_scraper_api",
            "Fetch a public web page as rendered HTML, Markdown, screenshot, or a combination.",
            _SCRAPER_PROPERTIES,
            ["url"],
        ),
        _handler("scraper_api"),
    ),
    (
        "mrscraper_web_search",
        _schema(
            "mrscraper_web_search",
            "Search the web to retrieve real-time search results, including relevant website URLs, titles, descriptions, and related questions based on a given query.",
            _SEARCH_PROPERTIES,
            ["url"],
        ),
        _handler("web_search"),
    ),
    (
        "mrscraper_account",
        _schema("mrscraper_account", "Inspect account subscription, token usage, quota, and rate limits.",
                {"timeout": {"type": "number", "exclusiveMinimum": 0, "default": 30}}, []),
        _handler("account"),
    ),
]
