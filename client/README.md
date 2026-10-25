# Altrix client

Next.js frontend for the Altrix API. Setup, environment variables and endpoints are in the
[repository README](../README.md#web-app-nextjs--fastapi) (the API lives in [`../server`](../server)).

```bash
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                  # http://localhost:3000 (start the API first)
npm run lint && npx tsc --noEmit && npm run build
```

`src/lib/api.ts` is the only module that calls the API, and `src/lib/types.ts` mirrors `../server/api/schemas.py`.
No signals or indicators are computed in the frontend.
