# Hazbit Customer Web/PWA

Responsive customer application for desktop and mobile. It includes Email OTP,
subscription and payment flows, VPN devices, Family, referrals, promo codes,
support tickets, RU/EN localization, themes and an installable PWA shell.

## Run the showcase

```bash
npm install
VITE_DEMO_MODE=true npm run dev
```

Open `http://127.0.0.1:5174/`.

## Connect the API

```bash
VITE_API_URL=http://127.0.0.1:8000/api/v1 npm run dev
```

See [`STEP 12`](../docs/frontend/step-12-customer-web-pwa.md) for contracts,
security behavior and verification notes.
