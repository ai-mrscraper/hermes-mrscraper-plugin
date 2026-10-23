"""Validate tool arguments and serialize the Python SDK's HTTP contract."""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn
from urllib.parse import parse_qs, urlparse

from tools.url_safety import is_safe_url
from tools.website_policy import check_website_access


def _error(message: str) -> NoReturn:
    from .client import MrScraperError
    raise MrScraperError(message)


def _boolean(args: dict[str, Any], name: str, default: bool | None) -> bool | None:
    value = args.get(name, default)
    if value is None and default is None:
        return None
    if not isinstance(value, bool):
        _error(f"{name} must be a boolean.")
    return value


def _integer(args: dict[str, Any], name: str, default: int | None, minimum: int) -> int | None:
    value = args.get(name, default)
    if value is None and default is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _error(f"{name} must be an integer of at least {minimum}.")
    return value


def positive_timeout(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _error("timeout must be a positive finite number.")
    if not math.isfinite(value) or value <= 0:
        _error("timeout must be a positive finite number.")
    return float(value)


def _required_text(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} is required.")
    return value.strip()


def build_scraper_request(args: dict[str, Any]) -> tuple[dict, dict, int]:
    url = _required_text(args, "url")
    if not is_safe_url(url):
        _error("url must be a safe HTTP or HTTPS URL.")
    blocked = check_website_access(url)
    if blocked:
        _error(blocked.get("message") or "Website access blocked.")
    timeout = _integer(args, "timeout", 120, 1)
    if timeout > 300:
        _error("timeout must be between 1 and 300 seconds.")
    screenshot = _boolean(args, "screenshot", False)
    rendering = _boolean(args, "browser_rendering", None)
    headers = args.get("headers")
    if headers is not None and not isinstance(headers, (dict, str)):
        _error("headers must be a string or an object of string values.")
    if isinstance(headers, dict):
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items()):
            _error("headers must contain string values.")
        headers = json.dumps(headers)
    query = {
        "timeout": timeout,
        "geoCode": args.get("geo_code", "US"),
        "proxyCountry": args.get("proxy_country"),
        "browserRendering": True if screenshot else rendering,
        "super": True if _boolean(args, "super", False) else None,
        "useProxy": False if not _boolean(args, "use_proxy", True) else None,
        "proxy": args.get("proxy"),
        "html": _boolean(args, "html", True),
        "markdown": _boolean(args, "markdown", False),
        "waitForSelector": args.get("wait_for_selector"),
        "warmStart": True if _boolean(args, "home_page", False) else None,
        "screenshot": True if screenshot else None,
        "blockResources": True if _boolean(args, "block_resources", False) else None,
        "bypassProxy": True if _boolean(args, "bypass_proxy", False) else None,
        "cookieJar": args.get("cookie_jar"),
        "headers": headers,
        "stream": _boolean(args, "stream", None),
    }
    params = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in query.items() if value is not None
    }
    body = {"url": url, "maxRetries": _integer(args, "max_retries", 3, 0)}
    token_cap = _integer(args, "token_cap", None, 0)
    if token_cap is not None:
        body["tokenCap"] = token_cap
    return params, body, timeout


def build_search_request(args: dict[str, Any]) -> tuple[dict, float]:
    query = _required_text(args, "url")
    region, language, page = None, None, None
    parsed = urlparse(query)
    if parsed.scheme.lower() in {"http", "https"}:
        values = parse_qs(parsed.query)
        query = values.get("q", [""])[0].strip()
        if not query:
            _error("Google search URL must contain a q parameter.")
        region = values.get("gl", [None])[0]
        language = values.get("hl", [None])[0]
        try:
            start = int(values.get("start", [0])[0])
        except ValueError:
            start = 0
        page = start // 10 + 1 if start > 0 else None
    representation = args.get("format", "json")
    if representation not in {"json", "html"}:
        _error("format must be json or html.")
    body = {
        "query": query,
        "region": args.get("region") or region,
        "language": args.get("language") or language,
        "page": _integer(args, "page", None, 1) or page,
        "format": "html" if _boolean(args, "raw", False) else representation,
        "renderJs": _boolean(args, "render_js", False),
    }
    return {key: value for key, value in body.items() if value is not None}, positive_timeout(args.get("timeout", 600))
