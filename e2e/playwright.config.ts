import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 90_000,
  globalSetup: "./global-setup.ts",
  use: { baseURL: process.env.BASE_URL ?? "http://192.168.18.2:8300", storageState: ".auth.json" },
});
