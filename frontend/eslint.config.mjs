import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';
import importPlugin from 'eslint-plugin-import';
import prettierRecommended from 'eslint-plugin-prettier/recommended';
import { defineConfig, globalIgnores } from 'eslint/config';

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // eslint-config-next already registers the `import` plugin; only pull in the
  // recommended rules (re-registering the plugin would throw).
  { rules: importPlugin.flatConfigs.recommended.rules },
  // eslint-config-next 16 ships eslint-plugin-react-hooks v7, whose React
  // Compiler rules flag existing code. Keep them visible as warnings until the
  // affected components are refactored; they were not enforced under Next 15.
  {
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/static-components': 'warn',
    },
  },
  prettierRecommended,
  globalIgnores(['.next/**', 'out/**', 'build/**', 'next-env.d.ts']),
]);

export default eslintConfig;
