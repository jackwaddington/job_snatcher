"""
Fetch public GitHub repos and summarise them using the configured LLM backend.
Writes output to assets/projects_summary.json.

Usage:
    python -m scripts.fetch_github_projects           # uses GENERATOR_LLM backend
    python -m scripts.fetch_github_projects --no-llm  # use GitHub descriptions only (no LLM)

LLM backend is controlled by GENERATOR_LLM in .env:
    claude         → Claude API (requires CLAUDE_API_KEY)
    ollama_local   → local Ollama (default dev fallback)
    ollama_gaming  → gaming PC Ollama

Requires:
    - assets/contact_info.json with a "github" field (full URL or username)
"""
import json
import re
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
CONTACT_INFO_PATH = BASE_DIR / "assets" / "contact_info.json"
OUTPUT_PATH = BASE_DIR / "assets" / "projects_summary.json"

GITHUB_API = "https://api.github.com"


def get_github_username(github_url: str) -> str:
    match = re.search(r"github\.com/([^/]+)", github_url)
    return match.group(1) if match else github_url.strip("/")


def fetch_repos(username: str) -> list[dict]:
    url = f"{GITHUB_API}/users/{username}/repos"
    params = {"sort": "updated", "per_page": 30, "type": "public"}
    headers = {"Accept": "application/vnd.github+json"}

    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_readme(username: str, repo_name: str) -> str | None:
    url = f"{GITHUB_API}/repos/{username}/{repo_name}/readme"
    headers = {"Accept": "application/vnd.github.raw+json"}

    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text[:3000]


def build_prompt(username: str, repos: list[dict]) -> str:
    repo_text = ""
    for repo in repos:
        repo_text += f"\n---\nRepo: {repo['name']}\n"
        repo_text += f"Description: {repo.get('description') or 'None'}\n"
        repo_text += f"Language: {repo.get('language') or 'None'}\n"
        repo_text += f"Topics: {', '.join(repo.get('topics', [])) or 'None'}\n"
        repo_text += f"Stars: {repo.get('stargazers_count', 0)}\n"
        if repo.get("readme"):
            repo_text += f"README (excerpt):\n{repo['readme']}\n"

    return f"""You are summarising GitHub repos for a CV/job application system.

Here are the public repos for GitHub user '{username}':

{repo_text}

For each repo, return a JSON array. Each item should have:
- "name": repo name exactly as shown
- "description": 1-2 sentence summary of what it does and why it exists (write this clearly for a recruiter, not just a developer)
- "technologies": list of languages, frameworks, tools used (infer from language, topics, README)
- "github_url": "https://github.com/{username}/<name>"
- "topics": list of topics from the repo (empty list if none)
- "stars": integer star count

Skip repos that are: forks of other projects, empty repos with no description or README, or clearly just coursework clones with no original work.

Return ONLY valid JSON — an array of objects, nothing else."""


def summarise_with_llm(username: str, repos: list[dict]) -> list[dict]:
    """Summarise repos using the configured LLM backend (see src/llm_client.py)."""
    from src.llm_client import generate

    prompt = build_prompt(username, repos)
    raw = generate(prompt, max_tokens=2000, temperature=0.3)

    # Strip markdown code fences if the model wrapped the JSON
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def summarise_no_llm(username: str, repos: list[dict]) -> list[dict]:
    """
    Build project entries directly from GitHub metadata — no LLM call.
    Useful for dev/testing when no LLM is available.
    """
    print("--no-llm: using GitHub descriptions directly (no LLM call)")
    projects = []
    for repo in repos:
        projects.append({
            "name": repo["name"],
            "description": repo.get("description") or f"A project by {username}.",
            "technologies": [repo["language"]] if repo.get("language") else [],
            "github_url": repo["html_url"],
            "topics": repo.get("topics", []),
            "stars": repo.get("stargazers_count", 0),
        })
    return projects


def main():
    no_llm = "--no-llm" in sys.argv

    if not CONTACT_INFO_PATH.exists():
        print("ERROR: assets/contact_info.json not found.")
        return

    contact = json.loads(CONTACT_INFO_PATH.read_text())
    github_field = contact.get("github", "").strip()
    if not github_field:
        print("ERROR: 'github' field is empty in assets/contact_info.json")
        return

    username = get_github_username(github_field)
    print(f"Fetching repos for: {username}")

    repos = fetch_repos(username)
    print(f"Found {len(repos)} public repos")

    print("Fetching READMEs...")
    for repo in repos:
        if not repo.get("fork"):
            repo["readme"] = fetch_readme(username, repo["name"])

    repos = [r for r in repos if not r.get("fork")]
    print(f"Processing {len(repos)} non-fork repos")

    if no_llm:
        projects = summarise_no_llm(username, repos)
    else:
        from src import config
        print(f"Summarising with LLM (backend: {config.GENERATOR_LLM})...")
        projects = summarise_with_llm(username, repos)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_username": username,
        "projects": projects,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"Written {len(projects)} projects to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
