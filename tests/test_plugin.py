"""Standalone discovery, REST wire compatibility, and profile security contracts."""

from __future__ import annotations

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

import pytest

from agent.secret_scope import (
    is_multiplex_active,
    reset_secret_scope,
    set_multiplex_active,
    set_secret_scope,
)
from hermes_cli.plugins import PluginManager
from tools.registry import registry


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PAGE_URL = "https://93.184.216.34/article"
BLOCKED_URL = "https://93.184.216.35/private"
FILE_URL = "file:///srv/article.html"
SCOPED_TOKEN = "scope/token+key"
TOOL_NAMES = {
    "mrscraper_status", "mrscraper_scrape_html", "mrscraper_scrape_markdown",
    "mrscraper_get_screenshot", "mrscraper_scrape_brand", "mrscraper_scrape_json",
    "mrscraper_web_search",
}
SHARED_DEFAULTS = {"timeout": "300", "saveResult": "true", "maxAge": "0"}
LOADING_DEFAULTS = {"warmStart": "false", "blockResources": "false"}
REMOVED = (
    "super", "wait_until", "proxy_country", "proxy", "return_cookie", "markdown",
    "save_result", "token_cap",
)
STANDARD = {
    "url": "Absolute HTTP or HTTPS URL of the page to process.",
    "timeout": "Maximum seconds to wait for the scrape, from 1 to 330. The HTTP request allows 30 additional seconds.",
    "warm_start": "Whether to open the site's home page first to warm the session before loading the target URL.",
    "browser_rendering": "Whether to load the page in a browser: true always does and false never does. Omit it to load the page without a browser first and switch to a browser automatically if the request is blocked.",
    "max_age": "Return a cached result of the same request when it is newer than the selected age. A cached result costs the same tokens as the original scrape.",
    "screenshot_area": "Screenshot area to capture: full for the entire scroll height, top for the first viewport, or a WIDTHxHEIGHT viewport from 100 to 3840 pixels with an optional -ZOOM percent from 25 to 300, such as 1280x800 or 1920x1080-75.",
    "screenshot": "Screenshot to capture with the HTML: false for none, full for the entire page, top for the first viewport, or a WIDTHxHEIGHT viewport from 100 to 3840 pixels with an optional -ZOOM percent from 25 to 300, such as 1280x800 or 1920x1080-75. Setting a screenshot also sends browserRendering=true.",
    "query": "Search query text, trimmed before sending, containing 1 to 1000 characters.",
}


def _kind(query: dict, body: dict | None) -> str:
    action = query.get("action", [None])[0]
    if action == "websearch":
        return "search"
    if action == "brand-scraping":
        return "brand"
    if query.get("agent") == ["general"] or (body or {}).get("agent") == "general":
        return "json"
    if query.get("screenshot", ["false"])[0] in {"full", "top"}:
        return "screenshot"
    if query.get("markdown") == ["true"]:
        return "markdown"
    return "html"


