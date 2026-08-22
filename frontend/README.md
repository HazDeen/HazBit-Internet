# Hazbit Admin Panel

```bash
npm install
cp .env.example .env
npm run dev
```

`VITE_API_URL` points to the FastAPI `/api/v1` prefix. Set
`VITE_DEMO_MODE=true` only for the local showcase dataset.

Quality gate:

```bash
npm run typecheck
npm run build
```
