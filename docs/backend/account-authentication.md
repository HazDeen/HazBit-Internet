# Hazbit account authentication

Hazbit supports one canonical user with several verified identities:

- email and a permanent Argon2id password;
- email OTP for confirmation and recovery-style sign-in;
- Google Identity Services using a server-verified ID token;
- Telegram Login Widget on the website;
- Telegram Mini App `initData` inside Telegram;
- numeric Telegram ID followed by confirmation in the official customer bot.

A numeric Telegram ID is never accepted as a password. Registration with an
optional Telegram ID remains pending until that exact Telegram account opens the
short-lived bot link. If the Telegram identity already owns devices or a
subscription, email and password are attached to that existing `user_id`.

## Google setup

Create an OAuth 2.0 **Web application** client in Google Cloud Console. Add:

- `https://hazdeen.xyz`
- `https://app.hazdeen.xyz`

to Authorized JavaScript origins. Google Identity Services does not support
ordinary OAuth buttons inside embedded webviews, so the Telegram Mini App keeps
using signed Telegram `initData`.

Set the same client ID in both places:

```env
HAZBIT_AUTH__GOOGLE__ENABLED=true
HAZBIT_AUTH__GOOGLE__CLIENT_ID=000000000000-example.apps.googleusercontent.com
VITE_GOOGLE_CLIENT_ID=000000000000-example.apps.googleusercontent.com
```

## Telegram setup

In BotFather, use `/setdomain` for the customer bot and select `hazdeen.xyz`.
The Mini App URL is `https://mini.hazdeen.xyz`. Production settings must include:

```env
HAZBIT_AUTH__TELEGRAM__BOT_TOKEN=123456:real-customer-token
HAZBIT_AUTH__TELEGRAM__BOT_USERNAME=hazbit_bot
VITE_TELEGRAM_BOT_USERNAME=hazbit_bot
HAZBIT_FEATURES__TELEGRAM_BOTS=true
HAZBIT_CONFIGURE_TELEGRAM_WEBHOOKS=true
HAZBIT_TELEGRAM_BOTS__WEBHOOK_BASE_URL=https://api.hazdeen.xyz
HAZBIT_TELEGRAM_BOTS__MINI_APP_URL=https://mini.hazdeen.xyz
```

The customer and operations tokens must belong to different bots. After launch,
inspect both bot identities, webhook URLs, pending updates and the last Telegram
delivery error:

```bash
cd /opt/hazbit
docker compose --env-file deploy/.env.production -f compose.prod.yml \
  exec -T platform python -m app.workers.check_telegram_bots
```

If `/start` is silent, this command now fails with the actual reason. The common
causes are a disabled `HAZBIT_FEATURES__TELEGRAM_BOTS`, a missing token, a stale
webhook, or `api.hazdeen.xyz` returning 502 to Telegram. The production launch
script configures the webhooks and runs this check before declaring success.

## Platega review

The public website and the authenticated Profile page both permanently expose:

- Privacy Policy;
- User Agreement;
- support email, Telegram contact and the ticket system.

The permanent password flow allows a bank reviewer to enter the account without
access to the account mailbox. Email OTP remains mandatory when the password is
first created.
