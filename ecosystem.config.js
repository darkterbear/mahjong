module.exports = {
  apps: [
    {
      name: 'mahjong-server',
      cwd: './server-py',
      script: '.venv/bin/uvicorn',
      args: 'server.app:app --host 0.0.0.0 --port 8080',
      env: {
        PORT: 8080,
      },
    },
    {
      name: 'mahjong-client',
      cwd: './client',
      script: 'yarn',
      args: 'start',
      env: {
        PORT: 5000,
      },
    },
  ],
};
