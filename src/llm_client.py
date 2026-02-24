"""
Unified LLM client.

Routes generation to one of three backends based on GENERATOR_LLM config:

  claude         → Anthropic Claude API (requires CLAUDE_API_KEY)
  ollama_gaming  → Ollama on gaming PC  (OLLAMA_BASE_URL / OLLAMA_MODEL)
  ollama_local   → Ollama on this Mac   (LOCAL_OLLAMA_URL / LOCAL_OLLAMA_MODEL)

Auto-fallback: if GENERATOR_LLM=claude but no API key is set (or it's the
placeholder), quietly falls back to ollama_local so dev works without a key.
"""
import logging

import requests

from src import config

logger = logging.getLogger(__name__)

_claude_client = None


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        from anthropic import Anthropic
        _claude_client = Anthropic(api_key=config.CLAUDE_API_KEY)
    return _claude_client


def _generate_ollama(base_url: str, model: str, prompt: str, max_tokens: int) -> str:
    resp = requests.post(
        f'{base_url}/api/generate',
        json={
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {'num_predict': max_tokens},
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()['response']


def _key_is_set() -> bool:
    key = config.CLAUDE_API_KEY
    return bool(key) and key != 'your-key-here'


def generate(prompt: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
    """
    Generate text using the configured LLM backend.

    Reads GENERATOR_LLM at call time so you can change it without restarting.
    """
    backend = config.GENERATOR_LLM

    if backend == 'claude':
        if not _key_is_set():
            logger.warning(
                'GENERATOR_LLM=claude but CLAUDE_API_KEY is not set — '
                'falling back to ollama_local (%s, model=%s)',
                config.LOCAL_OLLAMA_URL,
                config.LOCAL_OLLAMA_MODEL,
            )
            backend = 'ollama_local'
        else:
            client = _get_claude_client()
            response = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{'role': 'user', 'content': prompt}],
            )
            logger.debug('Claude response: %d chars', len(response.content[0].text))
            return response.content[0].text

    if backend == 'ollama_gaming':
        logger.info(
            'LLM backend: gaming PC Ollama (%s, model=%s)',
            config.OLLAMA_BASE_URL,
            config.OLLAMA_MODEL,
        )
        return _generate_ollama(config.OLLAMA_BASE_URL, config.OLLAMA_MODEL, prompt, max_tokens)

    # ollama_local (default dev fallback)
    logger.info(
        'LLM backend: local Ollama (%s, model=%s)',
        config.LOCAL_OLLAMA_URL,
        config.LOCAL_OLLAMA_MODEL,
    )
    return _generate_ollama(config.LOCAL_OLLAMA_URL, config.LOCAL_OLLAMA_MODEL, prompt, max_tokens)
