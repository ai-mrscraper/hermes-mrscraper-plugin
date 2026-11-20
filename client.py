"""Direct HTTP adapter for the seven MrScraper services."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, quote_plus

import requests

from agent.secret_scope import get_secret
from .request_options import (
    STATUS_TIMEOUT,
    build_brand_request,
    build_json_request,
    build_page_request,
    build_search_request,
    check_options,
)

SCRAPER_API_URL = "https://api.mrscraper.com/"
ACCOUNT_API_URL = "https://api.app.mrscraper.com/api/v1/subscription-accounts"
_SENSITIVE_HEADERS = {
    "authorization", "proxy-authorization", "set-cookie", "set-cookie2", "x-api-token",
}


class MrScraperError(RuntimeError):
    """Invalid configuration or tool arguments."""


class MrScraperAPIError(MrScraperError):
    """An upstream request failed without exposing request credentials."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_mrscraper_token() -> str:
    token = (get_secret("MRSCRAPER_API_TOKEN", "") or "").strip()
    if not token:
        raise MrScraperError(
            "MRSCRAPER_API_TOKEN is required. Configure it when installing the plugin."
        )
    return token


def is_mrscraper_available() -> bool:
    return bool((get_secret("MRSCRAPER_API_TOKEN", "") or "").strip())


def _redact(value: Any, token: str) -> Any:
    if isinstance(value, str):
        for secret in {token, quote(token, safe=""), quote_plus(token)}:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {key: _redact(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, token) for item in value]
    return value


class MrScraperClient:
    """Synchronous adapter for MrScraper's REST API.

    Every method takes the tool's argument object and returns the common
    response envelope: ``status_code``, ``data``, and filtered ``headers``.
    """

    def __init__(self, token: str | None = None) -> None:
        self.token = get_mrscraper_token() if token is None else token.strip()
        if not self.token:
            raise MrScraperError("MRSCRAPER_API_TOKEN is required.")

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float,
    ) -> dict[str, Any]:
        try:
            response = requests.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "x-api-token": self.token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                params=params,
                json=body,
                timeout=timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            # Exception text can echo proxy credentials, cookies, and target headers.
            raise MrScraperAPIError(
                f"MrScraper request failed ({type(exc).__name__})."
            ) from None
        if not 200 <= response.status_code < 300:
            message = (
                "MrScraper authentication failed. Check MRSCRAPER_API_TOKEN."
                if response.status_code == 401
                else f"MrScraper API returned HTTP {response.status_code}."
            )
            raise MrScraperAPIError(message, status_code=response.status_code)
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type == "application/json" or content_type.endswith("+json"):
            try:
                data = response.json()
            except ValueError:
                raise MrScraperAPIError("MrScraper returned invalid JSON.") from None
        else:
            data = response.text
        return {
            "status_code": response.status_code,
            "data": _redact(data, self.token),
            "headers": {
                key: _redact(value, self.token)
                for key, value in response.headers.items()
                if key.lower() not in _SENSITIVE_HEADERS
            },
        }

    def status(self, args: dict[str, Any]) -> dict[str, Any]:
        check_options("status", args)
        return self._request("GET", ACCOUNT_API_URL, timeout=STATUS_TIMEOUT)

    def _page(self, service: str, args: dict[str, Any]) -> dict[str, Any]:
        params, timeout = build_page_request(service, args)
        return self._request("GET", SCRAPER_API_URL, params=params, timeout=timeout)

    def scrape_html(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._page("scrape_html", args)

    def scrape_markdown(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._page("scrape_markdown", args)

    def get_screenshot(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._page("get_screenshot", args)

    def scrape_brand(self, args: dict[str, Any]) -> dict[str, Any]:
        params, timeout = build_brand_request(args)
        return self._request("GET", SCRAPER_API_URL, params=params, timeout=timeout)

    def scrape_json(self, args: dict[str, Any]) -> dict[str, Any]:
        method, params, body, timeout = build_json_request(args, SCRAPER_API_URL)
        return self._request(method, SCRAPER_API_URL, params=params, body=body, timeout=timeout)

    def web_search(self, args: dict[str, Any]) -> dict[str, Any]:
        params, timeout = build_search_request(args)
        return self._request("GET", SCRAPER_API_URL, params=params, timeout=timeout)
