import axios from 'axios';
import { config } from './config';
import { JobApplication } from './db';

/**
 * Post a Slack message listing drafted jobs awaiting approval.
 * Each job gets a link to the curator approval endpoint.
 *
 * If SLACK_WEBHOOK_URL is not set, logs to console instead.
 */
export async function notifySlack(jobs: JobApplication[], baseUrl: string): Promise<void> {
  const blocks = jobs.map((job) => {
    const score = job.combined_match_score?.toFixed(2) ?? 'n/a';
    const approveUrl = `${baseUrl}/decide`;
    return {
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: [
          `*${job.job_title}* at *${job.company_name}*`,
          `Score: ${score} | <${job.job_url}|View posting>`,
          `\`POST ${approveUrl}\` with \`{"job_id":"${job.id}","decision":"approve"}\``,
        ].join('\n'),
      },
    };
  });

  const payload = {
    text: `${jobs.length} job application${jobs.length !== 1 ? 's' : ''} ready for review`,
    blocks: [
      {
        type: 'header',
        text: {
          type: 'plain_text',
          text: `Job Snatcher — ${jobs.length} draft${jobs.length !== 1 ? 's' : ''} awaiting approval`,
        },
      },
      ...blocks,
    ],
  };

  if (!config.slackWebhookUrl) {
    console.log('[curator] Slack not configured — draft notification:');
    console.log(JSON.stringify(payload, null, 2));
    return;
  }

  await axios.post(config.slackWebhookUrl, payload);
}
