# STEP 13 — Telegram Mini App

## Результат

STEP 13 добавляет отдельный mobile-first React-клиент `telegram-miniapp/` поверх
общих customer contracts, дизайн-токенов и backend feature API. Mini App не
доверяет данным Telegram на клиенте: raw `Telegram.WebApp.initData` всегда
проверяется backend endpoint `/api/v1/auth/telegram`.

Реализованы:

- автоматическая Telegram authentication и JWT/refresh session;
- тёмная тема Hazbit по умолчанию и сохраняемый переключатель светлой темы;
- `viewportStableHeight`, safe-area и expanded viewport;
- native Back Button для sheet/chat navigation;
- native Main Button для Telegram invoice flow;
- haptic feedback для навигации, успеха и ошибок;
- platform-first bottom navigation;
- deep links для тарифов, промокодов, Family invitations и tickets;
- подписка, устройства, Family, referral sharing и support chat;
- RU/EN с автоматическим выбором по Telegram language code;
- browser fallback/demo mode для локальной разработки.

## Общие модули

Web/PWA и Mini App используют общие типизированные domain contracts из
`shared/customer/types.ts` и brand tokens из
`shared/customer/design-tokens.css`. Оба клиента обращаются к одному набору
backend feature modules: portal, devices, payments, promotions, referrals,
families и support.

Визуальная композиция Mini App отдельная: она оптимизирована под узкий Telegram
viewport, bottom dock и native sheets, но не создаёт параллельные модели данных
или entitlement rules.

## Telegram authentication

Bootstrap выполняется в таком порядке:

1. `Telegram.WebApp.ready()` и `expand()`;
2. raw `initData` вместе с device fingerprint отправляется в
   `POST /api/v1/auth/telegram`;
3. backend проверяет HMAC, `auth_date`, typed user payload и replay window;
4. access JWT хранится только в `sessionStorage`;
5. refresh token остаётся в rotating HttpOnly cookie;
6. все customer API requests получают Bearer JWT и fingerprint.

`initDataUnsafe.user` используется только для мгновенного отображения имени и
темы до загрузки server identity. Он никогда не является источником авторизации.

## Deep links

Поддерживаются `startapp`/`tgWebAppStartParam`:

| Параметр | Результат |
|---|---|
| `plan_family` | Открыть тарифы и поставить Family первым |
| `promo_WELCOME20` | Открыть тарифы и заполнить промокод |
| `invite_<token>` | После auth принять Family invitation |
| `ticket_<uuid-or-number>` | Открыть нужный support conversation |

Referral sharing использует Telegram share URL и существующий signed attribution
flow backend.

## Invoice flow

`PaymentResponse` содержит optional `telegram_invoice_url`. Когда backend или bot
provider возвращает ссылку, Mini App открывает её через
`Telegram.WebApp.openInvoice()` и обрабатывает `paid`, `pending`, `cancelled` и
`failed`. Если invoice link отсутствует, сохраняется текущий bank-transfer flow и
пользователь может загрузить чек через Web/PWA.

Получение provider invoice link через Bot API и settlement webhook относятся к
STEP 14, потому что они требуют bot provider token, webhook verification и
идемпотентную обработку `successful_payment`.

## Telegram platform adapter

`src/telegram.ts` изолирует Telegram SDK от feature UI:

- background/header colors согласно выбранной теме Hazbit;
- stable viewport CSS variable;
- Back Button и Main Button lifecycle;
- haptics;
- Telegram links, external links и invoices;
- graceful browser fallback.

Тема Telegram не переопределяет оформление автоматически: продукт всегда впервые
открывается в фирменной тёмной теме. Пользователь может включить светлую тему из
header или раздела «Ещё», после чего выбор сохраняется в local storage и цвет
Telegram header/background синхронизируется с ним.

При закрытии React sheet обработчики Telegram-кнопок снимаются, поэтому повторное
открытие не создаёт дубликаты callbacks.

## Запуск

Локальный showcase:

```bash
cd telegram-miniapp
npm install
VITE_DEMO_MODE=true npm run dev
```

Открыть `http://127.0.0.1:5175/`.

Production build:

```bash
VITE_API_URL=https://api.example.com/api/v1 npm run build
```

В BotFather нужно создать Web App/Menu Button с публичным HTTPS URL Mini App.
Localhost напрямую внутри Telegram не открывается; для device testing нужен
HTTPS tunnel или staging deployment.

## Проверки

- Mini App `tsc --noEmit` и production build;
- Customer Web/PWA повторно проходит typecheck/build после выноса shared modules;
- backend Ruff, Mypy и unit tests;
- local server и manifest отвечают на порту 5175;
- Telegram bridge не используется как источник доверенной identity.
