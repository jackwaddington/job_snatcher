"""
Cosine Matcher service — FastAPI app.
Runs on port 5002.

Start with:
    uvicorn src.matchers.cosine.main:app --port 5002 --reload
"""
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import make_asgi_app

from src.matchers.cosine.matcher import match_jobs

logging.basicConfig(level='INFO')

app = FastAPI(title='Cosine Matcher', version='0.1.0')
app.mount('/metrics', make_asgi_app())


class MatchRequest(BaseModel):
    job_ids: list[str]


class MatchResult(BaseModel):
    job_id: str
    cosine_match_score: float


class MatchResponse(BaseModel):
    results: list[MatchResult]
    processed: int
    failed: int


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'cosine-matcher'}


@app.post('/match', response_model=MatchResponse)
def match(req: MatchRequest):
    """
    Score jobs against professional narrative using cosine similarity.
    Updates cosine_match_score in the database for each job.
    """
    if not req.job_ids:
        raise HTTPException(status_code=400, detail='job_ids must not be empty')

    try:
        results, failed = match_jobs(req.job_ids)
        return MatchResponse(
            results=[MatchResult(**r) for r in results],
            processed=len(results),
            failed=failed,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Matching failed: {e}')
