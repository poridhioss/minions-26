# Frontend production image.
# Build with:  docker build -f frontend/Dockerfile -t replit-frontend frontend/
# Run with:    docker run --rm -p 8080:80 replit-frontend
#
# Multi-stage build keeps the runtime image small (nginx:alpine ≈ 40MB)
# while reusing the full Node toolchain for the Vite build.
#
# Nginx reverse-proxies /api/* and /socket.io/* to the backend service.
# In docker-compose the backend is reachable at http://backend:3001;
# override BACKEND_URL at build time to point at a different host.
#
#   docker build --build-arg BACKEND_URL=http://api.example.com -t replit-frontend frontend/

# ---------- Stage 1: build ----------
FROM node:20-alpine AS build

WORKDIR /app

# Install deps with the lockfile present so we get a reproducible tree.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Build the static bundle into /app/dist.
COPY . .
ARG VITE_API_BASE=/api
ARG VITE_SOCKET_URL=
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_SOCKET_URL=${VITE_SOCKET_URL}
RUN npm run build

# ---------- Stage 2: serve ----------
FROM nginx:1.27-alpine

# Drop the default site, ship our reverse-proxy-aware one.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Static assets produced by `vite build`.
COPY --from=build /app/dist /usr/share/nginx/html

# Render the BACKEND_URL placeholder at start time. We use envsubst on
# the bundled config (already copied above) and write it back atomically
# via a small entrypoint script.
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV BACKEND_URL=http://backend:3001
EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
