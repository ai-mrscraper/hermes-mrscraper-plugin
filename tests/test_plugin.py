"""Behavior checks for the standalone installation path."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

from hermes_cli.plugins import PluginManager


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_external_discovery_registers_provider_and_tools(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    plugin_dir = home / "plugins" / "mrscraper"
    shutil.copytree(PLUGIN_ROOT, plugin_dir, ignore=shutil.ignore_patterns("tests", "__pycache__", ".git"))
    (home / "config.yaml").write_text("plugins:\n  enabled: [mrscraper]\n")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("MRSCRAPER_API_TOKEN", "fixture-token")

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["mrscraper"]
    assert loaded.enabled and loaded.error is None
    assert set(loaded.tools_registered) == set(loaded.manifest.provides_tools)
    from agent.web_search_registry import get_provider

    assert get_provider("mrscraper").supports_extract()


def test_rendered_request_rejects_unsafe_url_and_redacts_token(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    plugin_dir = home / "plugins" / "mrscraper"
    shutil.copytree(PLUGIN_ROOT, plugin_dir, ignore=shutil.ignore_patterns("tests", "__pycache__", ".git"))
    (home / "config.yaml").write_text("plugins:\n  enabled: [mrscraper]\n")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("MRSCRAPER_API_TOKEN", "fixture-token")
    manager = PluginManager()
    manager.discover_and_load()
    module = manager._plugins["mrscraper"].module
    rendered = module.rendered
    client = module.client

    import pytest

    with pytest.raises(client.MrScraperError, match="safe HTTP or HTTPS"):
        rendered.build_rendered_request({"url": "file:///etc/passwd"})

    monkeypatch.setattr(rendered, "is_safe_url", lambda _url: True)
    params, body, timeout = rendered.build_rendered_request({"url": "https://example.com"})
    assert body["url"] == "https://example.com"
    assert timeout == 120

    observed = {}

    def request(method, url, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(ok=False, status_code=401, text="token=fixture-token", headers={})

    monkeypatch.setattr(client.requests, "request", request)
    with pytest.raises(client.MrScraperAPIError) as error:
        client.MrScraperClient().fetch_rendered(params=params, body=body, timeout=timeout)
    assert observed["headers"]["x-api-token"] == "fixture-token"
    assert observed["params"]["token"] == "fixture-token"
    assert "fixture-token" not in str(error.value)
