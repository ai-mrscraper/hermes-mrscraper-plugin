"""The seven native tool surfaces for MrScraper's direct HTTP API.

Tool and parameter descriptions follow the MrScraper standard service reference
shared by the CLI, SDKs, and integrations. Get screenshot additionally accepts
``warm_start``.
"""

from __future__ import annotations

import copy
from typing import Any

from .client import MrScraperClient, MrScraperError
from .request_options import DEFAULT_JSON_PROMPT, SCREENSHOT_AREAS, WAIT_UNTIL_EVENTS
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


def _boolean(description: str, default: bool = False) -> dict:
    return {"type": "boolean", "default": default, "description": description}


def _country(description: str) -> dict:
    return {"type": "string", "pattern": "^[A-Za-z]{2}$", "default": "us",
            "description": description}


URL = {"type": "string", "description": "Absolute HTTP or HTTPS URL of the page to process."}
PAGE = {
    "url": URL,
    "timeout": {"type": "integer", "minimum": 1, "maximum": 300, "default": 300,
                "description": "Page load timeout in seconds, from 1 to 300. "
                               "The HTTP request allows 30 additional seconds."},
    "geo_code": _country("Two-letter country code to load the page from, sent in lowercase."),
    "proxy_country": _country("Two-letter country code of the proxy server, sent in lowercase."),
    "super": _boolean("Whether to route the request through real devices."),
    "wait_until": {"type": "string", "enum": list(WAIT_UNTIL_EVENTS),
                   "default": "domcontentloaded",
                   "description": "Navigation completion event to wait for: "
                                  "domcontentloaded, load, networkidle0, or networkidle2."},
    "proxy": {"type": "string", "description": "Custom proxy URL used to load the page."},
    "max_retries": {"type": "integer", "minimum": 0,
                    "description": "Maximum number of retries, as a nonnegative integer. "
                                   "Omit this parameter for no limit."},
    "save_result": _boolean("Whether to save the result to the dashboard Result tab."),
}
LOADING = {
    "block_resources": _boolean(
        "Whether to block images, fonts, and stylesheets while loading the page."),
    "wait_for_selector": {"type": "string",
                          "description": "Wait for the page to contain the specified CSS "
                                         "selector before returning the result."},
    "return_cookie": _boolean("Whether to include browser session cookies in the response."),
}
BROWSER_RENDERING = _boolean(
    "Whether to render the page in a browser before returning the result.")
WARM_START = _boolean(
    "Whether to enable warm start for more reliable scraping, at the cost of additional latency.")
INCLUDE_HTML = "Whether to include the page HTML in the response."

SERVICES = (
    ("mrscraper_status", "status",
     "Return the raw account status API response without summarizing, redacting body fields, "
     "or adding calculated fields.",
     {}, []),
    ("mrscraper_scrape_html", "scrape_html",
     "Retrieve the raw HTML of a page. Browser rendering is optional.",
     {**PAGE, **LOADING, "browser_rendering": BROWSER_RENDERING, "warm_start": WARM_START},
     ["url"]),
    ("mrscraper_scrape_markdown", "scrape_markdown",
     "Retrieve a page as Markdown. Including HTML also enables browser rendering and returns "
     "both outputs as JSON.",
     {**PAGE, **LOADING, "browser_rendering": BROWSER_RENDERING, "warm_start": WARM_START,
      "html": _boolean(INCLUDE_HTML)},
     ["url"]),
    ("mrscraper_get_screenshot", "get_screenshot",
     "Capture a base64 screenshot of the full page or top viewport. "
     "Browser rendering is always enabled.",
     {**PAGE, **LOADING, "warm_start": WARM_START,
      "screenshot": {"type": "string", "enum": list(SCREENSHOT_AREAS), "default": "full",
                     "description": "Screenshot area to capture: full for the entire page "
                                    "or top for the top viewport."},
      "html": _boolean(INCLUDE_HTML, True),
      "markdown": _boolean("Whether to include the page Markdown in the response.")},
     ["url"]),
    ("mrscraper_scrape_brand", "scrape_brand",
     "Extract a website's colors, typography, logos, and social links as JSON.",
     {"url": URL}, ["url"]),
    ("mrscraper_scrape_json", "scrape_json",
     "Extract structured JSON from a page using a natural-language prompt. "
     "Append Json Schema: and a JSON schema to shape the output.",
     {**PAGE,
      "prompt": {"type": "string", "default": DEFAULT_JSON_PROMPT,
                 "description": "Instructions describing the data to extract. "
                                "Append Json Schema: and a JSON schema to shape the output."},
      "browser_rendering": BROWSER_RENDERING,
      "html": _boolean(INCLUDE_HTML),
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
