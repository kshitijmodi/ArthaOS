module.exports = {
  apps: [
    {
      name: "arthaos",
      script: "C:\\Users\\KshitijModi\\AppData\\Local\\Programs\\Python\\Python311\\Scripts\\uvicorn.exe",
      args: "backend.main:app --host 0.0.0.0 --port 8000",
      cwd: "c:\\Users\\KshitijModi\\Downloads\\Remote Engineering Agents\\workspace\\ArthaOS",
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: {
        PYTHONPATH: "c:\\Users\\KshitijModi\\Downloads\\Remote Engineering Agents\\workspace\\ArthaOS"
      }
    },
    {
      name: "arthaos-frontend",
      script: "node_modules\\next\\dist\\bin\\next",
      args: "dev",
      cwd: "c:\\Users\\KshitijModi\\Downloads\\Remote Engineering Agents\\workspace\\ArthaOS\\frontend",
      interpreter: "C:\\Users\\KshitijModi\\AppData\\Roaming\\nodejs\\node.exe",
      autorestart: true,
      watch: false
    }
  ]
};
