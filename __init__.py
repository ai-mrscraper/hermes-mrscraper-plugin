"""MrScraper native HTTP API tools and web provider for Hermes."""

from .client import is_mrscraper_available
from .mrscraper_tools import MRSCRAPER_TOOLS
from .provider import MrScraperWebSearchProvider


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
