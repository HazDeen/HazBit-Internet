const common = {
  cwd: "/app/backend",
  interpreter: "none",
  autorestart: true,
  restart_delay: 2000,
  kill_timeout: 15000,
  time: false,
  merge_logs: true,
};

module.exports = {
  apps: [
    {
      ...common,
      name: "hazbit-api",
      script: "/opt/venv/bin/python",
      args: `-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${process.env.HAZBIT_API_WORKERS || "2"} --proxy-headers --forwarded-allow-ips=*`,
    },
    {
      ...common,
      name: "vpn-sync",
      script: "/opt/venv/bin/python",
      args: "-m app.workers.run_vpn_sync",
    },
    {
      ...common,
      name: "payment-analysis",
      script: "/opt/venv/bin/python",
      args: "-m app.workers.run_payments",
    },
    {
      ...common,
      name: "referral-rewards",
      script: "/opt/venv/bin/python",
      args: "-m app.workers.run_referrals",
    },
    {
      ...common,
      name: "telegram-notifications",
      script: "/opt/venv/bin/python",
      args: "-m app.workers.run_telegram_notifications",
    },
  ],
};
