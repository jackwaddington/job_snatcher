"""
Thin wrapper — delegates to src.llm_client which handles backend routing
(Claude, gaming-PC Ollama, or local Ollama based on GENERATOR_LLM config).
"""
from src.llm_client import generate

__all__ = ['generate']
