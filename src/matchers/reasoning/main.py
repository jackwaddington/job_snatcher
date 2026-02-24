"""
Reasoning Matcher service — FastAPI app.
Runs on port 5003.

Start with:
    uvicorn src.matchers.reasoning.main:app --port 5003 --reload
"""
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import make_asgi_app

from src.matchers.reasoning.matcher import match_jobs

logging.basicConfig(level='INFO')

app = FastAPI(title='Reasoning Matcher', version='0.1.0')
app.mount('/metrics', make_asgi_app())


class ReasonRequest(BaseModel):
    job_ids: list[str]


class ReasonResult(BaseModel):
    job_id: str
    reasoning_match_score: float
    reasoning_explanation: str


class ReasonResponse(BaseModel):
    results: list[ReasonResult]
    processed: int
    failed: int


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'reasoning-matcher'}


@app.post('/reason', response_model=ReasonResponse)
def reason(req: ReasonRequest):
    """
    Run LLM reasoning on jobs. Only processes jobs with cosine_score >= 0.6.
    Wakes gaming PC via WoL if needed.
    """
    if not req.job_ids:
        raise HTTPException(status_code=400, detail='job_ids must not be empty')

    try:
        results, failed = match_jobs(req.job_ids)
        return ReasonResponse(
            results=[ReasonResult(**r) for r in results],
            processed=len(results),
            failed=failed,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Reasoning failed: {e}')
