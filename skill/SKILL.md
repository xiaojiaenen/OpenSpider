---
name: openspider
description: |
  Manage web scrapers through the OpenSpider platform. Use this skill when the user wants to create, run, stop, monitor, or export data from web scrapers. Also use when they mention crawling websites, scraping data, building spiders, automating data collection, or need to manage multiple scraping tasks. Even if they just say "I need to get data from this website" or "help me scrape X", this is the right skill.
---

# OpenSpider

OpenSpider is a spider management platform. It manages the full lifecycle of multiple scrapers — registration, start/stop, pause/resume, failure recovery, scheduling, data export — and exposes everything through a standard HTTP API.

Your job is to help the user create spider code, upload it to the platform, manage running spiders, and retrieve scraped data.

## Quick Reference

**API base**: `http://localhost:8000` (configurable)
**API docs**: `http://localhost:8000/docs`

## Core Workflow

When the user asks to scrape a website, follow this sequence:

1. **Analyze the target** — fetch the page, inspect its structure, identify what data to extract and what selectors to use. Check if the site uses JavaScript rendering, anti-bot protection, or non-UTF-8 encoding.
2. **Write the spider** — create a `.py` file that inherits `BaseSpider` and implements `run()`. Match the site's characteristics: use `use_stealth=True` for protected sites, set `encoding` for old sites with GBK/Big5, etc.
3. **Upload** — `POST /spiders/upload` with the `.py` file.
4. **Start** — `POST /spiders/{name}/start`.
5. **Monitor** — poll `GET /tasks?spider={name}` until status is `completed` or `failed`.
6. **Retrieve** — `GET /items?spider={name}` for data, `GET /tasks/{id}/logs` for errors.

## Writing Spider Code

All spiders inherit from `BaseSpider` and implement `async def run(self)`.

```python
from openspider.spiders.base import BaseSpider

class MySpider(BaseSpider):
    name = "my_spider"           # Required: unique identifier
    start_urls = ["https://..."] # Entry URLs

    async def run(self):
        page = await self.get(self.start_urls[0])
        for item in page.css(".article"):
            if self.should_stop:  # Check stop signal for graceful exit
                break
            yield {
                "title": item.css("h2::text").get(""),
                "link": item.css("a::attr(href)").get(""),
            }
```

The `run()` method is an async generator. Use `yield` to output scraped data items (dicts). Use `await self.get(url)` or `await self.post(url, data=...)` to fetch pages.

### Available Methods

| Method | What it does |
|--------|-------------|
| `await self.get(url, **kwargs)` | HTTP GET, returns a Scrapling Response object |
| `await self.post(url, **kwargs)` | HTTP POST, returns a Scrapling Response object |
| `self.should_stop` | Returns `True` if a stop signal was received |
| `self.session` | The underlying Scrapling session for advanced use |

### Lifecycle Hooks

| Hook | When it runs |
|------|-------------|
| `on_start(resuming=False)` | Before crawling begins. `resuming=True` if resuming from checkpoint. |
| `on_error(error)` | When an exception occurs during crawling. |
| `on_complete()` | After crawling finishes (success or failure). |
| `on_item_scraped(item) -> dict\|None` | Per-item post-processing. Return `None` to drop the item. |

### Key Configuration Attributes

These are class-level attributes you set on the spider class.

**Basic:**

| Attribute | Type | Default | Purpose |
|-----------|------|---------|---------|
| `name` | str | required | Unique spider identifier |
| `description` | str | `""` | Human-readable description |
| `start_urls` | list[str] | `[]` | Entry point URLs |
| `schedule` | str | `None` | Cron expression (e.g. `"0 */6 * * *"`) for scheduled runs |
| `max_retries` | int | `3` | Retry count on failure |
| `retry_delay` | int | `60` | Seconds between retries (exponential backoff applied) |
| `concurrent_requests` | int | `4` | Max parallel requests |
| `download_delay` | float | `0.5` | Seconds between requests |
| `proxies` | list[str] | `[]` | Proxy list |

**Anti-bot and browser:**

| Attribute | Type | Default | Purpose |
|-----------|------|---------|---------|
| `use_stealth` | bool | `False` | Use stealth browser mode (bypasses Cloudflare etc.) |
| `impersonate` | str | `"chrome"` | TLS fingerprint to impersonate (`chrome`/`firefox`/`safari`/`edge`) |
| `solve_cloudflare` | bool | `False` | Auto-solve Cloudflare challenges (needs `use_stealth=True`) |
| `block_webrtc` | bool | `False` | Block WebRTC to prevent IP leaks |
| `hide_canvas` | bool | `False` | Add canvas noise to prevent fingerprinting |
| `real_chrome` | bool | `False` | Use real Chrome instead of bundled Chromium |
| `block_ads` | bool | `False` | Block ~3500 ad/tracker domains |
| `capture_xhr` | str | `None` | Regex to capture XHR/fetch responses (for SPAs) |
| `max_pages` | int | `1` | Browser tab pool size for concurrent fetching |

