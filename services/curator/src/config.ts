import 'dotenv/config';

function required(key: string): string {
  const val = process.env[key];
  if (!val) throw new Error(`Missing required env var: ${key}`);
  return val;
}

function optional(key: string, fallback: string): string {
  return process.env[key] ?? fallback;
}

export const config = {
  port: parseInt(optional('CURATOR_PORT', '5005'), 10),
  databaseUrl: required('DATABASE_URL'),
  slackWebhookUrl: optional('SLACK_WEBHOOK_URL', ''),
  approvalTimeoutHours: parseInt(optional('APPROVAL_TIMEOUT_HOURS', '48'), 10),
  logLevel: optional('LOG_LEVEL', 'info'),
} as const;
