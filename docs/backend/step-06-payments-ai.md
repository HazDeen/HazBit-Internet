# STEP 6 — Payments AI с Gemini Vision

## 1. Результат

STEP 6 реализует полный backend-flow оплаты банковским переводом по скриншоту:

```text
payment intent
  → canonical evidence upload
  → durable PostgreSQL claim
  → Gemini structured extraction
  → deterministic rules
      ├─ pass → approved + balanced ledger + outbox
      └─ fail → manual review → approved | rejected
```

Gemini не принимает финансовое решение. Модель возвращает только typed extraction:
сумму в minor units, ISO currency, дату, номер операции, банк, получателя,
признак платежного документа, confidence и warnings. Решение вычисляет локальный
rule engine, а переход в `approved` выполняется отдельной application-функцией.

Используется официальный `google-genai` SDK: image bytes передаются как
`Part.from_bytes`, а `response_schema=ReceiptExtraction` ограничивает ответ
Pydantic-схемой. Документация Google: [image understanding](https://ai.google.dev/gemini-api/docs/image-understanding),
[structured output](https://ai.google.dev/gemini-api/docs/structured-output) и
[Python SDK](https://googleapis.github.io/python-genai/).

## 2. API

Все customer endpoints требуют Bearer JWT и проверяют ownership. Mutation endpoints
также требуют `Idempotency-Key`.

| Method | Path | Назначение |
|---|---|---|
| `POST` | `/api/v1/payments/intents` | Зафиксировать активную цену, валюту и server-side recipient |
| `GET` | `/api/v1/payments/{payment_id}` | Получить state и summary последнего анализа |
| `POST` | `/api/v1/payments/{payment_id}/evidence` | Загрузить JPEG/PNG/WebP screenshot |
| `GET` | `/api/v1/admin/payments/review-queue` | Очередь ручной проверки, только admin/super_admin |
| `GET` | `/api/v1/admin/payments/evidence/{evidence_id}` | Приватно получить evidence с `no-store`/`nosniff` |
| `POST` | `/api/v1/admin/payments/{payment_id}/review` | Approve/reject с optimistic `expected_version` |

Клиент не передает ожидаемую сумму, валюту или получателя. Intent читает активный
`plan_prices` snapshot и `HAZBIT_PAYMENTS__EXPECTED_RECIPIENT`, поэтому нельзя
подменить условия платежа request payload-ом.

## 3. Evidence pipeline

Upload ограничен одновременно размером файла и числом pixels. Заявленный MIME
не считается доверенным: Pillow декодирует изображение, применяет EXIF orientation,
удаляет metadata и повторно кодирует RGB JPEG. В object storage сохраняются только
канонические bytes, SHA-256 и приватный key. HTML/polyglot, пустые файлы,
decompression bombs и неизвестные форматы отклоняются до Gemini.

Local backend хранит файлы в `.data/payment-evidence` только для разработки.
Production configuration требует S3-compatible storage. S3 writes используют
server-side AES-256 encryption. Endpoint нужен для MinIO и
других S3-compatible providers; для AWS S3 он может быть пустым. Credentials можно
передать явно или получить через стандартную AWS IAM credential chain. Evidence не
имеет публичного URL.

## 4. Gemini boundary

System instruction явно считает весь текст внутри изображения недоверенными данными
и запрещает выполнять напечатанные в чеке инструкции. В prompt не передаются
expected amount/recipient, чтобы не подталкивать модель к нужному совпадению.
Модель и prompt version сохраняются на каждой попытке в `payment_analyses`.

Ошибки `429`, `5xx`, timeout и временная ошибка storage retry-ятся до bounded
`analysis_max_attempts`. Невалидная structured response, отсутствие API key и
исчерпание попыток переводят payment в `manual_review`; они никогда не вызывают
ledger posting.

Worker claim использует `FOR UPDATE SKIP LOCKED`. Claim увеличивает payment version,
а результат применяется только при совпадении version. Поэтому stale worker не
может записать поздний Gemini response после reclaim другим worker.

## 5. Deterministic approval rules

Auto approval требует одновременного выполнения всех проверок:

- изображение классифицировано как payment receipt;
- amount в minor units точно равен snapshot intent;
- ISO currency совпадает;
- нормализованный recipient совпадает точно;
- operation/reference number присутствует;
- operation date входит в разрешенное окно;
- confidence не ниже configured threshold;
- normalized operation number + recipient + currency ещё не использованы.

Каждая проверка и примененная policy сохраняются в `rule_results`. Любое несовпадение
даёт `manual_review`, а не автоматический reject. Администратор принимает решение с
обязательной причиной; optimistic version защищает от двух параллельных reviewers.
Database unique index дополнительно запрещает повторно approved bank operation.

## 6. Ledger и activation boundary

Один переход в `approved` создаёт одну `payment_credit` transaction:

```text
user_wallet    +amount_minor
cash_clearing  -amount_minor
sum             0
```

Entries вставляются в draft, затем database trigger разрешает posting только при
минимум двух entries, нулевой сумме и одной валюте. Posted transaction immutable.
В той же PostgreSQL transaction создаются audit log и outbox event
`payment.approved`. Consumer этого event в следующем subscription stage создаст
entitlement/активацию; Gemini worker напрямую VPN не включает.

Миграция `20260822_0003` задаёт ledger trigger functions безопасный `search_path`
`pg_catalog, app`, чтобы triggers корректно и однозначно работали из runtime sessions.

## 7. Конфигурация

Минимальная local конфигурация:

```text
HAZBIT_PAYMENTS__GEMINI__API_KEY=<Gemini API key>
HAZBIT_PAYMENTS__GEMINI__MODEL=gemini-2.5-flash
HAZBIT_PAYMENTS__EXPECTED_RECIPIENT=HAZBIT VPN
HAZBIT_PAYMENTS__STORAGE__BACKEND=local
HAZBIT_PAYMENTS__STORAGE__LOCAL_DIRECTORY=.data/payment-evidence
```

Production S3-compatible storage:

```text
HAZBIT_PAYMENTS__STORAGE__BACKEND=s3
HAZBIT_PAYMENTS__STORAGE__BUCKET=hazbit-payment-evidence
HAZBIT_PAYMENTS__STORAGE__ENDPOINT_URL=https://objects.example.com
HAZBIT_PAYMENTS__STORAGE__REGION=us-east-1
HAZBIT_PAYMENTS__STORAGE__ACCESS_KEY_ID=...
HAZBIT_PAYMENTS__STORAGE__SECRET_ACCESS_KEY=...
```

API key находится только в backend/worker environment, не возвращается API и не
пишется в logs/audit. Gemini client создаётся лениво только при первом анализе.

## 8. Запуск

```bash
cd backend
.venv/bin/alembic upgrade head
make run
make worker-payments
```

API и worker должны использовать одну PostgreSQL database и одно object storage.
Для production worker масштабируется горизонтально благодаря `SKIP LOCKED` и
version-fenced results.

## 9. Проверки

Unit tests покрывают canonical image decoding, invalid image rejection, structured
receipt schema, prompt-injection boundary, identifier normalization, duplicate rule,
route registration и production config guards. PostgreSQL integration test покрывает:

- migration до head;
- intent и evidence upload;
- successful fake Gemini extraction;
- auto approval;
- balanced immutable ledger posting;
- transactional outbox;
- duplicate operation → manual review;
- admin rejection с optimistic version.

Интеграционные тесты используют fake extractor и не отправляют изображения во внешний
Gemini API, поэтому CI не требует secret и не расходует quota.
