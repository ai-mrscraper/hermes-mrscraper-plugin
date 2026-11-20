"""Validate tool arguments and serialize the seven MrScraper service requests."""

from __future__ import annotations

from typing import Any, NoReturn
from urllib.parse import urlencode

from tools.url_safety import is_safe_url
from tools.website_policy import check_website_access

DEFAULT_JSON_PROMPT = "Extract all data as complete as possible."
WAIT_UNTIL_EVENTS = ("domcontentloaded", "load", "networkidle0", "networkidle2")
SCREENSHOT_AREAS = ("full", "top")
MAX_GET_URL_LENGTH = 8000
TRANSPORT_GRACE_SECONDS = 30
BRAND_AND_SEARCH_TIMEOUT = 120
STATUS_TIMEOUT = 600

_PAGE = (
    "url", "timeout", "geo_code", "proxy_country", "super", "wait_until",
    "proxy", "max_retries", "save_result",
)
_LOADING = ("block_resources", "wait_for_selector", "return_cookie")
SERVICE_OPTIONS: dict[str, tuple[str, ...]] = {
    "status": (),
    "scrape_html": _PAGE + _LOADING + ("browser_rendering", "warm_start"),
    "scrape_markdown": _PAGE + _LOADING + ("browser_rendering", "warm_start", "html"),
    "get_screenshot": _PAGE + _LOADING + ("warm_start", "screenshot", "html", "markdown"),
    "scrape_brand": ("url",),
    "scrape_json": _PAGE + ("prompt", "browser_rendering", "html", "screenshot"),
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


def _choice(args: dict[str, Any], name: str, choices: tuple[str, ...], default: str) -> str:
    value = args.get(name)
    if value is None:
        return default
    if value not in choices:
        _error(f"{name} must be one of: {', '.join(choices)}.")
    return value


def _country(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if value is None:
        return "us"
    if not isinstance(value, str) or len(value) != 2 or not value.isascii() or not value.isalpha():
        _error(f"{name} must be a two-letter country code.")
    return value.lower()


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


def _page_params(args: dict[str, Any], *, loading: bool) -> dict[str, Any]:
    params: dict[str, Any] = {
        "url": _page_url(args),
        "super": _boolean(args, "super", False),
        "waitUntil": _choice(args, "wait_until", WAIT_UNTIL_EVENTS, "domcontentloaded"),
        "timeout": _integer(args, "timeout", 300, 1, 300),
        "geoCode": _country(args, "geo_code"),
        "proxyCountry": _country(args, "proxy_country"),
        "saveResult": _boolean(args, "save_result", False),
    }
    proxy = _optional_text(args, "proxy")
    if proxy is not None:
        params["proxy"] = proxy
    max_retries = _integer(args, "max_retries", None, 0)
    if max_retries is not None:
        params["maxRetries"] = max_retries
    if loading:
        params["blockResources"] = _boolean(args, "block_resources", False)
        selector = _optional_text(args, "wait_for_selector")
        if selector is not None:
            params["waitForSelector"] = selector
        params["returnCookie"] = _boolean(args, "return_cookie", False)
    return params


def encode(params: dict[str, Any]) -> dict[str, str]:
    """Serialize query values the way the MrScraper CLI and SDKs send them."""
    return {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in params.items()
    }


def build_page_request(service: str, args: dict[str, Any]) -> tuple[dict[str, str], int]:
    """Build Scrape HTML, Scrape Markdown, or Get screenshot GET query parameters."""
    check_options(service, args)
    params = _page_params(args, loading=True)
    if service == "scrape_html":
        params.update(
            browserRendering=_boolean(args, "browser_rendering", False),
            warmStart=_boolean(args, "warm_start", False),
            html=True, markdown=False, screenshot=False,
        )
    elif service == "scrape_markdown":
        html = _boolean(args, "html", False)
        params.update(
            # The API needs browser rendering to return HTML and Markdown together.
            browserRendering=html or _boolean(args, "browser_rendering", False),
            warmStart=_boolean(args, "warm_start", False),
            html=html, markdown=True, screenshot=False,
        )
    elif service == "get_screenshot":
        params.update(
            browserRendering=True,
            warmStart=_boolean(args, "warm_start", False),
            screenshot=_choice(args, "screenshot", SCREENSHOT_AREAS, "full"),
            html=_boolean(args, "html", True),
            markdown=_boolean(args, "markdown", False),
        )
    else:
        raise ValueError(f"Unsupported page service: {service}")
    return encode(params), params["timeout"] + TRANSPORT_GRACE_SECONDS


def build_json_request(
    args: dict[str, Any], base_url: str,
) -> tuple[str, dict[str, str], dict[str, str] | None, int]:
    """Scrape JSON uses GET unless the encoded URL exceeds 8,000 characters."""
    check_options("scrape_json", args)
    prompt = args.get("prompt")
    if prompt is None:
        prompt = DEFAULT_JSON_PROMPT
    if not isinstance(prompt, str) or not prompt.strip():
        _error("prompt must be a non-empty string.")
    params = _page_params(args, loading=False)
    params.update(
        browserRendering=_boolean(args, "browser_rendering", False),
        html=_boolean(args, "html", False),
        screenshot=_boolean(args, "screenshot", False),
        agent="general",
        prompt=prompt,
    )
    query = encode(params)
    timeout = params["timeout"] + TRANSPORT_GRACE_SECONDS
    if len(f"{base_url}?{urlencode(query)}") <= MAX_GET_URL_LENGTH:
        return "GET", query, None, timeout
    body = {key: query.pop(key) for key in ("url", "prompt", "agent")}
    return "POST", query, body, timeout


def build_brand_request(args: dict[str, Any]) -> tuple[dict[str, str], int]:
    check_options("scrape_brand", args)
    params = {"action": "brand-scraping", "url": _page_url(args), "bundle": "none"}
    return encode(params), BRAND_AND_SEARCH_TIMEOUT


def build_search_request(args: dict[str, Any]) -> tuple[dict[str, str], int]:
    check_options("web_search", args)
    query = args.get("query")
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
        _error("query must be 1 to 1000 characters.")
    params = {
        "action": "websearch",
        "query": query.strip(),
        "country": _country(args, "country"),
        "numResults": _integer(args, "num_results", 10, 10, 100),
    }
    return encode(params), BRAND_AND_SEARCH_TIMEOUT
