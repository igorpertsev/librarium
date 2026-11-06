import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

// Unit tests for the frontend: `pnpm test` (once) or `pnpm test:watch`.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
      // Node 22+ has its own localStorage global, which would hide the jsdom one.
      execArgv: ['--no-experimental-webstorage'],
      restoreMocks: true,
    },
  }),
);
