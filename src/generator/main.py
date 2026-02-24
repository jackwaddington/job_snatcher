"""
Generator service — FastAPI app.
Runs on port 5004.

Start with:
    uvicorn src.generator.main:app --port 5004 --reload
"""
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import make_asgi_app

from src.generator.main_logic import generate_applications

logging.basicConfig(level='INFO')

app = FastAPI(title='Application Generator', version='0.1.0')
app.mount('/metrics', make_asgi_app())


class GenerateRequest(BaseModel):
    job_ids: list[str]


class GenerateResult(BaseModel):
    job_id: str
    status: str


class GenerateResponse(BaseModel):
    results: list[GenerateResult]
    processed: int
    failed: int


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'generator'}


@app.post('/generate', response_model=GenerateResponse)
def generate(req: GenerateRequest):
    """
    Generate cover letter and CV variant for each job.
    Calls Claude API. Updates database with drafts and sets status='drafted'.
    """
    if not req.job_ids:
        raise HTTPException(status_code=400, detail='job_ids must not be empty')

    try:
        results, failed = generate_applications(req.job_ids)
        return GenerateResponse(
            results=[GenerateResult(**r) for r in results],
            processed=len(results),
            failed=failed,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Generation failed: {e}')
