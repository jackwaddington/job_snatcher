"""
Claude API prompt templates for cover letter and CV variant generation.
"""


def build_cover_letter_prompt(
    job_title: str,
    company_name: str,
    job_description: str,
    reasoning_explanation: str,
    narrative: str,
    employment_history: str,
    projects_summary: str,
    writing_style: str,
    contact_name: str,
) -> str:
    return f"""You are an expert cover letter writer. Write a compelling, authentic cover letter.

CANDIDATE INFORMATION:
Name: {contact_name}
Role: {job_title}
Company: {company_name}

JOB DESCRIPTION:
{job_description}

CANDIDATE PROFILE:
{narrative}

EMPLOYMENT HISTORY:
{employment_history}

PROJECTS:
{projects_summary}

WHY THIS FIT:
{reasoning_explanation}

WRITING STYLE GUIDE (write in the candidate's voice):
{writing_style}

YOUR TASK:
Write a 3-paragraph cover letter:
1. Opening: Why genuinely interested in this role (2-3 sentences). Use the candidate's signature philosophical/question-based style if appropriate.
2. Body: How specific experience matches their needs. Use ONE concrete STAR example from their history that aligns with the job description (3-4 sentences).
3. Closing: Call to action — enthusiasm, next steps (2 sentences). Sign off as the candidate naturally would.

REQUIREMENTS:
- Write in {contact_name}'s authentic voice as described in the writing style guide
- Be specific — reference actual skills/projects from their profile
- Mention the company/role by name
- Avoid clichés ("I'm a team player", "passionate about technology")
- 250-300 words total
- Output ONLY the cover letter text — no preamble, no formatting labels"""


def build_cv_variant_prompt(
    job_title: str,
    job_description: str,
    employment_history: str,
    projects_summary: str,
    tech_stack: str,
    contact_name: str,
) -> str:
    return f"""You are helping tailor a CV for a specific job application.

JOB: {job_title}
{job_description}

CANDIDATE: {contact_name}

EMPLOYMENT HISTORY:
{employment_history}

PROJECTS:
{projects_summary}

TECH STACK:
{tech_stack}

YOUR TASK:
Reorder and emphasise the candidate's experience to best match this job.
- Put the most relevant experience/projects first
- Call out specific skills from their profile that match the job requirements
- Keep all facts accurate — don't invent anything

Output a Markdown-formatted CV summary (not a full CV — just the relevant sections):
## Most Relevant Experience
[2-3 bullet points from employment history most relevant to this role]

## Most Relevant Projects
[2-3 projects most relevant to this role]

## Matching Skills
[Skills from their tech stack that directly match the job]"""