@pytest.fixture
def installed_plugin(tmp_path, monkeypatch):
    """Use the external install path and actual HTTP, with no paid-service calls."""
    home = tmp_path / ".hermes"
    plugin_dir = home / "plugins" / "mrscraper"
    shutil.copytree(
        PLUGIN_ROOT,
        plugin_dir,
        ignore=shutil.ignore_patterns("tests", "__pycache__", ".git", ".pytest_cache"),
    )
    (home / "config.yaml").write_text(
        "plugins:\n  enabled: [mrscraper]\n"
        "security:\n  website_blocklist:\n    enabled: true\n"
        "    domains: ['93.184.216.35']\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("MRSCRAPER_API_TOKEN", "another-profile-token")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    was_multiplex = is_multiplex_active()
    set_multiplex_active(True)
    secret_scope = set_secret_scope({"MRSCRAPER_API_TOKEN": SCOPED_TOKEN})
    requests_seen = []
    http_timeouts = []
    json_type = "application/json; charset=utf-8"
    responses = {
        "html": (200, "<h1>Local page</h1>", "text/html; charset=utf-8"),
        "markdown": (200, "# Local page", "text/markdown; charset=utf-8"),
        "screenshot": (200, {
            "html": "<h1>Local page</h1>", "screenshot": "BASE64_PNG_DATA",
            "markdown": "# Local page",
        }, json_type),
        "brand": (200, {"data": {
            "job_id": "JOB_ID", "status": "succeeded", "url": PAGE_URL,
            "brand": {"name": "Fixture", "colors": {"text": "#222222"}}, "error": None,
        }, "message": "Brand completed"}, "application/json"),
        "json": (200, {"success": True, "data": [{"title": "Item", "price": "10.00"}],
                       "status": "Results ready", "html": "", "screenshot": ""},
                 "application/json"),
        "search": (200, {"success": True, "message": "Search completed", "data": [
            {"rank": 7, "title": "First", "url": PAGE_URL,
             "description": "First result", "source": "example.com"},
            {"rank": 8, "title": "Second", "url": "https://93.184.216.34/second"},
        ], "tokenUsage": 1}, json_type),
        "account": (200, {"message": "Account", "data": {
            "stripeStatus": "active", "tokenLimit": 100, "tokenUsage": 25,
            "stripeCustomerId": "billing-id", "apiToken": SCOPED_TOKEN,
            "subscriptionItem": {"name": "Plan"}, "scraperAllowance": {"remaining": 75},
            "user": {"name": "Fixture", "email": "fixture@example.com", "isVerified": True},
        }}, json_type),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            target = urlsplit(self.path)
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            query = parse_qs(target.query, keep_blank_values=True)
            body = json.loads(raw_body) if raw_body else None
            kind = "account" if target.path == "/account" else _kind(query, body)
            requests_seen.append({
                "method": self.command, "path": target.path, "kind": kind,
                "query": query, "flat": {key: values[0] for key, values in query.items()},
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "body": body,
            })
            status, payload, content_type = responses[kind]
            encoded = (payload if isinstance(payload, str) else json.dumps(payload)).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("X-Request-Id", "fixture-request")
            self.send_header("Set-Cookie", "session=private-cookie")
            self.send_header("Authorization", "Bearer private-response-token")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    manager = PluginManager()
    try:
        manager.discover_and_load()
        loaded = manager._plugins["mrscraper"]
        assert loaded.enabled and loaded.error is None
        module = loaded.module
        base_url = f"http://127.0.0.1:{server.server_port}"
        monkeypatch.setattr(module.client, "SCRAPER_API_URL", base_url + "/api")
        monkeypatch.setattr(module.client, "ACCOUNT_API_URL", base_url + "/account")
        real_request = module.client.requests.request

        def request_with_observed_timeout(*args, **kwargs):
            http_timeouts.append(kwargs["timeout"])
            return real_request(*args, **kwargs)

        monkeypatch.setattr(module.client.requests, "request", request_with_observed_timeout)
        yield SimpleNamespace(
            loaded=loaded, module=module, manager=manager,
            requests=requests_seen, timeouts=http_timeouts, responses=responses,
        )
    finally:
        manager.unload()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        reset_secret_scope(secret_scope)
        set_multiplex_active(was_multiplex)


def _call(plugin, name, arguments):
    return json.loads(registry.dispatch(name, arguments, scope=plugin.manager.scope_key))


def test_seven_tools_register_with_standard_schemas(installed_plugin):
    plugin = installed_plugin
    assert set(plugin.loaded.tools_registered) == set(plugin.loaded.manifest.provides_tools) == TOOL_NAMES
    schemas = {name: schema for name, schema, _handler in plugin.module.mrscraper_tools.MRSCRAPER_TOOLS}
    for name in TOOL_NAMES:
        assert registry.get_entry(name, scope=plugin.manager.scope_key).schema == schemas[name]
    params = {name: schema["parameters"]["properties"] for name, schema in schemas.items()}
    loading = ["browser_rendering", "timeout", "warm_start", "block_resources", "wait_for_selector"]
    cache = ["geo_code", "max_age", "max_retries"]
    assert params["mrscraper_status"] == {}
    assert list(params["mrscraper_scrape_html"]) == ["url", *loading, "action", *cache, "screenshot"]
    assert list(params["mrscraper_scrape_markdown"]) == ["url", *loading, "action", *cache]
    assert list(params["mrscraper_get_screenshot"]) == [
        "url", "screenshot", "timeout", "wait_for_selector", *cache,
    ]
    assert params["mrscraper_get_screenshot"]["screenshot"] == {
        "type": "string", "pattern": "^(full|top|[0-9]{3,4}x[0-9]{3,4}(-[0-9]{2,3})?)$",
        "default": "full", "description": STANDARD["screenshot_area"],
    }
    assert list(params["mrscraper_scrape_brand"]) == ["url"]
    assert list(params["mrscraper_scrape_json"]) == ["url", "prompt", "html", *loading, *cache, "screenshot"]
    assert list(params["mrscraper_web_search"]) == ["query", "country", "num_results"]
    for name in TOOL_NAMES:
        assert not set(REMOVED) & set(params[name]), name
    for name in ("mrscraper_scrape_html", "mrscraper_scrape_markdown", "mrscraper_scrape_json"):
        assert params[name]["warm_start"] == {
            "type": "boolean", "description": STANDARD["warm_start"], "default": False,
        }
    for name in ("mrscraper_scrape_html", "mrscraper_scrape_markdown", "mrscraper_scrape_json"):
        assert params[name]["browser_rendering"] == {
            "type": "boolean", "description": STANDARD["browser_rendering"],
        }
    for name in ("mrscraper_scrape_html", "mrscraper_scrape_markdown",
                 "mrscraper_get_screenshot", "mrscraper_scrape_json"):
        assert params[name]["url"]["description"] == STANDARD["url"]
        assert params[name]["timeout"] == {
            "type": "integer", "minimum": 1, "maximum": 330, "default": 300,
            "description": STANDARD["timeout"],
        }
        assert params[name]["max_age"] == {
            "type": "integer", "minimum": 0, "maximum": 604800000, "default": 0,
            "description": STANDARD["max_age"],
        }
        assert params[name]["wait_for_selector"]["maxLength"] == 500
        for optional in ("geo_code", "max_retries", "wait_for_selector"):
            assert "default" not in params[name][optional], (name, optional)
    capture = params["mrscraper_scrape_html"]["screenshot"]
    assert capture["type"] == "string" and capture["default"] == "false"
    assert capture["description"] == STANDARD["screenshot"]
    assert params["mrscraper_scrape_json"]["screenshot"] == {
        "type": "boolean", "description": "Whether to include a base64 screenshot in the response.",
        "default": False,
    }
    assert params["mrscraper_scrape_json"]["html"]["default"] is True
    assert "default" not in params["mrscraper_web_search"]["country"]
    assert params["mrscraper_web_search"]["query"]["description"] == STANDARD["query"]
    assert schemas["mrscraper_get_screenshot"]["description"] == (
        "Capture a base64 PNG screenshot of the full page, the first viewport, or a custom "
        "viewport. Browser rendering is always enabled."
    )
    assert schemas["mrscraper_scrape_markdown"]["description"] == (
        "Retrieve a page as clean Markdown. Browser rendering is optional."
    )


def test_page_tools_match_cli_wire_contract(installed_plugin):
    plugin = installed_plugin

    html = _call(plugin, "mrscraper_scrape_html", {"url": PAGE_URL})
    request = plugin.requests[-1]
    assert html["status_code"] == 200 and html["data"] == "<h1>Local page</h1>"
    assert request["method"] == "GET" and request["path"] == "/api" and request["body"] is None
    assert list(request["flat"].items()) == [
        ("url", PAGE_URL), ("html", "true"), ("markdown", "false"), ("timeout", "300"),
        ("warmStart", "false"), ("blockResources", "false"), ("saveResult", "true"),
        ("maxAge", "0"), ("screenshot", "false"),
    ]
    assert plugin.timeouts[-1] == 300 + 30

    target_url = PAGE_URL + "?q=a%2Bb&tag=café#section"
    _call(plugin, "mrscraper_scrape_html", {
        "url": target_url, "browser_rendering": False, "timeout": 330, "warm_start": True,
        "block_resources": True, "wait_for_selector": " body ", "action": " product-flow ",
        "geo_code": "ID", "max_age": 3600000, "max_retries": 0, "screenshot": "1920x1080-75",
    })
    # A screenshot sends browserRendering=true even when browser_rendering is false.
    assert list(plugin.requests[-1]["flat"].items()) == [
        ("url", target_url), ("html", "true"), ("markdown", "false"),
        ("browserRendering", "true"), ("timeout", "330"), ("warmStart", "true"),
        ("blockResources", "true"), ("waitForSelector", "body"), ("action", "product-flow"),
        ("geoCode", "id"), ("saveResult", "true"), ("maxAge", "3600000"),
        ("maxRetries", "0"), ("screenshot", "1920x1080-75"),
    ]
    assert plugin.timeouts[-1] == 330 + 30

    for rendering in (None, True, False):
        for capture in ("full", "top", "1280x800"):
            arguments = {"url": PAGE_URL, "screenshot": capture}
            if rendering is not None:
                arguments["browser_rendering"] = rendering
            _call(plugin, "mrscraper_scrape_html", arguments)
            flat = plugin.requests[-1]["flat"]
            assert flat["browserRendering"] == "true" and flat["screenshot"] == capture
            assert list(flat)[:4] == ["url", "html", "markdown", "browserRendering"]
        _call(plugin, "mrscraper_scrape_html", {
            "url": PAGE_URL, "screenshot": False,
            **({} if rendering is None else {"browser_rendering": rendering}),
        })
        flat = plugin.requests[-1]["flat"]
        assert flat.get("browserRendering") == (None if rendering is None else str(rendering).lower())
        assert flat["screenshot"] == "false"

    markdown = _call(plugin, "mrscraper_scrape_markdown", {"url": PAGE_URL})
    assert markdown["data"] == "# Local page"
    assert plugin.requests[-1]["flat"] == {
        "url": PAGE_URL, "markdown": "true", "html": "false", "screenshot": "false",
        **SHARED_DEFAULTS, **LOADING_DEFAULTS,
    }
    assert list(plugin.requests[-1]["flat"])[:4] == ["url", "markdown", "html", "screenshot"]
    _call(plugin, "mrscraper_scrape_markdown", {
        "url": PAGE_URL, "browser_rendering": True, "action": "docs", "max_age": 86400000,
    })
    assert list(plugin.requests[-1]["flat"].items()) == [
        ("url", PAGE_URL), ("markdown", "true"), ("html", "false"), ("screenshot", "false"),
        ("browserRendering", "true"), ("timeout", "300"), ("warmStart", "false"),
        ("blockResources", "false"), ("action", "docs"), ("saveResult", "true"),
        ("maxAge", "86400000"),
    ]

    screenshot = _call(plugin, "mrscraper_get_screenshot", {"url": PAGE_URL})
    assert screenshot["data"]["screenshot"] == "BASE64_PNG_DATA"
    assert list(plugin.requests[-1]["flat"].items()) == [
        ("url", PAGE_URL), ("screenshot", "full"), ("html", "false"), ("markdown", "false"),
        ("browserRendering", "true"), ("timeout", "300"), ("saveResult", "true"),
        ("maxAge", "0"),
    ]
    _call(plugin, "mrscraper_get_screenshot", {
        "url": PAGE_URL, "screenshot": "1280x800", "timeout": 60, "wait_for_selector": "#results",
        "geo_code": "DE", "max_retries": 1,
    })
    assert list(plugin.requests[-1]["flat"].items()) == [
        ("url", PAGE_URL), ("screenshot", "1280x800"), ("html", "false"), ("markdown", "false"),
        ("browserRendering", "true"), ("timeout", "60"), ("waitForSelector", "#results"),
        ("geoCode", "de"), ("saveResult", "true"), ("maxAge", "0"), ("maxRetries", "1"),
    ]
    assert plugin.timeouts[-1] == 60 + 30
    for area in ("full", "top", "1920x1080-75", "3840x3840-300", "100x100-25"):
        _call(plugin, "mrscraper_get_screenshot", {"url": PAGE_URL, "screenshot": area})
        assert list(plugin.requests[-1]["flat"].items())[:5] == [
            ("url", PAGE_URL), ("screenshot", area), ("html", "false"), ("markdown", "false"),
            ("browserRendering", "true"),
        ]

    for request in plugin.requests:
        assert "token" not in request["query"]
        assert not {"super", "waitUntil", "proxyCountry", "proxy", "returnCookie", "tokenCap"} & set(request["flat"])
        assert request["headers"]["x-api-token"] == SCOPED_TOKEN
        assert request["headers"]["authorization"] == f"Bearer {SCOPED_TOKEN}"
    for response in (html, markdown, screenshot):
        assert response["headers"].get("X-Request-Id", response["headers"].get("x-request-id")) == "fixture-request"
        assert not ({"set-cookie", "authorization", "x-api-token"} & {key.lower() for key in response["headers"]})


def test_status_brand_json_and_search_match_cli_wire_contract(installed_plugin):
    plugin = installed_plugin

    status = _call(plugin, "mrscraper_status", {})
    request = plugin.requests[-1]
    assert request["method"] == "GET" and request["path"] == "/account"
    assert request["body"] is None and not request["query"]
    assert plugin.timeouts[-1] == 600
    account = status["data"]["data"]
    assert account["tokenLimit"] == 100 and account["stripeCustomerId"] == "billing-id"
    assert account["subscriptionItem"] == {"name": "Plan"}
    assert "token_remaining" not in json.dumps(status)
    assert account["apiToken"] == "[REDACTED]" and SCOPED_TOKEN not in json.dumps(status)
    assert not ({"set-cookie", "authorization"} & {key.lower() for key in status["headers"]})

    brand = _call(plugin, "mrscraper_scrape_brand", {"url": PAGE_URL})
    assert list(plugin.requests[-1]["flat"].items()) == [
        ("action", "brand-scraping"), ("url", PAGE_URL), ("bundle", "none"),
    ]
    assert plugin.requests[-1]["method"] == "GET" and plugin.timeouts[-1] == 120
    assert brand["data"]["data"]["brand"]["name"] == "Fixture"

    extracted = _call(plugin, "mrscraper_scrape_json", {"url": PAGE_URL})
    assert plugin.requests[-1]["method"] == "GET" and plugin.requests[-1]["body"] is None
    assert list(plugin.requests[-1]["flat"].items()) == [
        ("url", PAGE_URL), ("prompt", "Extract all data as complete as possible."),
        ("agent", "general"), ("html", "true"), ("timeout", "300"), ("warmStart", "false"),
        ("blockResources", "false"), ("saveResult", "true"), ("maxAge", "0"),
        ("screenshot", "false"),
    ]
    assert plugin.timeouts[-1] == 330
    assert extracted["data"]["data"][0]["title"] == "Item"

    _call(plugin, "mrscraper_scrape_json", {
        "url": PAGE_URL, "html": False, "screenshot": True, "warm_start": True,
        "block_resources": True, "wait_for_selector": "body", "geo_code": "SG",
    })
    flat = plugin.requests[-1]["flat"]
    # Scrape JSON's boolean screenshot does not force browser rendering.
    assert "browserRendering" not in flat
    assert (flat["html"], flat["screenshot"], flat["warmStart"], flat["blockResources"]) == (
        "false", "true", "true", "true")
    assert (flat["waitForSelector"], flat["geoCode"]) == ("body", "sg")

    schema_prompt = "Extract every item. Json Schema: " + json.dumps(
        {"type": "array", "items": {"type": "object", "description": "x" * 9000}})
    _call(plugin, "mrscraper_scrape_json", {
        "url": PAGE_URL, "prompt": schema_prompt, "browser_rendering": True,
        "html": True, "screenshot": True, "timeout": 90, "max_retries": 2,
    })
    long_request = plugin.requests[-1]
    assert long_request["method"] == "POST"
    assert long_request["body"] == {"url": PAGE_URL, "prompt": schema_prompt, "agent": "general"}
    assert list(long_request["flat"].items()) == [
        ("html", "true"), ("browserRendering", "true"), ("timeout", "90"),
        ("warmStart", "false"), ("blockResources", "false"), ("saveResult", "true"),
        ("maxAge", "0"), ("maxRetries", "2"), ("screenshot", "true"),
    ]
    assert plugin.timeouts[-1] == 90 + 30

    searched = _call(plugin, "mrscraper_web_search", {
        "query": "  hermes agent  ", "country": "ID", "num_results": 100,
    })
    request = plugin.requests[-1]
    assert request["method"] == "GET" and request["body"] is None
    assert request["flat"] == {
        "action": "websearch", "query": "hermes agent", "country": "id", "numResults": "100",
    }
    assert plugin.timeouts[-1] == 120
    assert searched["data"]["data"][0]["title"] == "First"
    _call(plugin, "mrscraper_web_search", {"query": "café & tea"})
    assert plugin.requests[-1]["flat"] == {
        "action": "websearch", "query": "café & tea", "numResults": "10",
    }
    for request in plugin.requests:
        assert "token" not in request["query"]
        assert request["headers"]["x-api-token"] == SCOPED_TOKEN


def test_standard_web_provider_uses_search_and_page_services(installed_plugin):
    plugin = installed_plugin
    from agent.web_search_registry import get_provider

    provider = get_provider("mrscraper")
    assert provider.is_available() and provider.supports_search() and provider.supports_extract()
    assert provider.search("hermes agent", limit=1) == {
        "success": True, "data": {"web": [{
            "title": "First", "url": PAGE_URL, "description": "First result", "position": 7,
        }]},
    }
    assert plugin.requests[-1]["flat"] == {
        "action": "websearch", "query": "hermes agent", "numResults": "10",
    }
    provider.search("more results", limit=25)
    assert plugin.requests[-1]["flat"]["numResults"] == "25"
    provider.search("maximum results", limit=101)
    assert plugin.requests[-1]["flat"]["numResults"] == "100"

    extracted = provider.extract([PAGE_URL])
    assert extracted[0]["url"] == PAGE_URL
    assert extracted[0]["content"] == extracted[0]["raw_content"] == "# Local page"
    request = plugin.requests[-1]["flat"]
    assert (request["markdown"], request["html"], request["timeout"], request["maxRetries"]) == (
        "true", "false", "120", "3")
    as_html = provider.extract([PAGE_URL], format="html")
    assert as_html[0]["content"] == "<h1>Local page</h1>"
    assert (plugin.requests[-1]["flat"]["html"], plugin.requests[-1]["flat"]["markdown"]) == (
        "true", "false")

    plugin.responses["markdown"] = (200, {"data": {
        "markdown": "# Nested page", "title": "Nested page",
    }}, "application/json")
    nested = provider.extract([PAGE_URL])[0]
    assert nested["content"] == "# Nested page" and nested["title"] == "Nested page"


@pytest.mark.parametrize(("name", "options"), [
    ("mrscraper_status", {"timeout": 30}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "timeout": 331}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "timeout": 0}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "max_retries": -1}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "geo_code": "usa"}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "warm_start": "yes"}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "browser_rendering": "auto"}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "save_result": "false"}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "max_age": -1}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "max_age": 604800001}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "token_cap": 5}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "save_result": True}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "save_result": False}),
    ("mrscraper_scrape_json", {"url": PAGE_URL, "token_cap": 5}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "wait_for_selector": "a" * 501}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "action": " "}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "screenshot": True}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "screenshot": "middle"}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "screenshot": "99x800"}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "screenshot": "1280x800-301"}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "screenshot": "top", "browser_rendering": "no"}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "home_page": True}),
    ("mrscraper_scrape_html", {"url": PAGE_URL, "use_proxy": False}),
    *[("mrscraper_scrape_html", {"url": PAGE_URL, name: value}) for name, value in (
        ("super", True), ("wait_until", "load"), ("proxy_country", "sg"),
        ("proxy", "http://proxy.example.com:8080"), ("return_cookie", True), ("markdown", True),
    )],
    ("mrscraper_scrape_markdown", {"url": PAGE_URL, "html": True}),
    ("mrscraper_scrape_markdown", {"url": PAGE_URL, "screenshot": "top"}),
    *[(name, {"url": PAGE_URL, "screenshot": value})
      for name in ("mrscraper_scrape_html", "mrscraper_get_screenshot")
      for value in ("1280x800\n", " 1280x800", "1280x800 ", "\u0661\u0662\u0668\u0660x800",
                    "1280x800-75\n")],
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "screenshot": False}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "screenshot": True}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "screenshot": "false"}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "screenshot": "middle"}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "screenshot": "99x800"}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "screenshot": "1280x800-301"}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "browser_rendering": False}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "warm_start": True}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "html": False}),
    ("mrscraper_get_screenshot", {"url": PAGE_URL, "action": "flow"}),
    ("mrscraper_scrape_json", {"url": PAGE_URL, "prompt": "  "}),
    ("mrscraper_scrape_json", {"url": PAGE_URL, "action": "flow"}),
    ("mrscraper_scrape_json", {"url": PAGE_URL, "screenshot": "top"}),
    ("mrscraper_scrape_json", {"url": PAGE_URL, "html": "true"}),
    ("mrscraper_scrape_brand", {"url": PAGE_URL, "timeout": 60}),
    ("mrscraper_scrape_brand", {"url": PAGE_URL, "warm_start": False}),
    ("mrscraper_scrape_brand", {"url": PAGE_URL, "timeout": 0}),
    ("mrscraper_scrape_brand", {"url": PAGE_URL, "timeout": 331}),
    ("mrscraper_scrape_brand", {"url": PAGE_URL, "warm_start": "yes"}),
    ("mrscraper_scrape_brand", {"url": PAGE_URL, "geo_code": "usa"}),
    ("mrscraper_scrape_brand", {"url": PAGE_URL, "max_age": 0}),
    ("mrscraper_scrape_brand", {"url": PAGE_URL, "bundle": "full"}),
    ("mrscraper_web_search", {"query": "   "}),
    ("mrscraper_web_search", {"query": "x" * 1001}),
    ("mrscraper_web_search", {"query": "hermes", "num_results": 9}),
    ("mrscraper_web_search", {"query": "hermes", "num_results": 101}),
    ("mrscraper_web_search", {"query": "hermes", "num_results": True}),
    ("mrscraper_web_search", {"query": "hermes", "num_results": 10.5}),
    ("mrscraper_web_search", {"query": "hermes", "country": "indonesia"}),
    ("mrscraper_web_search", {"url": "hermes agent"}),
    ("mrscraper_web_search", {"query": "hermes", "region": "us"}),
    ("mrscraper_web_search", {"query": "hermes", "render_js": True}),
])
def test_invalid_or_removed_options_never_reach_transport(installed_plugin, name, options):
    result = _call(installed_plugin, name, options)
    assert result.get("error"), (name, options)
    assert not installed_plugin.requests


