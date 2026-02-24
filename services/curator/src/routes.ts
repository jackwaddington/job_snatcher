import { FastifyInstance } from 'fastify';
import { getJob, getJobsByIds, getDraftedJobs, updateJobStatus } from './db';
import { notifySlack } from './slack';
import { curatorDecisions, curatorNotifications, registry } from './metrics';

export async function registerRoutes(app: FastifyInstance): Promise<void> {
  /**
   * GET /health
   * Liveness probe.
   */
  app.get('/health', async () => ({
    status: 'ok',
    service: 'curator',
  }));

  /**
   * GET /metrics
   * Prometheus scrape endpoint.
   */
  app.get('/metrics', async (_req, reply) => {
    reply.header('Content-Type', registry.contentType);
    return registry.metrics();
  });

  /**
   * POST /notify
   * Called by Airflow after generation is complete.
   * Sends Slack message with drafted jobs awaiting approval.
   *
   * Body: { job_ids: string[] }
   */
  app.post<{ Body: { job_ids: string[] } }>(
    '/notify',
    {
      schema: {
        body: {
          type: 'object',
          required: ['job_ids'],
          properties: {
            job_ids: { type: 'array', items: { type: 'string' } },
          },
        },
      },
    },
    async (req, reply) => {
      const { job_ids } = req.body;

      if (!job_ids.length) {
        return reply.code(400).send({ error: 'job_ids must not be empty' });
      }

      const jobs = await getJobsByIds(job_ids);
      if (!jobs.length) {
        return reply.code(404).send({ error: 'No jobs found for given IDs' });
      }

      const baseUrl = `${req.protocol}://${req.hostname}`;
      try {
        await notifySlack(jobs, baseUrl);
        curatorNotifications.labels('success').inc();
      } catch (err) {
        curatorNotifications.labels('failed').inc();
        app.log.error({ err }, 'Slack notification failed');
        // Non-fatal: return 200 so Airflow doesn't retry — drafts are in DB
      }

      return {
        notified: jobs.length,
        job_ids: jobs.map((j) => j.id),
      };
    },
  );

  /**
   * GET /approval-status/:job_id
   * Check the current status of a job application.
   */
  app.get<{ Params: { job_id: string } }>(
    '/approval-status/:job_id',
    async (req, reply) => {
      const job = await getJob(req.params.job_id);
      if (!job) {
        return reply.code(404).send({ error: 'Job not found' });
      }
      return {
        job_id: job.id,
        status: job.status,
        job_title: job.job_title,
        company_name: job.company_name,
        combined_match_score: job.combined_match_score,
      };
    },
  );

  /**
   * GET /drafts
   * List all jobs currently in 'drafted' status, ranked by score.
   * Convenience endpoint for manual review.
   */
  app.get('/drafts', async () => {
    const jobs = await getDraftedJobs();
    return {
      count: jobs.length,
      jobs: jobs.map((j) => ({
        job_id: j.id,
        job_title: j.job_title,
        company_name: j.company_name,
        job_url: j.job_url,
        combined_match_score: j.combined_match_score,
        location: j.location,
        salary_range: j.salary_range,
        cover_letter_preview: j.cover_letter_draft?.slice(0, 200) ?? null,
      })),
    };
  });

  /**
   * GET /drafts/:job_id
   * Full detail view of a specific drafted job including cover letter and CV variant.
   */
  app.get<{ Params: { job_id: string } }>(
    '/drafts/:job_id',
    async (req, reply) => {
      const job = await getJob(req.params.job_id);
      if (!job) {
        return reply.code(404).send({ error: 'Job not found' });
      }
      return job;
    },
  );

  /**
   * POST /decide
   * Human decision on a drafted job.
   *
   * Body: {
   *   job_id: string,
   *   decision: 'approve' | 'reject' | 'edit',
   *   cover_letter_final?: string   // required when decision = 'edit'
   * }
   *
   * Status transitions:
   *   approve → 'approved'  (cover_letter_draft becomes cover_letter_final)
   *   reject  → 'rejected'
   *   edit    → 'approved'  (cover_letter_final = provided text)
   */
  app.post<{
    Body: {
      job_id: string;
      decision: 'approve' | 'reject' | 'edit';
      cover_letter_final?: string;
    };
  }>(
    '/decide',
    {
      schema: {
        body: {
          type: 'object',
          required: ['job_id', 'decision'],
          properties: {
            job_id: { type: 'string' },
            decision: { type: 'string', enum: ['approve', 'reject', 'edit'] },
            cover_letter_final: { type: 'string' },
          },
        },
      },
    },
    async (req, reply) => {
      const { job_id, decision, cover_letter_final } = req.body;

      const job = await getJob(job_id);
      if (!job) {
        return reply.code(404).send({ error: 'Job not found' });
      }

      if (job.status !== 'drafted') {
        return reply.code(409).send({
          error: `Job is not in 'drafted' state (current: ${job.status})`,
        });
      }

      if (decision === 'edit' && !cover_letter_final) {
        return reply.code(400).send({
          error: "cover_letter_final is required when decision is 'edit'",
        });
      }

      let newStatus: string;
      let finalLetter: string | undefined;

      if (decision === 'approve') {
        newStatus = 'approved';
        finalLetter = job.cover_letter_draft ?? undefined;
      } else if (decision === 'edit') {
        newStatus = 'approved';
        finalLetter = cover_letter_final;
      } else {
        newStatus = 'rejected';
      }

      await updateJobStatus(job_id, newStatus, finalLetter);
      curatorDecisions.labels(decision).inc();

      app.log.info({ job_id, decision, newStatus }, 'Curator decision recorded');

      return {
        job_id,
        decision,
        new_status: newStatus,
        job_title: job.job_title,
        company_name: job.company_name,
      };
    },
  );
}
