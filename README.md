# MrScraper for Hermes

This standalone plugin adds MrScraper as a `web_search` and `web_extract`
provider and registers 15 `mrscraper_*` tools for SERP search, page rendering,
crawling, extraction, scraper runs, and result retrieval.

## Install

```bash
hermes plugins install ai-mrscraper/hermes-mrscraper-plugin
```

Configure `MRSCRAPER_API_TOKEN` when prompted, or store it in the active
Hermes profile's `.env` file. Then select MrScraper under Web Search in
`hermes tools`, or set:

```yaml
web:
  search_backend: mrscraper
  extract_backend: mrscraper
```

The rendered-page tool performs independent requests; MrScraper does not expose
a persistent CDP session for interactive `browser_*` actions.

The Playground API [documents a required `token` query parameter](https://docs.mrscraper.com/docs/api/playground/ai-parser), so rendered requests include it and the `x-api-token` header. The client redacts raw and URL-encoded token values from transport and API errors. The rendered tool defaults to a 120-second page timeout and permits an additional 30 seconds for the HTTP response.

## Development

Use `hermes plugins validate .` to check the manifest, registered capabilities,
and security scan. Tests use controlled HTTP responses and do not require an API
token or billable requests.
