"""
Prompt template for the reasoning matcher.
"""


def build_prompt(job_description: str, contact_info: str, career_goals: str,
                 employment_history: str, projects_summary: str,
                 tech_stack: str) -> str:
    return f"""You are a hiring advisor evaluating job fit for a candidate.

JOB POSTING:
{job_description}

CANDIDATE PROFILE:
{contact_info}

Career Goals:
{career_goals}

Employment History:
{employment_history}

Projects & Technical Work:
{projects_summary}

Technical Skills:
{tech_stack}

YOUR TASK:
Evaluate if this is a good fit for the candidate. Respond with ONLY valid JSON:
{{
  "fit_assessment": "[one sentence: is this a good fit?]",
  "top_3_reasons": [
    "[reason 1 with specific reference to candidate or job]",
    "[reason 2]",
    "[reason 3]"
  ],
  "confidence": 0.75,
  "concerns": "[any red flags or mismatches]"
}}

Be honest. A mediocre fit gets 0.4-0.6. A great fit gets 0.8+.
Respond with JSON only — no preamble, no explanation."""
