// E2E for the Revenue Navigation UI (mvp/app/static). Two suites:
//   parity.spec.mjs : demo mode (?demo=1) must match prototype v9 pixel for pixel (no baselines: it renders
//                     the prototype file itself and diffs against it).
//   live.spec.mjs   : the real UI against the real API, with the mock LLM provider (no API key, deterministic).
// Run from mvp/e2e:  npm test   (starts uvicorn on :8765 by itself, or reuses a running one).
import { defineConfig } from '@playwright/test';

const PORT = Number(process.env.E2E_PORT || 8765);

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.mjs/,
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: [['list'], ['html', { outputFolder: 'report', open: 'never' }]],
  snapshotPathTemplate: '{testDir}/__screenshots__/{arg}{ext}',
  expect: { toHaveScreenshot: { maxDiffPixels: 40, animations: 'disabled', caret: 'hide' } },
  globalSetup: './global-setup.mjs',
  globalTeardown: './global-teardown.mjs',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1440, height: 900 },
    locale: 'en-GB',
    timezoneId: 'Asia/Jakarta',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `${process.env.E2E_PYTHON || ".venv/bin/python"} -m uvicorn app.main:app --port ${PORT}`,
    cwd: '..',
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
