import { Registry, Counter, Histogram } from 'prom-client';

export const registry = new Registry();

export const curatorDecisions = new Counter({
  name: 'curator_decisions_total',
  help: 'Total decisions made by curator',
  labelNames: ['decision'] as const,  // approve | reject | edit
  registers: [registry],
});

export const curatorNotifications = new Counter({
  name: 'curator_notifications_total',
  help: 'Total Slack notifications sent',
  labelNames: ['status'] as const,  // success | failed
  registers: [registry],
});

export const curatorRequestDuration = new Histogram({
  name: 'curator_request_duration_seconds',
  help: 'HTTP request duration in seconds',
  labelNames: ['method', 'route', 'status'] as const,
  buckets: [0.01, 0.05, 0.1, 0.5, 1, 2],
  registers: [registry],
});
