# Backend orchestration server.
# Build with:  docker build -f backend/Dockerfile -t replit-backend backend/
# Run with:    docker run --rm -p 3001:3001 \
#                -v /var/run/docker.sock:/var/run/docker.sock \
#                replit-backend
#
# The image only contains the Node orchestration server. It is
# designed to be launched with the host's Docker daemon socket
# bind-mounted in, so the backend can create/destroy sibling
# workspace containers via dockerode.
#
# The non-root `node` user baked into the base image runs the server.
# Access to the docker socket is mediated by the host's docker group
# permissions — if your /var/run/docker.sock is owned by `root:docker`
# with mode 0660, add `--group-add $(getent group docker | cut -d: -f3)`
# to the `docker run` command.

# ---------- Stage 1: deps ----------
FROM node:20-alpine AS deps

WORKDIR /app

# Install ONLY production dependencies. node:20-alpine ships with the
# `node` user (uid 1000) preconfigured; we'll use it for the runtime
# stage below to avoid running as root.
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --no-audit --no-fund

# ---------- Stage 2: runtime ----------
FROM node:20-alpine

ENV NODE_ENV=production
ENV PORT=3001
# Where the docker daemon lives. The compose file bind-mounts the
# host's socket at exactly this path; if you mount elsewhere, set
# DOCKER_SOCKET_PATH at run time.
ENV DOCKER_SOCKET_PATH=/var/run/docker.sock
# The image name we expect to be available on the host's daemon.
# Build it once with `make sandbox` (see root Makefile) before
# starting the backend.
ENV SANDBOX_IMAGE=replit-sandbox
ENV SANDBOX_USER=developer
ENV AUTO_CLEANUP=true

WORKDIR /app

# Production deps only — copied from the deps stage so we don't carry
# the `node_modules` install layer into the final image.
COPY --from=deps /app/node_modules ./node_modules
COPY package.json ./
COPY src ./src

# Use the unprivileged `node` user from the base image.
USER node

EXPOSE 3001

# A quick TCP probe — the server logs "[replit] backend listening" once
# it's up, but a TCP check is the cheapest portable signal.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3001/api/health >/dev/null 2>&1 || exit 1

CMD ["node", "src/server.js"]