def test_validation_scope_and_error_redaction_precede_transport(installed_plugin):
    plugin = installed_plugin
    page_tools = (
        "mrscraper_scrape_html", "mrscraper_scrape_markdown", "mrscraper_get_screenshot",
        "mrscraper_scrape_brand", "mrscraper_scrape_json",
    )
    for name in page_tools:
        for url in (FILE_URL, "http://127.0.0.1/private",
                    "http://169.254.169.254/latest/meta-data", BLOCKED_URL, ""):
            result = _call(plugin, name, {"url": url})
            assert result.get("error"), (name, url)
    assert not plugin.requests

    from agent.web_search_registry import get_provider

    provider = get_provider("mrscraper")
    denied = provider.extract([FILE_URL, BLOCKED_URL])
    assert all(result.get("error") for result in denied)
    assert not plugin.requests

    calls = (
        ("account", "mrscraper_status", {}),
        ("html", "mrscraper_scrape_html", {"url": PAGE_URL}),
        ("markdown", "mrscraper_scrape_markdown", {"url": PAGE_URL}),
        ("screenshot", "mrscraper_get_screenshot", {"url": PAGE_URL}),
        ("brand", "mrscraper_scrape_brand", {"url": PAGE_URL}),
        ("json", "mrscraper_scrape_json", {"url": PAGE_URL}),
        ("search", "mrscraper_web_search", {"query": "hermes agent"}),
    )
    empty_scope = set_secret_scope({})
    try:
        assert not plugin.module.client.is_mrscraper_available()
        assert not provider.is_available()
        for _kind_name, name, arguments in calls:
            entry = registry.get_entry(name, scope=plugin.manager.scope_key)
            assert entry.check_fn() is False
            result = _call(plugin, name, arguments)
            assert "MRSCRAPER_API_TOKEN" in result["error"]
        assert not plugin.requests
    finally:
        reset_secret_scope(empty_scope)

    leaked_error = " ".join({SCOPED_TOKEN, quote(SCOPED_TOKEN, safe=""), quote_plus(SCOPED_TOKEN)})
    for kind, name, arguments in calls:
        plugin.responses[kind] = (403, {"message": leaked_error}, "application/json")
        result = _call(plugin, name, arguments)
        assert result.get("error") and result.get("status_code") == 403
        for secret in (SCOPED_TOKEN, quote(SCOPED_TOKEN, safe=""), "another-profile-token"):
            assert secret not in json.dumps(result)
    assert [request["kind"] for request in plugin.requests] == [kind for kind, _, _ in calls]

    plugin.responses["html"] = (401, {"message": "bad token"}, "application/json")
    unauthorized = _call(plugin, "mrscraper_scrape_html", {"url": PAGE_URL})
    assert "MRSCRAPER_API_TOKEN" in unauthorized["error"]

    plugin.responses["search"] = (200, {"success": False, "message": leaked_error}, "application/json")
    failed_search = provider.search("hermes agent")
    assert failed_search["success"] is False and failed_search.get("error")
    assert SCOPED_TOKEN not in json.dumps(failed_search)
    for payload in ({"error": leaked_error}, {"html": "", "markdown": "", "error": None}):
        plugin.responses["markdown"] = (200, payload, "application/json")
        failed_extract = provider.extract([PAGE_URL])[0]
        assert failed_extract.get("error") and "content" not in failed_extract
        assert SCOPED_TOKEN not in json.dumps(failed_extract)
