import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./openapi.json",
  output: {
    path: "src/api/generated",
    format: "prettier",
  },
  plugins: [
    "@hey-api/client-axios",
    "@hey-api/typescript",
    "@hey-api/sdk",
  ],
});
