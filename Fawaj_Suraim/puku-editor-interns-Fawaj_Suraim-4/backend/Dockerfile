# Multi-stage image for both the API server and the worker.
# Build from the REPO ROOT so the frontend source can be bundled into the
# final image and served by the Express backend.

# VITE_API_KEY is the frontend build-time equivalent of the backend's
# API_KEY. We accept it as a build arg (compose forwards it from the
# root .env) so the same-origin Docker UI ships with the key already
# baked in — otherwise the browser's localStorage is empty (localStorage
# is per-origin) and every /jobs request 401s until the user manually
# pastes the key into the header. ARG-with-default keeps the image
# buildable when no key is supplied.
ARG VITE_API_KEY=""
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Inline the arg into a .env file Vite picks up automatically (any
# VITE_-prefixed var in .env gets exposed to the bundle via
# import.meta.env). Passing it via --build-arg is cleaner than using
# ENV in this build stage, since Vite reads .env at build time only.
RUN echo "VITE_API_KEY=${VITE_API_KEY}" > .env.production
RUN npm run build

FROM node:20-alpine

# tini gives us proper signal forwarding (SIGTERM) so graceful shutdown runs.
RUN apk add --no-cache tini docker-cli
WORKDIR /app

# Install deps separately so source changes don't bust the layer cache.
COPY backend/package*.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY backend/src ./src
COPY backend/test ./test
COPY --from=frontend-build /app/frontend/dist ./public

ENV NODE_ENV=production
ENV PORT=3000
ENV REDIS_URL=redis://redis:6379

EXPOSE 3000
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "src/server.js"]