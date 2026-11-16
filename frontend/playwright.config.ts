import { defineConfig, devices } from '@playwright/test'

const apiPort = process.env.GIVVI_E2E_API_PORT || '5000'
const webPort = process.env.GIVVI_E2E_WEB_PORT || '5173'
const externalServers = process.env.GIVVI_E2E_EXTERNAL_SERVERS === '1'

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: externalServers ? undefined : [
    {
      command: `GIVVI_AUTH_RATE_LIMIT=1000 GIVVI_APP_ORIGIN=http://127.0.0.1:${webPort} .venv/bin/flask --env-file .env.example --app givvi db-upgrade && GIVVI_AUTH_RATE_LIMIT=1000 GIVVI_APP_ORIGIN=http://127.0.0.1:${webPort} .venv/bin/flask --env-file .env.example --app givvi run --port ${apiPort} --no-reload`,
      cwd: '..',
      url: `http://127.0.0.1:${apiPort}/api/health/ready`,
      reuseExistingServer: !process.env.CI,
      timeout: 30000,
    },
    {
      command: `npm run dev -- --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: !process.env.CI,
      timeout: 30000,
    },
  ],
})
