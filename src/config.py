import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
SRC_DIR = Path(__file__).parent

# Database
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'job_snatcher')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'changeme')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'job_snatcher_dev')

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# LLM — Claude (production)
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-opus-4-6')

# LLM — Ollama gaming PC (reasoning matcher)
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'neural-chat')

# LLM — Ollama local Mac (dev / cheap tasks)
LOCAL_OLLAMA_URL = os.getenv('LOCAL_OLLAMA_URL', 'http://localhost:11434')
LOCAL_OLLAMA_MODEL = os.getenv('LOCAL_OLLAMA_MODEL', 'llama3.2')

# Which backend to use for generation: claude | ollama_gaming | ollama_local
# Falls back to ollama_local if claude is selected but no API key is present.
GENERATOR_LLM = os.getenv('GENERATOR_LLM', 'claude')

# System
MATCH_SCORE_THRESHOLD = float(os.getenv('MATCH_SCORE_THRESHOLD', 0.65))
GAMING_PC_MAC_ADDRESS = os.getenv('GAMING_PC_MAC_ADDRESS')
GAMING_PC_IDLE_TIMEOUT = int(os.getenv('GAMING_PC_IDLE_TIMEOUT', 300))

# Notifications
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
