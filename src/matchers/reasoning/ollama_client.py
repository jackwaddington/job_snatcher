"""
Ollama API client for the gaming PC.
"""
import json
import logging
import time

import requests

from src.metrics import gaming_pc_inference_latency

logger = logging.getLogger(__name__)


def generate(base_url: str, model: str, prompt: str, timeout: int = 300) -> str:
    """
    Call Ollama generate API and return the response text.
    Raises requests.HTTPError or TimeoutError on failure.
    """
    url = f"{base_url}/api/generate"
    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
    }

    start = time.time()
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    elapsed = time.time() - start

    gaming_pc_inference_latency.observe(elapsed)
    logger.info(f"Ollama response in {elapsed:.1f}s")

    return resp.json().get('response', '')


def parse_reasoning_response(raw: str) -> dict:
    """
    Parse the JSON response from the reasoning LLM.
    Falls back to safe defaults if parsing fails.
    """
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith('```'):
        lines = raw.split('\n')
        raw = '\n'.join(lines[1:-1])

    try:
        data = json.loads(raw)
        return {
            'fit_assessment': data.get('fit_assessment', ''),
            'top_3_reasons': data.get('top_3_reasons', []),
            'confidence': float(data.get('confidence', 0.0)),
            'concerns': data.get('concerns', ''),
        }
    except Exception as e:
        logger.warning(f"Failed to parse reasoning response: {e}\nRaw: {raw[:200]}")
        return {
            'fit_assessment': 'Unable to parse response',
            'top_3_reasons': [],
            'confidence': 0.0,
            'concerns': 'Parse error',
        }
