FROM node:24.11.0-bookworm-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM golang:1.27.3-alpine AS proxy
WORKDIR /build
RUN go mod init givvi-proxy \
	&& go get github.com/caddyserver/caddy/v2/cmd/caddy@v2.11.7 \
		github.com/go-jose/go-jose/v4@v4.1.6 golang.org/x/net@v0.60.0 \
	&& CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /usr/bin/caddy github.com/caddyserver/caddy/v2/cmd/caddy

FROM caddy:2.11.7-alpine
RUN apk upgrade --no-cache && mkdir -p /srv /data /config && chown -R 10001:10001 /srv /data /config
COPY --from=proxy /usr/bin/caddy /usr/bin/caddy
COPY --from=build --chown=10001:10001 /app/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile
USER 10001:10001
EXPOSE 8080 8443
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD nc -z 127.0.0.1 8443