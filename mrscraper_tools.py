"""The seven native tool surfaces for MrScraper's direct HTTP API.

Tool and parameter descriptions follow the MrScraper standard service reference
shared by the CLI, SDKs, and integrations. Each tool offers only the parameters
the Scraper API reference documents.
"""

from __future__ import annotations

import copy
from typing import Any

from .client import MrScraperClient, MrScraperError
from .request_options import (
    DEFAULT_JSON_PROMPT,
    MAX_CACHE_AGE_MS,
    MAX_SELECTOR_LENGTH,
    MAX_TIMEOUT,
    SCREENSHOT_PATTERN,
)
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
            # Shared property definitions must not alias across registered schemas.
            "type": "object", "properties": copy.deepcopy(properties),
            "required": required, "additionalProperties": False,
        },
    }


def _boolean(description: str, default: bool | None = False) -> dict:
    schema: dict[str, Any] = {"type": "boolean", "description": description}
    if default is not None:
        schema["default"] = default
    return schema


def _country(description: str) -> dict:
    return {"type": "string", "pattern": "^[A-Za-z]{2}$", "description": description}


URL = {"type": "string", "description": "Absolute HTTP or HTTPS URL of the page to process."}
BROWSER_RENDERING = _boolean(
    "Whether to load the page in a browser: true always does and false never does. "
    "Omit it to load the page without a browser first and switch to a browser "
    "automatically if the request is blocked.",
    default=None,
)
TIMEOUT = {"type": "integer", "minimum": 1, "maximum": MAX_TIMEOUT, "default": 300,
           "description": "Maximum seconds to wait for the scrape, from 1 to 330. "
                          "The HTTP request allows 30 additional seconds."}
WARM_START = _boolean(
    "Whether to open the site's home page first to warm the session before loading the "
    "target URL.")
BLOCK_RESOURCES = _boolean(
    "Whether to block images, fonts, and stylesheets while loading the page.")
WAIT_FOR_SELECTOR = {"type": "string", "maxLength": MAX_SELECTOR_LENGTH,
                     "description": "CSS selector or text to wait for on the page before "
                                    "returning the result, up to 500 characters."}
ACTION = {"type": "string",
          "description": "Scraper action that routes the request or simply flags it, "
                         "useful for separating analytics per domain."}
CACHE = {
    "geo_code": _country("Two-letter country code to load the page from, sent in lowercase."),
    "max_age": {"type": "integer", "minimum": 0, "maximum": MAX_CACHE_AGE_MS, "default": 0,
                "description": "Return a cached result of the same request when it is newer "
                               "than the selected age. A cached result costs the same tokens "
                               "as the original scrape."},
    "max_retries": {"type": "integer", "minimum": 0,
                    "description": "Maximum number of retries, as a nonnegative integer. "
                                   "Omit this parameter for no limit."},
}
LOADING = {
    "browser_rendering": BROWSER_RENDERING,
    "timeout": TIMEOUT,
    "warm_start": WARM_START,
    "block_resources": BLOCK_RESOURCES,
    "wait_for_selector": WAIT_FOR_SELECTOR,
}
SCREENSHOT_CAPTURE = {
    "type": "string", "pattern": SCREENSHOT_PATTERN, "default": "false",
    "description": "Screenshot to capture with the HTML: false for none, full for the entire "
                   "page, top for the first viewport, or a WIDTHxHEIGHT viewport from 100 to "
                   "3840 pixels with an optional -ZOOM percent from 25 to 300, such as 1280x800 "
                   "or 1920x1080-75. Setting a screenshot also sends browserRendering=true.",
}

SERVICES = (
    ("mrscraper_status", "status",
     "Return the raw account status API response without summarizing, redacting body fields, "
     "or adding calculated fields.",
     {}, []),
    ("mrscraper_scrape_html", "scrape_html",
     "Retrieve the raw HTML of a page. Browser rendering is optional.",
     {"url": URL, **LOADING, "action": ACTION, **CACHE, "screenshot": SCREENSHOT_CAPTURE},
     ["url"]),
    ("mrscraper_scrape_markdown", "scrape_markdown",
     "Retrieve a page as clean Markdown. Browser rendering is optional.",
     {"url": URL, **LOADING, "action": ACTION, **CACHE},
     ["url"]),
    ("mrscraper_get_screenshot", "get_screenshot",
     "Capture a base64 PNG screenshot of the full page. Browser rendering is always enabled.",
     {"url": URL, "timeout": TIMEOUT, "wait_for_selector": WAIT_FOR_SELECTOR, **CACHE},
     ["url"]),
    ("mrscraper_scrape_brand", "scrape_brand",
     "Extract a website's colors, typography, logos, and social links as JSON.",
     # Scrape brand has no default timeout: it is sent only when set.
     {"url": URL, "timeout": {key: value for key, value in TIMEOUT.items() if key != "default"},
      "warm_start": WARM_START, "geo_code": CACHE["geo_code"]},
     ["url"]),
    ("mrscraper_scrape_json", "scrape_json",
     "Extract structured JSON from a page using a natural-language prompt. "
     "Append Json Schema: and a JSON schema to shape the output.",
     {"url": URL,
      "prompt": {"type": "string", "default": DEFAULT_JSON_PROMPT,
                 "description": "Instructions describing the data to extract. "
                                "Append Json Schema: and a JSON schema to shape the output."},
      "html": _boolean("Whether to include the page HTML in the response.", True),
      **LOADING, **CACHE,
      "screenshot": _boolean("Whether to include a base64 screenshot in the response.")},
     ["url"]),
    ("mrscraper_web_search", "web_search",
     "Search the web and return ranked results with titles, URLs, descriptions, and sources.",
     {"query": {"type": "string", "minLength": 1, "maxLength": 1000,
                "description": "Search query text, trimmed before sending, containing "
                               "1 to 1000 characters."},
      "country": _country("Two-letter country code to search from, sent in lowercase."),
      "num_results": {"type": "integer", "minimum": 10, "maximum": 100, "default": 10,
                      "description": "Number of search results to request, as an integer "
                                     "from 10 to 100. Fewer results may be returned."}},
     ["query"]),
)

MRSCRAPER_TOOLS = [
    (name, _schema(name, description, properties, required), _handler(operation))
    for name, operation, description, properties, required in SERVICES
]
