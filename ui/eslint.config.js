import js from "@eslint/js";
import importPlugin from "eslint-plugin-import";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "node_modules",
      "coverage",
      "test-results",
      "e2e",
      "**/*.config.{js,ts}",
      "vite.config.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser },
    },
    plugins: {
      "react-hooks": reactHooks,
      import: importPlugin,
    },
    settings: {
      "import/resolver": { typescript: true, node: true },
    },
    rules: {
      // Real-bug guards — the highest-value reason to add ESLint to a React app.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Keep imports tidy and group @/ internal imports consistently.
      "import/order": [
        "warn",
        {
          groups: ["builtin", "external", "internal", "parent", "sibling", "index"],
          pathGroups: [{ pattern: "@/**", group: "internal" }],
          pathGroupsExcludedImportTypes: ["builtin"],
          alphabetize: { order: "asc", caseInsensitive: true },
        },
      ],
    },
  },
  // Test files use jsdom + node globals.
  {
    files: ["src/**/*.{test,spec}.{ts,tsx}", "src/test/**"],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
);
