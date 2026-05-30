// PM2 config for Oracle Cloud Ubuntu (Linux)
// Path: ~/arthaos/deploy/ecosystem.linux.config.js
// Start: pm2 start ~/arthaos/deploy/ecosystem.linux.config.js

const HOME = process.env.HOME || "/home/ubuntu";
const ARTHAOS = `${HOME}/arthaos`;
const VENV = `${ARTHAOS}/.venv`;

module.exports = {
  apps: [
    // ─── Backend (FastAPI) ───────────────────────────────────────────────────
    {
      name: "arthaos",
      script: `${VENV}/bin/uvicorn`,
      args: "backend.main:app --host 0.0.0.0 --port 8000",
      cwd: ARTHAOS,
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: {
        PYTHONPATH: ARTHAOS,
        PATH: `${VENV}/bin:${process.env.PATH}`,
      },
    },

    // ─── Frontend (Next.js — production) ────────────────────────────────────
    {
      name: "arthaos-frontend",
      script: "node_modules/.bin/next",
      args: "start --port 3000",
      cwd: `${ARTHAOS}/frontend`,
      interpreter: "node",
      autorestart: true,
      watch: false,
      env: {
        NODE_ENV: "production",
      },
    },

    // ─── REA Communication Agent (WhatsApp bridge) ───────────────────────────
    {
      name: "arthaos-rea",
      script: "index.js",
      cwd: `${ARTHAOS}/REA`,
      interpreter: "node",
      autorestart: true,
      watch: false,
      env: {
        // Chromium path on Ubuntu — set for puppeteer/whatsapp-web.js
        PUPPETEER_EXECUTABLE_PATH: "/usr/bin/chromium-browser",
        // Disable sandbox in headless server environment
        CHROMIUM_FLAGS: "--no-sandbox --disable-setuid-sandbox",
        // Use localhost — REA and ArthaOS run on the same server.
        // Using the external GCP IP for same-machine calls causes hairpin routing
        // failures on GCP (port 8000 is not exposed externally through nginx).
        ARTHAOS_API_URL: "http://localhost:8000",
        ARTHAOS_ALERT_PORT: "8001",
      },
    },
  ],
};
