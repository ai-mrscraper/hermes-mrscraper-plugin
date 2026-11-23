"""Validate tool arguments and serialize the seven MrScraper service requests."""

from __future__ import annotations

import re
from typing import Any, NoReturn
from urllib.parse import urlencode

from tools.url_safety import is_safe_url
from tools.website_policy import check_website_access

DEFAULT_JSON_PROMPT = "Extract all data as complete as possible."
MAX_GET_URL_LENGTH = 8000
TRANSPORT_GRACE_SECONDS = 30
SEARCH_TIMEOUT = 120
STATUS_TIMEOUT = 600
MAX_TIMEOUT = 330
MAX_SELECTOR_LENGTH = 500
MAX_CACHE_AGE_MS = 604_800_000
SCREENSHOT_PATTERN = r"^(false|full|top|[0-9]{3,4}x[0-9]{3,4}(-[0-9]{2,3})?)$"
_VIEWPORT = re.compile(r"^(\d{3,4})x(\d{3,4})(?:-(\d{2,3}))?$")

_LOADING = ("browser_rendering", "timeout", "warm_start", "block_resources", "wait_for_selector")
_CACHE = ("geo_code", "save_result", "max_age", "token_cap", "max_retries")
SERVICE_OPTIONS: dict[str, tuple[str, ...]] = {
    "status": (),
    "scrape_html": ("url", *_LOADING, "action", *_CACHE, "screenshot"),
    "scrape_markdown": ("url", *_LOADING, "action", *_CACHE),
    "get_screenshot": ("url", "timeout", "wait_for_selector", *_CACHE),
    "scrape_brand": ("url", "timeout", "warm_start", "geo_code"),
    "scrape_json": ("url", "prompt", "html", *_LOADING, *_CACHE, "screenshot"),
    "web_search": ("query", "country", "num_results"),
}


def _error(message: str) -> NoReturn:
    from .client import MrScraperError
    raise MrScraperError(message)


def check_options(service: str, args: dict[str, Any]) -> None:
    """Reject options that belong to another service or an earlier plugin version."""
    if not isinstance(args, dict):
        _error("Tool arguments must be an object.")
    unknown = sorted(set(args) - set(SERVICE_OPTIONS[service]))
    if unknown:
        supported = ", ".join(SERVICE_OPTIONS[service]) or "none"
        _error(f"Unsupported options: {', '.join(unknown)}. Supported options: {supported}.")


def _boolean(args: dict[str, Any], name: str, default: bool) -> bool:
    value = args.get(name)
    if value is None:
        return default
    if not isinstance(value, bool):
        _error(f"{name} must be a boolean.")
    return value


def _optional_boolean(args: dict[str, Any], name: str) -> bool | None:
    value = args.get(name)
    if value is not None and not isinstance(value, bool):
        _error(f"{name} must be a boolean.")
    return value


