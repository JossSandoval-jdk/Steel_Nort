import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    // Permite que los archivos de contexto exporten hooks (p. ej.
    // AuthContext: <AuthProvider> + useAuth()). Es un patron estandar
    // de React y no rompe el fast refresh.
    files: ['**/context/*.jsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
