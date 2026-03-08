# llms_txt_generator

Generate an `llms.txt` file from a website by crawling pages, extracting metadata, and formatting output.

## Features

- FastAPI backend with simple web UI
- URL normalization and friendly validation messages
- Crawl settings: `max_depth`, `max_pages` (capped at 200)
- Async generation jobs with polling progress
- Failed-page reporting (without failing whole run)
- CLI support
- Download output as `{domain}-llms.txt`

## Tech Stack

- Python 3.10+
- FastAPI
- Pydantic
- BeautifulSoup4
- Uvicorn

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload
```

Open: `http://127.0.0.1:8000`

## CLI Usage

```bash
python3 cli.py example.com --max-depth 1 --max-pages 20
```

Save output to file:

```bash
python3 cli.py example.com --output llms.txt
```

## API Endpoints

- `GET /` - UI
- `POST /generate` - synchronous plain-text generation
- `POST /api/generate` - synchronous JSON generation
- `POST /api/generate/start` - start async job
- `GET /api/jobs/{job_id}` - poll async job status

## Project Structure

```text
.
├── main.py
├── cli.py
├── requirements.txt
├── schemas.py
├── core/
│   ├── errors.py
│   └── url_input.py
├── services/
│   ├── crawler.py
│   ├── extractor.py
│   ├── fetch_cache.py
│   ├── generator.py
│   └── http_fetcher.py
├── templates/
│   └── index.html
└── tests/
```

## Notes

- Crawling and extraction depend on target-site behavior (redirects, rate limits, bot protections).
- For deployment, a long-running container platform is usually a better fit than strict serverless for this workflow.
