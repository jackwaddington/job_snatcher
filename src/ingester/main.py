"""
Ingester service — FastAPI app.
Runs on port 5001.

Start with:
    uvicorn src.ingester.main:app --port 5001 --reload
"""
import logging
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from prometheus_client import make_asgi_app
from starlette.routing import Mount

from src.ingester.ingester import ingest_job, DuplicateJobError, ParseError

logging.basicConfig(level='INFO')
logger = logging.getLogger(__name__)

app = FastAPI(title='Job Ingester', version='0.1.0')

# Expose /metrics endpoint for Prometheus scraping
metrics_app = make_asgi_app()
app.mount('/metrics', metrics_app)


# --- Request / Response models ---

class IngestRequest(BaseModel):
    job_url: str
    source: str = 'manual'


class IngestResponse(BaseModel):
    job_id: str
    job_title: str
    company_name: str
    job_url: str
    job_description: str | None
    required_skills: list[str]
    seniority_level: str | None
    location: str | None
    salary_range: str | None
    status: str
    source: str
    date_found: str
    created_at: str


# --- Routes ---

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'ingester'}


@app.post('/ingest', response_model=IngestResponse)
def ingest(req: IngestRequest):
    """
    Ingest a job posting from a URL.

    - 200: Job ingested successfully
    - 400: Invalid URL or parse failure
    - 409: Job already exists (idempotent)
    - 500: Network or database error
    """
    try:
        result = ingest_job(req.job_url, source=req.source)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            'error': 'Invalid URL',
            'details': str(e),
        })

    except DuplicateJobError as e:
        raise HTTPException(status_code=409, detail={
            'error': 'Job already exists',
            'job_id': e.job_id,
            'message': f'This job was already ingested on {e.date_found}',
        })

    except ParseError as e:
        raise HTTPException(status_code=400, detail={
            'error': 'Failed to parse job posting',
            'details': str(e),
            'job_url': req.job_url,
        })

    except requests.HTTPError as e:
        raise HTTPException(status_code=500, detail={
            'error': 'Failed to fetch job posting',
            'details': str(e),
            'job_url': req.job_url,
        })

    except Exception as e:
        logger.exception(f"Unexpected error ingesting {req.job_url}")
        raise HTTPException(status_code=500, detail={
            'error': 'Internal server error',
            'details': str(e),
        })
