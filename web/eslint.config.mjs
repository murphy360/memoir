// From murphy360/standards templates/eslint.config.mjs, plus React's hooks rules. The complexity
// limits come from node-lint, not here. Change a rule only with a reason written beside it.
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist/",
      "node_modules/",
      "coverage/",
      ".standards/",
      "src/api/schema.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
  { languageOptions: { globals: { ...globals.browser } } },
);
