import { Pool } from 'pg';
import { config } from './config';

export const pool = new Pool({ connectionString: config.databaseUrl });

export interface JobApplication {
  id: string;
  job_title: string;
  company_name: string;
  job_url: string;
  job_description: string | null;
  cover_letter_draft: string | null;
  cv_variant_generated: string | null;
  combined_match_score: number | null;
  cosine_match_score: number | null;
  reasoning_match_score: number | null;
  reasoning_explanation: string | null;
  status: string;
  date_found: string;
  location: string | null;
  salary_range: string | null;
}

export async function getJob(id: string): Promise<JobApplication | null> {
  const { rows } = await pool.query<JobApplication>(
    `SELECT id, job_title, company_name, job_url, job_description,
            cover_letter_draft, cv_variant_generated,
            combined_match_score, cosine_match_score, reasoning_match_score,
            reasoning_explanation, status, date_found, location, salary_range
     FROM job_applications
     WHERE id = $1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function getJobsByIds(ids: string[]): Promise<JobApplication[]> {
  if (ids.length === 0) return [];
  const placeholders = ids.map((_, i) => `$${i + 1}`).join(', ');
  const { rows } = await pool.query<JobApplication>(
    `SELECT id, job_title, company_name, job_url, job_description,
            cover_letter_draft, cv_variant_generated,
            combined_match_score, cosine_match_score, reasoning_match_score,
            reasoning_explanation, status, date_found, location, salary_range
     FROM job_applications
     WHERE id IN (${placeholders})
     ORDER BY combined_match_score DESC NULLS LAST`,
    ids,
  );
  return rows;
}

export async function updateJobStatus(
  id: string,
  status: string,
  coverLetterFinal?: string,
): Promise<void> {
  if (coverLetterFinal !== undefined) {
    await pool.query(
      `UPDATE job_applications
       SET status = $1, cover_letter_final = $2, updated_at = NOW()
       WHERE id = $3`,
      [status, coverLetterFinal, id],
    );
  } else {
    await pool.query(
      `UPDATE job_applications SET status = $1, updated_at = NOW() WHERE id = $2`,
      [status, id],
    );
  }
}

export async function getDraftedJobs(): Promise<JobApplication[]> {
  const { rows } = await pool.query<JobApplication>(
    `SELECT id, job_title, company_name, job_url, job_description,
            cover_letter_draft, cv_variant_generated,
            combined_match_score, cosine_match_score, reasoning_match_score,
            reasoning_explanation, status, date_found, location, salary_range
     FROM job_applications
     WHERE status = 'drafted'
     ORDER BY combined_match_score DESC NULLS LAST`,
  );
  return rows;
}
