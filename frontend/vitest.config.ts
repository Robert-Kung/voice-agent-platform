import path from 'path';
import { defineConfig } from 'vitest/config';

// Pure-function tests only (no jsdom, no component rendering) — review D7.
export default defineConfig({
  resolve: {
    alias: { '@': path.resolve(__dirname) },
  },
  // Imported component CSS (e.g. @xyflow/react) must not run the app's
  // Tailwind postcss pipeline inside the test runner.
  css: { postcss: {} },
  test: {
    include: ['**/__tests__/**/*.test.ts'],
    environment: 'node',
  },
});
