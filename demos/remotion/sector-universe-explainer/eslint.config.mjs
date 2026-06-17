import {config as remotion} from "@remotion/eslint-config-flat";

export default [
  ...remotion,
  {
    rules: {
      "@typescript-eslint/no-unused-vars": "error"
    }
  }
];
