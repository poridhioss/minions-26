# Multi-stage-ish single image used for both the API server and the worker.
# The container runs the role passed via CMD (server or worker).
#
# Build from the REPO ROOT, not from ./backend, so we can COPY ../frontend:
#   docker build -f backend/Dockerfile .
# (docker compose handles this automatically.)

FROM node:20-alpine

# tini gives us proper signal forwarding (SIGTERM) so graceful shutdown runs.
RUN apk add --no-cache tini docker-cli
WORKDIR /app

# Install deps separately so source changes don't bust the layer cache.
COPY backend/package*.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY backend/src ./src
COPY backend/test ./test
COPY frontend ./public

ENV NODE_ENV=production
ENV PORT=3000
ENV REDIS_URL=redis://redis:6379

EXPOSE 3000
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "src/server.js"]


# ===== REBUILT =====
# (placeholder for visibility)