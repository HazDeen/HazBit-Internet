# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS admin-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL VITE_DEMO_MODE=false
RUN npm run build

FROM node:22-bookworm-slim AS customer-build
WORKDIR /build
COPY customer-frontend/package.json customer-frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY customer-frontend ./
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL VITE_DEMO_MODE=false
RUN npm run build

FROM node:22-bookworm-slim AS miniapp-build
WORKDIR /build
COPY telegram-miniapp/package.json telegram-miniapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY telegram-miniapp ./
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL VITE_DEMO_MODE=false
RUN npm run build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=admin-build /build/dist /srv/admin
COPY --from=customer-build /build/dist /srv/customer
COPY --from=miniapp-build /build/dist /srv/miniapp
