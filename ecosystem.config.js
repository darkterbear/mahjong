/* PM2 CONFIGURATION FILE */
// Options reference: https://pm2.io/doc/en/runtime/reference/ecosystem-file/
module.exports = {
  apps: [
    {
      name: 'mahjong-api',
      script: 'build/app.js',
      cwd: 'server/',
      env: {
        NODE_ENV: 'production',
        PORT: 3004
      },
      instances: 1,
      autorestart: true,
      watch: false,
    },
    {
      name: 'mahjong-client',
      script: 'serve',
      cwd: 'client/',
      env: {
        PM2_SERVE_PATH: 'build/',
        PM2_SERVE_PORT: 5004,
        PM2_SERVE_SPA: 'true'
      },
      instances: 1,
      autorestart: true,
      watch: false,
    },
  ],
};
