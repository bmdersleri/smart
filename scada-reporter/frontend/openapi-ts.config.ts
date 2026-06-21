import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./openapi.json",
  output: {
    // No prettier post-processing: hey-api spawns the `prettier` binary which
    // isn't on PATH in CI (ENOENT). hey-api's own formatting is deterministic
    // and the generated dir is lint-excluded, so prettier adds no value here.
    path: "src/api/generated",
  },
  plugins: [
    "@hey-api/client-axios",
    "@hey-api/typescript",
    "@hey-api/sdk",
  ],
});