def _integer(
    args: dict[str, Any], name: str, default: int | None, minimum: int,
    maximum: int = 2**53 - 1,
) -> int | None:
    value = args.get(name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        _error(f"{name} must be an integer from {minimum} to {maximum}.")
    return value


def _optional_text(args: dict[str, Any], name: str) -> str | None:
    value = args.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be a non-empty string.")
    return value.strip()


def _selector(args: dict[str, Any]) -> str | None:
    selector = _optional_text(args, "wait_for_selector")
    if selector is not None and len(selector) > MAX_SELECTOR_LENGTH:
        _error(f"wait_for_selector must be at most {MAX_SELECTOR_LENGTH} characters.")
    return selector


def _country(args: dict[str, Any], name: str) -> str | None:
    value = args.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 2 or not value.isascii() or not value.isalpha():
        _error(f"{name} must be a two-letter country code.")
    return value.lower()


def _screenshot_capture(args: dict[str, Any]) -> str | bool:
    """Accept false, full, top, or WIDTHxHEIGHT with an optional -ZOOM."""
    value = args.get("screenshot")
    if value is None or value is False or value == "false":
        return False
    if value in ("full", "top"):
        return value
    match = _VIEWPORT.match(value) if isinstance(value, str) else None
    if match:
        width, height = int(match[1]), int(match[2])
        zoom = 100 if match[3] is None else int(match[3])
        if 100 <= width <= 3840 and 100 <= height <= 3840 and 25 <= zoom <= 300:
            return value
    _error(
        "screenshot must be false, full, top, or WIDTHxHEIGHT from 100 to 3840 pixels with "
        "an optional -ZOOM from 25 to 300, such as 1280x800 or 1920x1080-75."
    )


def _page_url(args: dict[str, Any]) -> str:
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        _error("url is required.")
    url = url.strip()
    if not is_safe_url(url):
        _error("url must be a safe absolute HTTP or HTTPS URL.")
    blocked = check_website_access(url)
    if blocked:
        _error(blocked.get("message") or "Website access blocked.")
    return url


def _shared(args: dict[str, Any], *, loading: bool, action: bool) -> dict[str, Any]:
    """Validate the shared controls and return them in the documented request order."""
    fields: dict[str, Any] = {}
    if loading:
        fields["browserRendering"] = _optional_boolean(args, "browser_rendering")
    fields["timeout"] = _integer(args, "timeout", 300, 1, MAX_TIMEOUT)
    if loading:
        fields["warmStart"] = _boolean(args, "warm_start", False)
        fields["blockResources"] = _boolean(args, "block_resources", False)
    fields["waitForSelector"] = _selector(args)
    if action:
        fields["action"] = _optional_text(args, "action")
    fields["geoCode"] = _country(args, "geo_code")
    fields["saveResult"] = _boolean(args, "save_result", True)
    fields["maxAge"] = _integer(args, "max_age", 0, 0, MAX_CACHE_AGE_MS)
    fields["tokenCap"] = _integer(args, "token_cap", None, 1)
    fields["maxRetries"] = _integer(args, "max_retries", None, 0)
    return fields


def _compact(params: dict[str, Any]) -> dict[str, Any]:
    """Leave unset optional fields off the wire."""
    return {key: value for key, value in params.items() if value is not None}


def encode(params: dict[str, Any]) -> dict[str, str]:
    """Serialize query values the way the MrScraper CLI and SDKs send them."""
    return {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in params.items()
    }


def build_page_request(service: str, args: dict[str, Any]) -> tuple[dict[str, str], int]:
    """Build Scrape HTML, Scrape Markdown, or Get screenshot GET query parameters."""
    check_options(service, args)
    url = _page_url(args)
    if service == "scrape_html":
        shared = _shared(args, loading=True, action=True)
        capture = _screenshot_capture(args)
        if capture is not False:
            # A screenshot needs a rendered page, so it always sends browserRendering=true.
            shared["browserRendering"] = True
        params = {"url": url, "html": True, **shared, "screenshot": capture}
    elif service == "scrape_markdown":
        params = {"url": url, "markdown": True, **_shared(args, loading=True, action=True)}
    elif service == "get_screenshot":
        params = {
            "url": url, "screenshot": "full", "browserRendering": True,
            **_shared(args, loading=False, action=False),
        }
    else:
        raise ValueError(f"Unsupported page service: {service}")
    params = _compact(params)
    return encode(params), params["timeout"] + TRANSPORT_GRACE_SECONDS


def build_json_request(
    args: dict[str, Any], base_url: str,
) -> tuple[str, dict[str, str], dict[str, str] | None, int]:
    """Scrape JSON uses GET unless the encoded URL exceeds 8,000 characters."""
    check_options("scrape_json", args)
    url = _page_url(args)
    prompt = args.get("prompt")
    if prompt is None:
        prompt = DEFAULT_JSON_PROMPT
    if not isinstance(prompt, str) or not prompt.strip():
        _error("prompt must be a non-empty string.")
    params = _compact({
        "url": url,
        "prompt": prompt,
        "agent": "general",
        "html": _boolean(args, "html", True),
        **_shared(args, loading=True, action=False),
        "screenshot": _boolean(args, "screenshot", False),
    })
    query = encode(params)
    timeout = params["timeout"] + TRANSPORT_GRACE_SECONDS
    if len(f"{base_url}?{urlencode(query)}") <= MAX_GET_URL_LENGTH:
        return "GET", query, None, timeout
    body = {key: query.pop(key) for key in ("url", "prompt", "agent")}
    return "POST", query, body, timeout


def build_brand_request(args: dict[str, Any]) -> tuple[dict[str, str], int]:
    """Scrape brand sends action, url, and bundle, then timeout, warmStart, and geoCode if set."""
    check_options("scrape_brand", args)
    params = _compact({
        "action": "brand-scraping",
        "url": _page_url(args),
        "bundle": "none",
        "timeout": _integer(args, "timeout", 300, 1, MAX_TIMEOUT),
        "warmStart": _boolean(args, "warm_start", False),
        "geoCode": _country(args, "geo_code"),
    })
    return encode(params), params["timeout"] + TRANSPORT_GRACE_SECONDS


def build_search_request(args: dict[str, Any]) -> tuple[dict[str, str], int]:
    check_options("web_search", args)
    query = args.get("query")
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
        _error("query must be 1 to 1000 characters.")
    params = _compact({
        "action": "websearch",
        "query": query.strip(),
        "country": _country(args, "country"),
        "numResults": _integer(args, "num_results", 10, 10, 100),
    })
    return encode(params), SEARCH_TIMEOUT
