# MrScraper for Hermes

MrScraper is an AI-powered **Web Fetch and Web Search platform designed to support
Business Intelligence, market research, competitive intelligence, and real-time
data retrieval**. Its services support business intelligence use cases such as
e-commerce price intelligence, competitor monitoring, hotel rate comparisons,
market trend analysis, real estate research, and structured data extraction.

This native Hermes plugin calls the MrScraper HTTP API directly and provides the
seven standard MrScraper services as dedicated tools. Tool and parameter
descriptions match the MrScraper CLI, Python SDK, Node SDK, LangChain integration,
and MCP server; see the [API Reference](https://docs.mrscraper.com/docs/api/overview).
Version 4.0.0 requires one secret, `MRSCRAPER_API_TOKEN`. The hosted MCP server is
a separate connection.

## Install or update

Install the reviewed catalog version:

```bash
hermes plugins install mrscraper
hermes plugins enable mrscraper
```

The installer prompts for `MRSCRAPER_API_TOKEN` from the
[MrScraper app](https://app.mrscraper.com/api-tokens). Hermes stores and resolves
the token through the active profile's secret scope. Start a new Hermes session
after enabling or updating the plugin to load its tool definitions.

For an existing catalog installation, use `hermes plugins update mrscraper`.
The [Hermes catalog listing](https://hermes-agent.nousresearch.com/docs/plugins/mrscraper)
shows the version and exact reviewed commit it installs. The catalog can lag
behind this repository's `main` branch: the seven tools described below require
version 4.0.0. Changing `main` does not change the reviewed catalog pin or
existing installations.

To install the current repository version directly on a profile without an
existing MrScraper installation, use the repository source instead:

```bash
hermes plugins install ai-mrscraper/hermes-mrscraper-plugin
hermes plugins enable mrscraper
```

This is a custom-source installation rather than the reviewed catalog release.
For a specific revision, add `--ref <full-40-character-commit-SHA>` to the install
command. Replacing an existing installation also requires `--force`. Start a new
Hermes session after either installation path.

### Check the connection

Run `hermes plugins list` to confirm MrScraper is installed and enabled. In a new
Hermes session, ask the agent to call `mrscraper_status` with `{}` first. Then
test `mrscraper_scrape_markdown` with:

```json
{
  "url": "https://example.com",
  "timeout": 60,
  "max_retries": 2
}
```

The returned Markdown should contain the Example Domain page. Test
`mrscraper_web_search` with `{"query":"example domain"}` and inspect
the returned titles and links. Page, brand, JSON, and search calls consume account
quota. Check the requested page's content as well as the response status; HTTP 200
alone does not establish that the expected page was retrieved.

## Seven tools

| Tool | Description | HTTP request |
| --- | --- | --- |
| `mrscraper_status` | Return the raw account status API response without summarizing, redacting body fields, or adding calculated fields. | `GET https://api.app.mrscraper.com/api/v1/subscription-accounts` |
| `mrscraper_scrape_html` | Retrieve the raw HTML of a page. Browser rendering is optional. | `GET https://api.mrscraper.com/` with `html=true` |
| `mrscraper_scrape_markdown` | Retrieve a page as Markdown. Including HTML also enables browser rendering and returns both outputs as JSON. | `GET https://api.mrscraper.com/` with `markdown=true` |
| `mrscraper_get_screenshot` | Capture a base64 screenshot of the full page or top viewport. Browser rendering is always enabled. | `GET https://api.mrscraper.com/` with `screenshot=full\|top` |
| `mrscraper_scrape_brand` | Extract a website's colors, typography, logos, and social links as JSON. | `GET https://api.mrscraper.com/` with `action=brand-scraping` |
| `mrscraper_scrape_json` | Extract structured JSON from a page using a natural-language prompt. Append Json Schema: and a JSON schema to shape the output. | `GET https://api.mrscraper.com/` with `agent=general` (POST above 8,000 URL characters) |
| `mrscraper_web_search` | Search the web and return ranked results with titles, URLs, descriptions, and sources. | `GET https://api.mrscraper.com/` with `action=websearch` |

Every request authenticates with `Authorization: Bearer` and `x-api-token`
headers from Hermes's configured secret. The token is never a tool argument and
is not placed in the request URL.

Successful tool responses use the common response envelope: `status_code`,
`data` (the API body: text for HTML or Markdown, JSON otherwise), and filtered
HTTP `headers`. Credential-bearing response headers are removed, and the
configured API token value is masked as `[REDACTED]` wherever a response echoes it.

## Parameters

Tool parameters use snake_case. The HTTP field each one sends is shown in
parentheses. Unsupported or misspelled options are rejected before any request is
made.

### Page controls

`mrscraper_scrape_html`, `mrscraper_scrape_markdown`, `mrscraper_get_screenshot`,
and `mrscraper_scrape_json` share these parameters:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `url` (`url`) | string | Required | Absolute HTTP or HTTPS URL of the page to process. |
| `timeout` (`timeout`) | integer | `300` | Page load timeout in seconds, from 1 to 300. The HTTP request allows 30 additional seconds. |
| `geo_code` (`geoCode`) | string | `"us"` | Two-letter country code to load the page from, sent in lowercase. |
| `proxy_country` (`proxyCountry`) | string | `"us"` | Two-letter country code of the proxy server, sent in lowercase. |
| `super` (`super`) | boolean | `false` | Whether to route the request through real devices. |
| `wait_until` (`waitUntil`) | string: `domcontentloaded`, `load`, `networkidle0`, `networkidle2` | `"domcontentloaded"` | Navigation completion event to wait for: domcontentloaded, load, networkidle0, or networkidle2. |
| `proxy` (`proxy`) | string | Omitted | Custom proxy URL used to load the page. |
| `max_retries` (`maxRetries`) | integer | Omitted | Maximum number of retries, as a nonnegative integer. Omit this parameter for no limit. |
| `save_result` (`saveResult`) | boolean | `false` | Whether to save the result to the dashboard Result tab. |

### Loading controls

`mrscraper_scrape_html`, `mrscraper_scrape_markdown`, and
`mrscraper_get_screenshot` also accept:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `block_resources` (`blockResources`) | boolean | `false` | Whether to block images, fonts, and stylesheets while loading the page. |
| `wait_for_selector` (`waitForSelector`) | string | Omitted | Wait for the page to contain the specified CSS selector before returning the result. |
| `return_cookie` (`returnCookie`) | boolean | `false` | Whether to include browser session cookies in the response. |

URL safety and the active Hermes website policy are checked before any page,
brand, or JSON request is submitted.

### Status

`mrscraper_status` takes no parameters: call it with `{}`. The HTTP deadline is
fixed at 600 seconds. The API body contains `message` and `data`; account details,
including `subscriptionItem` and `scraperAllowance`, are at `data.data` in the
response envelope.

### Scrape HTML

Page and loading controls, plus:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `browser_rendering` (`browserRendering`) | boolean | `false` | Whether to render the page in a browser before returning the result. |
| `warm_start` (`warmStart`) | boolean | `false` | Whether to enable warm start for more reliable scraping, at the cost of additional latency. |

```json
{"url": "https://example.com", "browser_rendering": true, "warm_start": true, "wait_for_selector": "body", "timeout": 120}
```

The default response body is HTML text. Additional controls can cause the API to
return JSON; the returned structure is preserved.

### Scrape Markdown

Page and loading controls, `browser_rendering`, `warm_start`, plus:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `html` (`html`) | boolean | `false` | Whether to include the page HTML in the response. |

```json
{"url": "https://example.com", "html": true, "warm_start": true}
```

The default response body is Markdown text. Enabling HTML returns JSON containing
both `html` and `markdown`.

### Get screenshot

Page and loading controls, plus:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `warm_start` (`warmStart`) | boolean | `false` | Whether to enable warm start for more reliable scraping, at the cost of additional latency. |
| `screenshot` (`screenshot`) | string: `full`, `top` | `"full"` | Screenshot area to capture: full for the entire page or top for the top viewport. |
| `html` (`html`) | boolean | `true` | Whether to include the page HTML in the response. |
| `markdown` (`markdown`) | boolean | `false` | Whether to include the page Markdown in the response. |

```json
{"url": "https://example.com", "screenshot": "top", "warm_start": true, "html": false, "markdown": true}
```

`browserRendering=true` is always sent. The response body contains a base64
`screenshot` and the requested page outputs. The API can still include HTML when
HTML output is disabled.

### Scrape brand

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `url` (`url`) | string | Required | Absolute HTTP or HTTPS URL of the page to process. |

The request sends `action=brand-scraping` and `bundle=none` with a fixed
120-second HTTP deadline; page controls are not accepted. Brand details are at
`data.data.brand` in the response envelope.

### Scrape JSON

Page controls (not loading controls), plus:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `prompt` (`prompt`) | string | `"Extract all data as complete as possible."` | Instructions describing the data to extract. Append Json Schema: and a JSON schema to shape the output. |
| `browser_rendering` (`browserRendering`) | boolean | `false` | Whether to render the page in a browser before returning the result. |
| `html` (`html`) | boolean | `false` | Whether to include the page HTML in the response. |
| `screenshot` (`screenshot`) | boolean | `false` | Whether to include a base64 screenshot in the response. |

```json
{
  "url": "https://example.com",
  "prompt": "Extract the first 2 items with title and price. Json Schema: {\"type\":\"array\",\"items\":{\"type\":\"object\",\"properties\":{\"title\":{\"type\":\"string\"},\"price\":{\"type\":\"string\"}},\"required\":[\"title\",\"price\"]}}",
  "browser_rendering": true
}
```

The request sends `agent=general`. When the encoded GET URL would exceed 8,000
characters, the plugin switches to POST and moves `url`, `prompt`, and `agent`
into the JSON body. Extraction results are in the API body's `data` field.

### Web search

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `query` (`query`) | string | Required | Search query text, trimmed before sending, containing 1 to 1000 characters. |
| `country` (`country`) | string | `"us"` | Two-letter country code to search from, sent in lowercase. |
| `num_results` (`numResults`) | integer | `10` | Number of search results to request, as an integer from 10 to 100. Fewer results may be returned. |

```json
{"query": "site:example.com documentation", "country": "id", "num_results": 20}
```

The request sends `action=websearch` with a fixed 120-second HTTP deadline. The
API body contains `success`, `message`, a `data` array, and `tokenUsage`; each
result includes `rank`, `title`, `url`, `description`, and `source`.

### Equivalent HTTP request

With `MRSCRAPER_API_TOKEN` exported in your shell, the Get screenshot example
above is equivalent to:

```bash
curl --get 'https://api.mrscraper.com/' \
  --data-urlencode 'url=https://example.com' \
  --data 'super=false&waitUntil=domcontentloaded&timeout=300&geoCode=us&proxyCountry=us' \
  --data 'saveResult=false&blockResources=false&returnCookie=false' \
  --data 'browserRendering=true&warmStart=true&screenshot=top&html=false&markdown=true' \
  --header "Authorization: Bearer ${MRSCRAPER_API_TOKEN}" \
  --header "x-api-token: ${MRSCRAPER_API_TOKEN}" \
  --header 'Accept: application/json' \
  --max-time 330
```

## Optional integration with Hermes's built-in web tools

Hermes provides built-in `web_search` and `web_extract` tools. This plugin can
optionally supply MrScraper as their backend through its `mrscraper` provider.
The seven dedicated `mrscraper_*` tools work without this provider selection.

Select MrScraper under **Web Search & Extract** in `hermes tools`, or configure
the active profile's `config.yaml`:

```yaml
web:
  search_backend: mrscraper
  extract_backend: mrscraper
```

With this provider selected, Hermes's `web_search` uses Web search: it requests
10–100 results, trims to Hermes's requested limit, and preserves the returned
rank. `web_extract` uses Scrape Markdown (or Scrape HTML when HTML is requested)
with a 120-second page timeout and at most 3 retries. Derive structured fields
and listings from the returned page content, or call `mrscraper_scrape_json`
directly. For click/type/scroll workflows, use Hermes's interactive browser tools;
page retrieval does not create a persistent browser session. The standard web
tools report explicit upstream failures and missing page content as errors,
including when the API returns HTTP 200.

## Migration from 3.x

Version 4.0.0 replaces the three 3.x tools with the seven standard services.
Update saved prompts and automations, then start a new Hermes session to refresh
tool schemas. The `mrscraper` provider name and `MRSCRAPER_API_TOKEN` stay the same.

| 3.x tool | 4.0.0 tool |
| --- | --- |
| `mrscraper_account` | `mrscraper_status`, which returns the raw account response instead of a calculated summary and takes no `timeout`. |
| `mrscraper_scraper_api` | `mrscraper_scrape_html`, `mrscraper_scrape_markdown`, or `mrscraper_get_screenshot`, depending on the output you need. |
| `mrscraper_web_search` | `mrscraper_web_search` with `query`, `country`, and `num_results` instead of `url` and `region`. Search URLs are no longer parsed. |
| — | New: `mrscraper_scrape_brand` and `mrscraper_scrape_json`. |

Page option changes:

- `home_page` is now `warm_start`. Get screenshot accepts it as well.
- `screenshot` is now a separate tool with a `full` or `top` area.
- The page timeout default is 300 seconds (was 120). `max_retries` is omitted by
  default, meaning no limit (was 3); set it explicitly for bounded retries.
- `geo_code` and `proxy_country` default to `us` and are sent in lowercase.
- `browser_rendering` defaults to `false` instead of automatic fallback.
- New: `wait_until`, `save_result`, and `return_cookie`.
- Removed: `use_proxy`, `bypass_proxy`, `cookie_jar`, `headers`, `token_cap`, and
  `stream`. They are rejected with an error that lists the supported options.
- The API token is no longer sent as a `token` query parameter; authentication
  uses headers only.

The [hosted MCP server](https://docs.mrscraper.com/docs/getting-started/mcp-server)
is a separate connection using OAuth and server-provided tool names. Installing
this native plugin does not configure MCP.

## Service requests

Page, brand, JSON, and search requests can consume paid MrScraper account quota.
Target URLs, prompts, search queries, and supplied options are sent to MrScraper's
cloud service. Authentication stays in Hermes's configured secrets; never put an
API token in a tool argument or example. Surfaced errors omit request URLs and
response bodies that could reveal credentials, proxy passwords, or cookies.

`mrscraper_status` returns the account record as the API sends it, which includes
account identity, plan, and usage fields. Use it when the agent needs that detail.

## Development

Use `hermes plugins validate .` for manifest/capability admission and the
security scan. Current Hermes admission reports a compatibility warning for the
internal website-policy helper also used by earlier versions; the plugin retains
that check and tests it against the target Hermes checkout. Run this repository's
tests through a Hermes checkout's canonical runner:

```bash
/path/to/hermes-agent/scripts/run_tests.sh /path/to/hermes-mrscraper-plugin/tests/test_plugin.py -q --import-mode=importlib
```

The tests discover the plugin through a temporary `HERMES_HOME` and exercise all
seven tools and the web provider against a local HTTP server. They require no live
token or billable MrScraper request.
