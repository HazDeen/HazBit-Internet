# STEP 12 — Customer Web/PWA

## Результат

STEP 12 добавляет отдельный responsive React-клиент для пользователей Hazbit.
Это единое приложение для desktop и mobile/PWA, которое использует backend API,
созданные в STEP 3–11, и не дублирует бизнес-логику подписок, VPN, Family,
платежей, промокодов и support.

Основные разделы:

- главная со статусом VPN, подписки, устройств и Family;
- тарифы, создание payment intent, применение промокода и загрузка чека;
- VPN-устройства и приватная setup-ссылка;
- Family-группа, участники, лимиты и приглашения;
- referral rewards и активация промокодов;
- создание support ticket и customer chat;
- профиль, RU/EN, dark/light mode и безопасный logout.

## Архитектура

Клиент находится в `customer-frontend/` и использует React 19, TypeScript,
Vite и Lucide icons. Production API задаётся через `VITE_API_URL`, по умолчанию
`http://127.0.0.1:8000/api/v1`.

API client:

- хранит short-lived access JWT только в `sessionStorage`;
- повторяет запрос после refresh через rotating HttpOnly cookie и CSRF header;
- передаёт стабильный device fingerprint;
- использует `Idempotency-Key` для создающих операций;
- не сохраняет VPN subscription URL в persistent storage.

Backend portal façade предоставляет агрегаты, необходимые главной странице:

| Method | Path | Назначение |
|---|---|---|
| `GET` | `/api/v1/portal/overview` | Identity, subscription, VPN projection, devices, tickets и Family |
| `GET` | `/api/v1/portal/plans` | Активный customer catalog с версиями и ценами |
| `GET` | `/api/v1/portal/payments` | История платежей текущего пользователя |

Остальные экраны напрямую используют уже защищённые customer endpoints
`/devices`, `/family`, `/payments`, `/promo-codes`, `/referrals` и `/tickets`.

## PWA и responsive UI

Приложение содержит Web App Manifest, SVG app icon и service worker с
app-shell/offline fallback. На телефоне sidebar заменяется компактным bottom dock,
карточки переходят в одну колонку, формы и modal conversations занимают доступную
ширину. Поддерживаются safe-area inset и `prefers-reduced-motion`.

Дизайн-система использует тёмную premium-палитру, glass surfaces, мягкие
градиенты, connection signal animation и светлую тему. RU/EN переключается без
перезагрузки и сохраняется локально.

## Локальный запуск

Showcase с безопасными in-memory demo mutations:

```bash
cd customer-frontend
npm install
VITE_DEMO_MODE=true npm run dev
```

Открыть `http://127.0.0.1:5174/`.

Для реального backend:

```bash
cd customer-frontend
VITE_API_URL=http://127.0.0.1:8000/api/v1 npm run dev
```

## Проверки

- `npm run typecheck`;
- `npm run build`;
- backend `ruff`, `mypy` и unit test suite;
- browser QA desktop 1440×900 и mobile 390×844;
- проверены ticket reply, создание VPN-устройства, Family invitation,
  RU localization, centered modals и отсутствие console warnings/errors.
