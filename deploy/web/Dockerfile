# syntax=docker/dockerfile:1.7
# Frontend image: builds the Vite app and serves it with Caddy, which also proxies /api to
# the backend and obtains HTTPS certificates automatically. Build context: repository root.

FROM node:22-alpine AS build
WORKDIR /app
RUN npm install --global pnpm@10.32.1
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY . .
# Same origin as the page: the browser sends the refresh cookie without CORS tricks.
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=${VITE_API_URL}
RUN pnpm typecheck && pnpm build

FROM caddy:2-alpine
COPY deploy/web/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
