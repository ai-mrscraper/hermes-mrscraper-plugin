"""Direct HTTP adapter for the three MrScraper Python SDK operations."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import quote, quote_plus

import requests

from agent.secret_scope import get_secret
from .request_options import build_scraper_request, build_search_request, positive_timeout

SCRAPER_API_URL = "https://api.mrscraper.com/"
WEB_SEARCH_API_URL = "https://sync.scraper.mrscraper.com/api/google/serp/v2/sync"
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


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return 0
    return number if math.isfinite(number) else 0


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


class MrScraperClient:
    """Synchronous adapter using the SDK's endpoints and wire representations."""

    def __init__(self, token: str | None = None) -> None:
        self.token = get_mrscraper_token() if token is None else token.strip()
        if not self.token:
            raise MrScraperError("MRSCRAPER_API_TOKEN is required.")

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
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
            # URLs can contain the API token, proxy passwords and target headers.
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
        if "application/json" in response.headers.get("Content-Type", "").lower():
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

    def scraper_api(self, args: dict[str, Any]) -> dict[str, Any]:
        params, body, timeout = build_scraper_request(args)
        return self._request(
            "POST", SCRAPER_API_URL,
            params={"token": self.token, **params}, body=body, timeout=timeout + 30,
        )

    def web_search(self, args: dict[str, Any]) -> dict[str, Any]:
        body, timeout = build_search_request(args)
        return self._request("POST", WEB_SEARCH_API_URL, body=body, timeout=timeout)

    def account(self, args: dict[str, Any]) -> dict[str, Any]:
        timeout = positive_timeout(args.get("timeout", 30))
        result = self._request("GET", ACCOUNT_API_URL, timeout=timeout)
        body = result["data"]
        details = body.get("data", body) if isinstance(body, dict) else body
        if not isinstance(details, dict):
            raise MrScraperAPIError(
                "Account response must contain an object.", status_code=result["status_code"]
            )
        usage = _number(details.get("tokenUsage"))
        limit = _number(details.get("tokenLimit"))
        user = details.get("user")
        user = user if isinstance(user, dict) else {}
        # Account responses also contain API tokens and billing identifiers.
        result["data"] = {
            "subscription_status": _string(details.get("stripeStatus")),
            "enterprise": bool(details.get("isEnterprise")),
            "token_usage": usage,
            "token_limit": limit,
            "token_remaining": max(0, limit - usage),
            "usage_percent": round(usage / limit * 100, 2) if limit > 0 else 0,
            "rate_limit": _number(details.get("rateLimit")),
            "rate_ttl": _number(details.get("rateTtl")),
            "auto_renew": bool(details.get("isAutoRenew")),
            "ends_at": _string(details.get("endsAt")),
            "user": {
                "name": _string(user.get("name")),
                "email": _string(user.get("email")),
                "verified": bool(user.get("isVerified")),
            },
        }
        return result
