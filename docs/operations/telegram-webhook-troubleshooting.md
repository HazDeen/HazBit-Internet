# Telegram webhook readiness and recovery

`setWebhook` returning success confirms configuration, not delivery of an update.
According to [Telegram's WebhookInfo documentation](https://core.telegram.org/bots/api#webhookinfo),
`last_error_date` and `last_error_message` describe the most recent delivery error;
`pending_update_count` counts updates still awaiting delivery. An old error alone is
not a current health check, but a nonempty queue must not be silently ignored.

## What launch checks

1. Compose waits for containers to be running/healthy (up to 180 seconds).
2. Application preflight checks the configured dependencies.
3. When automatic setup is enabled, the setup worker checks the public API through
   Caddy before registering either webhook. It preserves pending updates.
4. The verification worker independently checks the public routes, bot identities,
   exact webhook URLs, error timestamps and pending queues.

The public probe requests `/health/ready` and expects `200` with `status=ok`.
It also POSTs `{"update_id":0}` **without a webhook secret** to both bot routes.
The expected response is `403` with `code=telegram_webhook_forbidden`. This confirms
the proxy reaches the intended application route without processing an update,
creating a user or sending messages. An arbitrary proxy-generated `403` is not enough.
The probe retries for at most 45 seconds; it does not disable TLS checks or follow redirects.

The Telegram delivery check has at most seven snapshots, five seconds apart, with
a 60-second overall limit. It succeeds only when both URLs match, both queues are
empty and no new/undated delivery errors remain. An error predating verification
is reported as historical only alongside an empty queue and successful public probes.
Error timestamps are printed in UTC. A fresh error does not age out during the run.

These checks do not prove a command handler successfully replies. Finish by sending
`/start` to each bot. An operations bot also requires the configured staff permissions.

## Feature flags

Set these in the production env file and recreate the platform container after changes:

- `HAZBIT_FEATURES__TELEGRAM_BOTS=false`: skip setup and verification entirely.
- `HAZBIT_CONFIGURE_TELEGRAM_WEBHOOKS=false`: skip automatic registration only;
  verification still checks the manually configured webhooks.

The flags are read inside the container. Docker's `--env-file` does not export them
into the shell running `launch.sh`.

## If verification fails

Do not repeatedly rebuild or restart the stack just to recheck delivery. The running
containers are not stopped when verification exits with an error. Keep them running
so Telegram can retry, then run:

```sh
cd /opt/hazbit
docker compose --env-file deploy/.env.production -f compose.prod.yml \
  exec -T platform python -m app.workers.check_telegram_bots
```

- Public probe `502`: inspect both the external Caddy and Hazbit Caddy upstreams,
  their shared Docker network, and platform readiness.
- Public probe wrong content or `404`: inspect the host/path routing and API prefix.
- Correct public probe but `pending>0` or a new Telegram error: inspect platform logs
  at the displayed UTC error time. Check webhook secret consistency and Telegram's
  reported delivery error; a working health endpoint alone does not prove delivery.
- Queue drained but `/start` has no reply: inspect command handling and outgoing
  Telegram API errors (including permissions/blocked bot), not just webhook setup.

Useful logs (redact old entries before sharing):

```sh
docker compose --env-file deploy/.env.production -f compose.prod.yml \
  logs --since=10m --tail=150 platform caddy \
  | sed -E 's@bot[0-9]+(:|%3[Aa])[A-Za-z0-9_-]+@bot[REDACTED]@g'

# Existing external Caddy, when its container is named caddy:
docker logs --since=10m --tail=100 caddy 2>&1 \
  | sed -E 's@bot[0-9]+(:|%3[Aa])[A-Za-z0-9_-]+@bot[REDACTED]@g'
```

For a containerized external Caddy on `hazbit-public`, the internal upstream is
`hazbit-web:80`, not `127.0.0.1:18080` (which refers to the external Caddy container
itself). This applies when Hazbit uses `deploy/Caddyfile.internal`.
Do not replace unrelated Remnawave virtual hosts or remove Docker volumes.

## Exposed tokens

The application now redacts Telegram URL credentials in rendered logs and suppresses
credential-bearing HTTP exception chains in the Telegram client. This does not erase
old logs or revoke already exposed credentials. Revoke both exposed bot tokens through
BotFather, update `HAZBIT_AUTH__TELEGRAM__BOT_TOKEN` and
`HAZBIT_TELEGRAM_BOTS__OPERATIONS_BOT_TOKEN` in the private production env file, and
recreate the platform container. Register and verify webhooks with the new credentials.
Never paste bot tokens or the full production env file into chat or Git.
