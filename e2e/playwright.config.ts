import { defineConfig, devices } from "@playwright/test";

const port = 8485;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "off" },
  projects: [
    {
      name: "desktop",
      use: { viewport: { width: 1440, height: 900 } },
      testIgnore: /changes\.spec\.ts/,
    },
    {
      name: "phone",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
      testIgnore: /changes\.spec\.ts/,
    },
    // Tests that really change files run last, so they can't disturb the others.
    {
      name: "changes",
      use: { viewport: { width: 1440, height: 900 } },
      testMatch: /changes\.spec\.ts/,
      dependencies: ["desktop", "phone"],
    },
  ],
  webServer: {
    command: "./start-server.sh",
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: { PORT: String(port) },
  },
});
