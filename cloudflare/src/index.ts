import { Hono } from 'hono';
import { cors } from 'hono/cors';

type Bindings = {
  ASSETS: Fetcher;
  DB: D1Database;
};

const app = new Hono<{ Bindings: Bindings }>();

app.use('*', cors());

app.get('/health', (c) => {
  return c.json({
    status: 'ok',
    version: '0.1.0-cf',
    ave_enabled: false,
    evaluation_codename: 'berry-bison-yonder-cabin',
    runtime: 'cloudflare-workers',
  });
});

app.get('/v1/me', (c) => {
  return c.json({
    user: { id: 'usr_demo', name: 'Demo Operator', email: 'demo@escalate.my' },
    org: { id: 'org_aurora', name: 'Aurora Group' },
    workspace: { id: 'ws_aurora', name: 'Aurora Group' },
  });
});

// Fallback to static assets for the operator console
app.all('*', async (c) => {
  return c.env.ASSETS.fetch(c.req.raw);
});

export default app;
