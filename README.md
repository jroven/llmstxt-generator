# llms_txt_generator

Generate an `llms.txt` Markdown file from a website by crawling internal pages, extracting metadata, and formatting output to the llms.txt-style structure.

## Features

- FastAPI backend with web UI (`templates/index.html`)
- CLI interface for local generation
- URL input normalization and friendly validation errors
- Pagination query normalization during crawl dedupe (`?page=...`, etc.)
- Crawl denylist for auth/account/system links and redirect-style query params
- Configurable crawl limits (`max_depth`, `max_pages`)
- Async job flow with polling status updates
- Failed-page reporting without failing the whole run
- Download filename auto-derived from source domain (editable in UI)
- Deterministic test suite (unit + integration, no live-network dependency)

## Architecture Overview

High-level flow:

1. User submits URL (UI or CLI)
2. Input URL is validated/normalized (`core/url_input.py`)
3. Pipeline attempts URL(s): `https://` first, optional `http://` fallback
4. Crawler discovers in-domain links with BFS (`services/crawler.py`)
5. Extractor parses title + meta description (`services/extractor.py`)
6. Generator builds final Markdown output (`services/generator.py`)
7. API returns output directly or through async job polling

Key modules:

- `api/`: FastAPI app wiring, routes, request schemas
- `services/`: crawler, extractor, generator, jobs, pipeline, fetch/cache
- `core/`: constants, error types, URL input handling
- `templates/`: frontend UI

## Requirements

- Python 3.10+
- `pip`
- macOS/Linux/WSL (or equivalent Python environment)

## Local Setup

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Run the app:

```bash
python3 -m uvicorn main:app --reload
```

Open:

- `http://127.0.0.1:8000`

## Usage

### Web UI

1. Enter a site URL (`example.com` or `https://example.com`)
2. Set `Max Depth` and `Max Pages`
3. Click `Generate`
4. Track progress in-stage (`resolving`, `crawling`, `extracting`, `generating`)
5. Copy output or download as a `.txt` file

### CLI

Print result to stdout:

```bash
python3 cli.py example.com --max-depth 1 --max-pages 20
```

Write result to file:

```bash
python3 cli.py example.com --max-depth 1 --max-pages 20 --output my-llms.txt
```

## API Endpoints

- `GET /`  
  UI page

- `GET /healthz`  
  Health check endpoint

- `POST /generate`  
  Form-based synchronous plain text response

- `POST /api/generate`  
  JSON synchronous generation

- `POST /api/generate/start`  
  Starts async job, returns `job_id`

- `GET /api/jobs/{job_id}`  
  Poll job status/results

Example async flow:

1. `POST /api/generate/start` with JSON payload:

```json
{
  "url": "https://example.com",
  "max_depth": 1,
  "max_pages": 20
}
```

2. Poll `GET /api/jobs/{job_id}` until `status` is `done` or `failed`

## Testing

Run all tests:

```bash
PYTHONPATH=. python3 -m pytest -q
```

Test structure:

- `tests/unit/`: focused unit tests for core/services
- `tests/integration/`: deterministic integration tests for pipeline + API

## Deployment

This app is easiest to deploy on a container-based platform (Render, Railway, Fly.io, etc.) because crawling/extraction jobs can run for tens of seconds.

### Basic container/process deployment

Start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Health check path:

- `/healthz`

### Vercel note

Serverless execution time limits can be restrictive for long crawl jobs. For this project, a long-running app process is usually a better fit than strict serverless functions.

## Project Structure

```text
.
├── api/
│   ├── app.py
│   ├── schemas.py
│   └── routes/
│       ├── generate.py
│       └── pages.py
├── core/
│   ├── constants.py
│   ├── errors.py
│   └── url_input.py
├── services/
│   ├── crawler.py
│   ├── extractor.py
│   ├── fetch_cache.py
│   ├── generator.py
│   ├── http_fetcher.py
│   ├── jobs.py
│   └── pipeline.py
├── templates/
│   └── index.html
├── tests/
│   ├── unit/
│   └── integration/
├── cli.py
├── main.py
├── schemas.py
└── requirements.txt
```
