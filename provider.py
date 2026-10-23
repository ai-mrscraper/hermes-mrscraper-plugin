"""MrScraper adapter for Hermes' standard web search/extract tools."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from agent.web_search_provider import WebSearchProvider
from .client import MrScraperClient, MrScraperError, is_mrscraper_available


def _nested(value: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _serp_items(payload: Any) -> List[Mapping[str, Any]]:
    """Find the result list across currently observed SERP response envelopes."""
    candidates = (
        payload if isinstance(payload, list) else None,
        _nested(payload, "data") if isinstance(_nested(payload, "data"), list) else None,
        _nested(payload, "web"),
        _nested(payload, "data", "web"),
        _nested(payload, "data", "organic"),
        _nested(payload, "data", "organic_results"),
        _nested(payload, "organic"),
        _nested(payload, "organic_results"),
        _nested(payload, "results"),
    )
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, Mapping)]
    return []


def _rendered_content(payload: Any) -> tuple[str, str, Dict[str, Any]]:
    """Prefer REST page fields over an unrelated nested ``data`` object."""
    if isinstance(payload, str):
        if payload.strip():
            return payload, "", {}
        raise MrScraperError("MrScraper returned no page content.")
    if not isinstance(payload, Mapping):
        raise MrScraperError("MrScraper returned no page content.")

    nested = payload.get("data")
    candidates = (payload, nested) if isinstance(nested, Mapping) else (payload,)
    for data in candidates:
        if data.get("error") or data.get("success") is False:
            raise MrScraperError("MrScraper reported a page retrieval failure.")
        content = data.get("markdown") or data.get("html") or data.get("content")
        if isinstance(content, str) and content.strip():
            metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
            title = str(data.get("title") or metadata.get("title") or "")
            return content, title, dict(metadata)
    raise MrScraperError("MrScraper returned no page content.")


class MrScraperWebSearchProvider(WebSearchProvider):
    """Route Hermes web search and extraction through MrScraper."""

    @property
    def name(self) -> str:
        return "mrscraper"

    @property
    def display_name(self) -> str:
        return "MrScraper"

    def is_available(self) -> bool:
        return is_mrscraper_available()

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        try:
            payload = MrScraperClient().web_search({"url": query, "raw": False})["data"]
            if isinstance(payload, Mapping) and payload.get("success") is False:
                raise MrScraperError("MrScraper reported a search failure.")
            items = _serp_items(payload)[: max(1, int(limit))]
            web = []
            for position, item in enumerate(items, start=1):
                web.append({
                    "title": str(item.get("title") or item.get("name") or ""),
                    "url": str(item.get("url") or item.get("link") or ""),
                    "description": str(
                        item.get("description") or item.get("snippet") or ""
                    ),
                    "position": int(item.get("position") or position),
                })
            return {"success": True, "data": {"web": web}}
        except MrScraperError as exc:
            return {"success": False, "error": f"MrScraper search failed: {exc}"}

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        requested_format = str(kwargs.get("format") or "markdown").lower()
        for url in urls:
            try:
                payload = MrScraperClient().scraper_api({
                    "url": url,
                    "html": requested_format != "markdown",
                    "markdown": requested_format == "markdown",
                })["data"]
                content, title, metadata = _rendered_content(payload)
                results.append({
                    "url": url,
                    "title": title,
                    "content": content,
                    "raw_content": content,
                    "metadata": metadata,
                })
            except MrScraperError as exc:
                results.append({
                    "url": url,
                    "title": "",
                    "error": f"MrScraper extract failed: {exc}",
                })
        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "MrScraper",
            "badge": "paid",
            "tag": "Google search and page retrieval",
            "env_vars": [
                {
                    "key": "MRSCRAPER_API_TOKEN",
                    "prompt": "MrScraper API token",
                    "url": "https://app.mrscraper.com",
                }
            ],
        }
