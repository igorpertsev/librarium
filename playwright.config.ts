import { defineConfig, devices } from '@playwright/test';

// Browser tests against the throwaway stack from e2e/docker-compose.yml (`pnpm e2e:stack`).
// Playwright starts the Vite dev server itself, pointed at that backend.
const PORT = 4173;
export const E2E_API_URL = 'http://localhost:8100/api/v1';

export default defineConfig({
  testDir: 'e2e/tests',
  // The tests share one database (orders, settings), so they run one at a time.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  timeout: 60_000,
  use: {
    baseURL: `http://localhost:${PORT}`,
    locale: 'en-US',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      // PLAYWRIGHT_CHANNEL=chrome uses the installed Google Chrome instead of downloading one.
      use: { ...devices['Desktop Chrome'], channel: process.env.PLAYWRIGHT_CHANNEL || undefined },
    },
  ],
  webServer: {
    command: `pnpm exec vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    env: { VITE_API_URL: E2E_API_URL },
    timeout: 60_000,
  },
});
