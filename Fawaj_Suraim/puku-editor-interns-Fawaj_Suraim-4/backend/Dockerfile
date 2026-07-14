# Multi-stage image for both the API server and the worker.
# Build from the REPO ROOT so the frontend source can be bundled into the
# final image and served by the Express backend.

FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
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