**Site compatibility (for old/problematic sites):**

| Attribute | Type | Default | Purpose |
|-----------|------|---------|---------|
| `encoding` | str | `None` | Force encoding (e.g. `"gbk"`, `"big5"`, `"shift_jis"`) |
| `ssl_verify` | bool | `True` | Skip SSL verification for sites with bad certs |
| `timeout` | int | `30` | Request timeout in seconds |
| `default_headers` | dict | `{}` | Custom default headers |
| `cookies` | dict | `{}` | Pre-set cookies |
| `network_idle` | bool | `False` | Wait for network idle before returning (JS-heavy sites) |
| `wait_selector` | str | `None` | CSS selector to wait for before returning |
| `wait` | int | `0` | Extra wait time in ms after page load |

**Adaptive scraping:**

| Attribute | Type | Default | Purpose |
|-----------|------|---------|---------|
| `adaptive` | bool | `False` | Enable adaptive selectors — auto-relocate elements after site redesigns |

## Choosing the Right Mode

Use this decision tree when writing a spider:

- **Static HTML, no JS needed** → default mode (no special flags)
- **Content loaded by JavaScript** → `network_idle=True` or `wait_selector=".content"`
- **Anti-bot protection (Cloudflare, etc.)** → `use_stealth=True`, `solve_cloudflare=True`
- **SPA that loads data via API calls** → `capture_xhr=r"https://api\.example\.com/.*"` to intercept XHR
- **Old site with GBK/Big5 encoding** → `encoding="gbk"`
- **Site with expired SSL cert** → `ssl_verify=False`
- **Need to appear as real browser** → `use_stealth=True`, `real_chrome=True`, `block_webrtc=True`

## Template Spiders

For common crawling patterns, use these templates instead of writing from scratch:

### RuleSpider (follow links by pattern)

```python
from openspider.spiders.templates import RuleSpider
from scrapling.spiders import CrawlRule, LinkExtractor

class BlogCrawler(RuleSpider):
    name = "blog"
    start_urls = ["https://example.com"]

    def rules(self):
        return [
            CrawlRule(LinkExtractor(allow=r"/posts/"), callback=self.parse_post),
            CrawlRule(LinkExtractor(allow=r"/page/\d+/")),  # follow only, no callback
        ]

    async def parse_post(self, response):
        yield {"title": response.css("h1::text").get("")}
```

### SitemapRuleSpider (crawl from sitemap.xml)

```python
from openspider.spiders.templates import SitemapRuleSpider
from scrapling.spiders import CrawlRule, LinkExtractor

class ProductSitemap(SitemapRuleSpider):
    name = "products"
    sitemap_urls = ["https://shop.example.com/sitemap.xml"]

    def rules(self):
        return [
            CrawlRule(LinkExtractor(allow=r"/products/"), callback=self.parse_product),
        ]

    async def parse_product(self, response):
        yield {"name": response.css("h1::text").get(""), "price": response.css(".price::text").get("")}
```

## API Endpoints

### Spider Management

```
GET    /spiders                  # List all spiders
GET    /spiders/{name}           # Spider details
POST   /spiders/{name}/start     # Start spider
POST   /spiders/{name}/stop      # Stop spider
POST   /spiders/{name}/pause     # Pause spider (resumable)
DELETE /spiders/{name}           # Delete spider (stops first if running)
POST   /spiders/upload           # Upload spider .py file
```

### Tasks

```
GET    /tasks                    # Task list (?spider=&status=)
GET    /tasks/{id}               # Task details
GET    /tasks/{id}/logs          # Task logs
```

### Data

```
GET    /items                    # Query scraped data (?spider=&task_id=&page=&page_size=)
GET    /export/{name}            # Export data (?format=json|jsonl|csv)
```

### System

```
GET    /health                   # Health check (MySQL status, active spiders)
GET    /capabilities             # Full platform capability description (for AI integration)
```

## CLI Commands

```bash
openspider serve                  # Start API server + scheduler + file watcher
openspider list                   # List all registered spiders
openspider start <name>           # Start a spider
openspider stop <name>            # Stop a spider
openspider info <name>            # Show spider details
openspider add <file.py>          # Register a new spider file
openspider validate <file.py>     # Validate spider file without registering
```

## Helper Utilities

These utilities are available in `openspider/utils/` for use in spider code:

- **`openspider.utils.form`** — `extract_form_fields(response)`, `extract_hidden_fields(response)`, `extract_asp_viewstate(response)`, `merge_form_data(hidden, user_data)` — for ASP.NET/JSP/PHP form submissions
- **`openspider.utils.url`** — `strip_jsessionid(url)`, `resolve_url(base, relative)`, `normalize_url(url)` — URL manipulation
- **`openspider.utils.selector`** — `find_by_text(response, text)`, `find_by_regex(response, pattern)`, `find_similar(response, element)` — enhanced element finding beyond CSS/XPath
