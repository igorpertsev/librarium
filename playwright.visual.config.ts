import { defineConfig, devices } from '@playwright/test';

// Visual regression tests: screenshots of the main pages compared with the reference images in
// e2e/visual/__screenshots__. Run them with `pnpm e2e:visual` (e2e/visual.sh), which starts a fresh
// e2e stack and runs this config inside the Playwright Docker image, so fonts and rendering match
// the reference images on every machine and in CI. The page and the API share one origin through
// Vite's proxy (VITE_PROXY_API), as behind Caddy in production.
// The e2e backend accepts this origin (FRONTEND_ORIGINS); inside the container the port is free.
const PORT = 4173;

export default defineConfig({
  testDir: 'e2e/visual',
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{arg}{ext}',
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never', outputFolder: 'playwright-report-visual' }]] : 'list',
  outputDir: 'test-results-visual',
  timeout: 60_000,
  expect: {
    toHaveScreenshot: { maxDiffPixels: 100, animations: 'disabled', caret: 'hide', scale: 'css' },
  },
  use: {
    baseURL: `http://localhost:${PORT}`,
    locale: 'en-US',
    timezoneId: 'Europe/Amsterdam',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop-light', use: { ...devices['Desktop Chrome'], colorScheme: 'light' } },
    { name: 'desktop-dark', use: { ...devices['Desktop Chrome'], colorScheme: 'dark' } },
    { name: 'mobile-light', use: { ...devices['Pixel 7'], colorScheme: 'light' } },
    { name: 'mobile-dark', use: { ...devices['Pixel 7'], colorScheme: 'dark' } },
  ],
  webServer: {
    command: `pnpm exec vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
    env: {
      VITE_API_URL: '/api/v1',
      VITE_PROXY_API: process.env.VISUAL_BACKEND_URL || 'http://localhost:8100',
    },
    timeout: 120_000,
  },
});
