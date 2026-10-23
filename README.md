# MrScraper for Hermes

A native Hermes plugin that calls the MrScraper HTTP API directly. It registers
three dedicated tools and the `mrscraper` provider for Hermes's standard
`web_search` and `web_extract` tools. It does not connect to an MCP server.

## Install or update

```bash
hermes plugins install mrscraper
hermes plugins enable mrscraper
```

The installer prompts for `MRSCRAPER_API_TOKEN` from the
[MrScraper dashboard](https://app.mrscraper.com). Hermes stores and resolves the
token through the active profile's secret scope. Start a new Hermes session after
enabling or updating the plugin to load its tool definitions.

For an existing catalog installation, use `hermes plugins update mrscraper` after
the catalog's reviewed pin has moved to version 2.0.0. The catalog installs an
exact reviewed commit; changing this repository alone does not update the live
catalog or existing installations.

## Three tools

| Tool | Purpose | Direct HTTP endpoint |
| --- | --- | --- |
| `mrscraper_scraper_api` | Retrieve HTML, Markdown, or a screenshot from a known page. | `POST https://api.mrscraper.com/` |
| `mrscraper_web_search` | Search Google using query text or a Google search URL. | `POST https://sync.scraper.mrscraper.com/api/google/serp/v2/sync` |
| `mrscraper_account` | Read subscription status, token usage, quota, and rate limits. | `GET https://api.app.mrscraper.com/api/v1/subscription-accounts` |

These operations follow the
[Python SDK](https://github.com/mrscraper-com/sdk-python)'s `scraper_api`,
`web_search`, and `account` methods. Successful native tool responses include
`status_code`, `data`, and filtered HTTP `headers`. Account data is an allowlisted
summary; API tokens, billing identifiers, and credential-bearing response headers
are excluded.

### Page retrieval

Call `mrscraper_scraper_api` with `url` and the page options required by the task:

```json
{
  "url": "https://example.com/article",
  "html": false,
  "markdown": true,
  "geo_code": "ID"
}
```

HTML defaults to enabled and Markdown to disabled. Omit `browser_rendering` for
automatic browser fallback; `true` forces rendering and `false` disables it.
A screenshot forces rendering. Real-device routing (`super`) defaults to `false`.
Other controls include `wait_for_selector`, `home_page`, `block_resources`,
`use_proxy`, `proxy_country`, `cookie_jar`, and target-page `headers`.

The page timeout defaults to 120 seconds and accepts 1–300 seconds; the HTTP
request allows 30 additional seconds. `max_retries` defaults to 3 and controls
server-side retries, with optional `token_cap`; HTTP requests are not retried
locally. `stream` requests a server stream but the plugin buffers the complete
response. URL safety and the active Hermes website policy are checked before
submitting a page request.

### Google search

```json
{
  "url": "Hermes Agent documentation",
  "region": "id",
  "language": "en",
  "page": 1
}
```

`url` accepts query text or a Google URL containing `q`. A URL's `gl`, `hl`, and
`start` parameters provide region, language, and page unless explicitly
overridden. The native tool defaults to `raw=false` and `format="json"`, so the
agent receives parsed results. This intentionally differs from the Python SDK's
legacy `raw=true` default. Set `raw=true` or `format="html"` for result-page HTML;
`raw` takes precedence. `render_js` defaults to `false`; the request timeout
defaults to 600 seconds.

### Account usage

Call `mrscraper_account` with `{}` to inspect usage before a larger task. Its
optional `timeout` defaults to 30 seconds. The response includes subscription
status, usage, limit, remaining tokens, usage percentage, rate limits, renewal
state, and basic account identity. It never returns the raw account record.
Unavailable rate-limit values remain `null` rather than being reported as zero.

## Standard Hermes web tools

Select MrScraper under **Web Search & Extract** in `hermes tools`, or configure
the active profile's `config.yaml`:

```yaml
web:
  search_backend: mrscraper
  extract_backend: mrscraper
```

`web_search` maps to the same Google search endpoint and `web_extract` maps to the
same page endpoint. Selecting the provider is optional for using the three
focused tools. Derive structured fields and listings from the returned page
content. For click/type/scroll workflows, use Hermes's interactive browser tools;
page retrieval does not create a persistent browser session.
The standard web tools report explicit upstream failures and missing page content
as errors, including when the API returns HTTP 200.

## Migration from 1.x

Version 2.0.0 replaces all 15 previous dedicated tools with the three names above.
Use `mrscraper_scraper_api` in place of `mrscraper_fetch_rendered_html`,
`mrscraper_web_search` in place of `mrscraper_search_google_serp`, and
`mrscraper_account` in place of `mrscraper_get_account_info`. Update saved prompts
and automations, then start a new session. The `mrscraper` provider name and
`MRSCRAPER_API_TOKEN` remain the same.

Managed crawler, extraction-job, scraper-run, and saved-result tools are no longer
registered. This plugin's surface follows the three SDK endpoints; manage other
MrScraper workflows in the dashboard.

The [hosted MCP server](https://docs.mrscraper.com/docs/getting-started/mcp-server)
is a separate connection using OAuth and server-provided `scraperAPI`,
`webSearch`, and `status` names. Installing this native plugin does not configure
MCP.

## Service requests

Page and search requests can consume paid MrScraper account tokens. Target URLs,
search queries, and supplied page options are sent to MrScraper's cloud service.
Authentication stays in Hermes's configured secrets; never put an API token in
a tool argument or example. The page endpoint requires the token query parameter
in addition to authentication headers; surfaced errors omit request URLs and
response bodies that could reveal credentials.

## Development

Use `hermes plugins validate .` for manifest/capability admission and the security
scan. Current Hermes admission reports a compatibility warning for the internal
URL-safety and website-policy helpers also used by version 1.x; the plugin retains
those checks and tests them against the target Hermes checkout. Run this repository's tests through a Hermes checkout's canonical runner:

```bash
/path/to/hermes-agent/scripts/run_tests.sh /path/to/hermes-mrscraper-plugin/tests/test_plugin.py -q --import-mode=importlib
```

The tests discover the plugin through a temporary `HERMES_HOME` and exercise its
tools and web provider against a local HTTP server. They require no live token or
billable MrScraper request.
