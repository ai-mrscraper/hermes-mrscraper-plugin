"""MrScraper web provider and tools for Hermes."""

from __future__ import annotations

from .client import is_mrscraper_available
from .mrscraper_tools import MRSCRAPER_TOOLS
from .provider import MrScraperWebSearchProvider
from .rendered import MRSCRAPER_FETCH_RENDERED_HTML_SCHEMA, handle_fetch_rendered_html


def register(ctx) -> None:
    ctx.register_web_search_provider(MrScraperWebSearchProvider())
    for name, schema, handler in MRSCRAPER_TOOLS:
        ctx.register_tool(
            name=name,
            toolset="mrscraper",
            schema=schema,
            handler=handler,
            check_fn=is_mrscraper_available,
            requires_env=["MRSCRAPER_API_TOKEN"],
            emoji="🕷️",
        )
    ctx.register_tool(
        name="mrscraper_fetch_rendered_html",
        toolset="mrscraper",
        schema=MRSCRAPER_FETCH_RENDERED_HTML_SCHEMA,
        handler=handle_fetch_rendered_html,
        check_fn=is_mrscraper_available,
        requires_env=["MRSCRAPER_API_TOKEN"],
        emoji="🕸️",
    )
