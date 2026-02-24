/**
 * Curator service — Fastify app.
 * Runs on port 5005.
 *
 * Human-in-the-loop approval gate for job applications.
 *
 * Start with:
 *   npm run dev          (development, hot-reload)
 *   npm run build && npm start  (production)
 */
import Fastify from 'fastify';
import sensible from '@fastify/sensible';
import { config } from './config';
import { registerRoutes } from './routes';
import { pool } from './db';

const app = Fastify({
  logger: {
    level: config.logLevel,
    transport:
      process.env.NODE_ENV !== 'production'
        ? { target: 'pino-pretty', options: { colorize: true } }
        : undefined,
  },
});

app.register(sensible);

async function start(): Promise<void> {
  try {
    await registerRoutes(app);

    await app.listen({ port: config.port, host: '0.0.0.0' });
    app.log.info(`Curator running on port ${config.port}`);
  } catch (err) {
    app.log.error(err);
    await pool.end();
    process.exit(1);
  }
}

const shutdown = async (signal: string): Promise<void> => {
  app.log.info(`${signal} received — shutting down`);
  await app.close();
  await pool.end();
  process.exit(0);
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

start();
