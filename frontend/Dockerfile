FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=builder /app/dist /srv
# Caddyfile is bind-mounted at runtime by docker-compose.yml, not baked in here,
# so it can be edited (e.g. swapping :80 for a real domain) without a rebuild.
