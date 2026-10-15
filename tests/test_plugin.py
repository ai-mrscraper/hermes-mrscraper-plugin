"""Standalone discovery, SDK wire compatibility, and profile security contracts."""

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
SCOPED_TOKEN = "scope/token+key"
TOOL_NAMES = {"mrscraper_scraper_api", "mrscraper_web_search", "mrscraper_account"}


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
    responses = {
        "/scraper": (200, {"data": {
            "markdown": "# Local page", "html": "<h1>Local page</h1>",
            "title": "Local page", "metadata": {"fixture": True},
        }}),
        "/search": (200, {"data": {"organic": [
            {"title": "First", "link": PAGE_URL, "snippet": "First result"},
            {"title": "Second", "link": "https://93.184.216.34/second"},
        ]}}),
        "/account": (200, {"data": {
            "stripeStatus": "active", "tokenLimit": "100", "tokenUsage": 25,
            "rateLimit": 10, "rateTtl": 60, "isAutoRenew": True,
            "stripeCustomerId": "private-billing-id", "apiToken": "private-root-token",
            "user": {"name": "Fixture", "email": "fixture@example.com",
                     "isVerified": True, "latestApiToken": "private-nested-token"},
        }}),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            target = urlsplit(self.path)
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            requests_seen.append({
                "method": self.command, "path": target.path,
                "query": parse_qs(target.query, keep_blank_values=True),
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "body": json.loads(raw_body) if raw_body else None,
            })
            status, payload = responses[target.path]
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
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
        for constant, path in (
            ("SCRAPER_API_URL", "/scraper"),
            ("WEB_SEARCH_API_URL", "/search"),
            ("ACCOUNT_API_URL", "/account"),
        ):
            monkeypatch.setattr(module.client, constant, base_url + path)
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


def test_external_tools_match_sdk_wire_and_preserve_standard_web_provider(installed_plugin):
    plugin = installed_plugin
    assert set(plugin.loaded.tools_registered) == set(plugin.loaded.manifest.provides_tools) == TOOL_NAMES
    schemas = {name: schema for name, schema, _handler in plugin.module.mrscraper_tools.MRSCRAPER_TOOLS}
    for name in TOOL_NAMES:
        assert registry.get_entry(name, scope=plugin.manager.scope_key).schema == schemas[name]

    scraped = _call(plugin, "mrscraper_scraper_api", {"url": PAGE_URL})
    default_request = plugin.requests[-1]
    assert scraped["status_code"] == 200
    assert scraped["data"]["data"]["title"] == "Local page"
    assert default_request["method"] == "POST"
    assert default_request["body"] == {"url": PAGE_URL, "maxRetries": 3}
    assert default_request["query"]["token"] == [SCOPED_TOKEN]
    assert default_request["query"]["timeout"] == ["120"]
    assert "browserRendering" not in default_request["query"]
    assert "super" not in default_request["query"]
    assert plugin.timeouts[-1] == 120 + 30

    _call(plugin, "mrscraper_scraper_api", {
        "url": PAGE_URL, "browser_rendering": False, "screenshot": True,
        "home_page": True, "html": False, "markdown": True,
        "timeout": 300, "max_retries": 0, "token_cap": 0,
        "headers": {"X-Target": "value"},
    })
    explicit_request = plugin.requests[-1]
    assert explicit_request["body"] == {"url": PAGE_URL, "maxRetries": 0, "tokenCap": 0}
    for key in ("browserRendering", "screenshot", "warmStart", "markdown"):
        assert explicit_request["query"][key] == ["true"]
    assert explicit_request["query"]["html"] == ["false"]
    assert json.loads(explicit_request["query"]["headers"][0]) == {"X-Target": "value"}
    assert plugin.timeouts[-1] == 300 + 30

    searched = _call(plugin, "mrscraper_web_search", {
        "url": "https://www.google.com/search?q=hermes+agent&gl=id&hl=id&start=20",
        "region": "sg",
    })
    search_request = plugin.requests[-1]
    assert search_request["path"] == "/search"
    assert search_request["body"] == {
        "query": "hermes agent", "region": "sg", "language": "id", "page": 3,
        "format": "json", "renderJs": False,
    }
    assert searched["data"]["data"]["organic"][0]["title"] == "First"

    account = _call(plugin, "mrscraper_account", {})
    account_request = plugin.requests[-1]
    assert account_request["method"] == "GET" and account_request["path"] == "/account"
    assert account_request["body"] is None and not account_request["query"]
    summary = account["data"]
    assert summary["token_remaining"] == summary["token_limit"] - summary["token_usage"]
    assert summary["usage_percent"] == summary["token_usage"] / summary["token_limit"] * 100
    assert summary["user"] == {"name": "Fixture", "email": "fixture@example.com", "verified": True}
    assert "private" not in json.dumps(account)
    for response in (scraped, searched, account):
        assert response["headers"].get("X-Request-Id", response["headers"].get("x-request-id")) == "fixture-request"
        assert not ({"set-cookie", "authorization", "x-api-token"} & {key.lower() for key in response["headers"]})
    for request in plugin.requests:
        assert request["headers"]["x-api-token"] == SCOPED_TOKEN
        assert request["headers"]["authorization"] == f"Bearer {SCOPED_TOKEN}"

    from agent.web_search_registry import get_provider

    provider = get_provider("mrscraper")
    assert provider.is_available() and provider.supports_search() and provider.supports_extract()
    assert provider.search("hermes agent", limit=1) == {
        "success": True, "data": {"web": [{
            "title": "First", "url": PAGE_URL, "description": "First result", "position": 1,
        }]},
    }
    extracted = provider.extract([PAGE_URL])
    assert extracted[0]["url"] == PAGE_URL and extracted[0]["title"] == "Local page"
    assert extracted[0]["content"] == extracted[0]["raw_content"] == "# Local page"
    assert plugin.requests[-1]["query"]["markdown"] == ["true"]


def test_validation_scope_and_error_redaction_precede_transport(installed_plugin):
    plugin = installed_plugin
    for arguments in (
        {"url": "file:///etc/passwd"},
        {"url": "http://127.0.0.1/private"},
        {"url": "http://169.254.169.254/latest/meta-data"},
        {"url": BLOCKED_URL},
        {"url": PAGE_URL, "timeout": 301},
        {"url": PAGE_URL, "max_retries": -1},
    ):
        result = _call(plugin, "mrscraper_scraper_api", arguments)
        assert result.get("error"), arguments
    assert not plugin.requests

    from agent.web_search_registry import get_provider

    provider = get_provider("mrscraper")
    denied = provider.extract(["file:///etc/passwd", BLOCKED_URL])
    assert all(result.get("error") for result in denied)
    assert not plugin.requests

    empty_scope = set_secret_scope({})
    try:
        assert not plugin.module.client.is_mrscraper_available()
        assert not provider.is_available()
        for name, arguments in (
            ("mrscraper_scraper_api", {"url": PAGE_URL}),
            ("mrscraper_web_search", {"url": "hermes agent"}),
            ("mrscraper_account", {}),
        ):
            entry = registry.get_entry(name, scope=plugin.manager.scope_key)
            assert entry.check_fn() is False
            result = _call(plugin, name, arguments)
            assert "MRSCRAPER_API_TOKEN" in result["error"]
        assert not plugin.requests
    finally:
        reset_secret_scope(empty_scope)

    leaked_error = " ".join({SCOPED_TOKEN, quote(SCOPED_TOKEN, safe=""), quote_plus(SCOPED_TOKEN)})
    for path, name, arguments in (
        ("/scraper", "mrscraper_scraper_api", {"url": PAGE_URL}),
        ("/search", "mrscraper_web_search", {"url": "hermes agent"}),
        ("/account", "mrscraper_account", {}),
    ):
        plugin.responses[path] = (403, {"message": leaked_error})
        result = _call(plugin, name, arguments)
        assert result.get("error")
        for secret in (SCOPED_TOKEN, quote(SCOPED_TOKEN, safe=""), "another-profile-token"):
            assert secret not in json.dumps(result)
    assert [request["path"] for request in plugin.requests] == ["/scraper", "/search", "/account"]
