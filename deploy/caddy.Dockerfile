# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS admin-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
COPY shared /build/shared
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL VITE_DEMO_MODE=false
RUN npm run build

FROM node:22-bookworm-slim AS customer-build
WORKDIR /build/customer-frontend
COPY customer-frontend/package.json customer-frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY customer-frontend ./
COPY shared /build/shared
ARG VITE_API_URL=/api/v1
ARG VITE_LEGAL_PROJECT_NAME="Hazbit"
ARG VITE_LEGAL_OPERATOR_NAME="Hazbit"
ARG VITE_SUPPORT_EMAIL=support@hazdeen.xyz
ARG VITE_SUPPORT_TELEGRAM=@hazbit_support
ENV VITE_API_URL=$VITE_API_URL VITE_DEMO_MODE=false VITE_LEGAL_PROJECT_NAME=$VITE_LEGAL_PROJECT_NAME VITE_LEGAL_OPERATOR_NAME=$VITE_LEGAL_OPERATOR_NAME VITE_SUPPORT_EMAIL=$VITE_SUPPORT_EMAIL VITE_SUPPORT_TELEGRAM=$VITE_SUPPORT_TELEGRAM
RUN npm run build

FROM node:22-bookworm-slim AS miniapp-build
WORKDIR /build/telegram-miniapp
COPY telegram-miniapp/package.json telegram-miniapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY telegram-miniapp ./
COPY customer-frontend/src/mock.ts customer-frontend/src/types.ts /build/customer-frontend/src/
COPY shared /build/shared
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL VITE_DEMO_MODE=false
RUN npm run build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=admin-build /build/frontend/dist /srv/admin
COPY --from=customer-build /build/customer-frontend/dist /srv/customer
COPY --from=miniapp-build /build/telegram-miniapp/dist /srv/miniapp
