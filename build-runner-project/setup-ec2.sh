#!/usr/bin/env bash
# One-command deploy for a fresh free-tier EC2 instance (Ubuntu 22.04/24.04).
# Run as the default `ubuntu` user, NOT root.
#
#   curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/setup-ec2.sh | bash
#   # or locally:
#   ./setup-ec2.sh
#
# After it finishes, the API is on http://<ec2-public-ip>:8000.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/poridhioss/minions-26.git}"
APP_DIR="$HOME/build-runner-project"
EC2_IP="$(curl -fsSL http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo localhost)"

echo "==> Installing Docker"
sudo apt-get update -y
sudo apt-get install -y docker.io docker-compose-v2 git ufw
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker

echo "==> Opening firewall for ports 8000 (API) and 22 (SSH)"
sudo ufw allow OpenSSH || true
sudo ufw allow 8000/tcp || true
sudo ufw --force enable || true

echo "==> Cloning repo to $APP_DIR"
if [ ! -d "$APP_DIR" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  (cd "$APP_DIR" && git pull)
fi
cd "$APP_DIR"

echo "==> Generating .env (edit before going to production!)"
if [ ! -f .env ]; then
  cat > .env <<EOF
REDIS_HOST=redis
GMAIL_SENDER=${GMAIL_SENDER:-you@gmail.com}
GMAIL_APP_PASSWORD=${GMAIL_APP_PASSWORD:-replace-me}
GMAIL_RECEIVER=${GMAIL_RECEIVER:-you@gmail.com}
API_KEY=$(openssl rand -hex 24)
GITHUB_WEBHOOK_SECRET=$(openssl rand -hex 24)
EOF
  echo "Generated fresh .env with random API_KEY and GITHUB_WEBHOOK_SECRET."
  echo "Edit it now to set your real Gmail app password:"
  echo "  nano $APP_DIR/.env"
fi

echo "==> Building and starting the stack"
docker compose up -d --build
docker compose ps

cat <<EOF

==========================================================
  Build Runner is live!

  API:     http://$EC2_IP:8000
  Health:  curl http://$EC2_IP:8000/

  GitHub webhook setup:
    Payload URL:  http://$EC2_IP:8000/webhook/github
    Content type: application/json
    Secret:       (value of GITHUB_WEBHOOK_SECRET in .env)
    Events:       Just the 'push' event.

  Submit a build:
    curl -X POST -H "X-API-Key: $(grep API_KEY .env | cut -d= -f2)" \\
         "http://$EC2_IP:8000/build?github_url=https://github.com/owner/repo"

  Tail logs:
    docker compose logs -f worker
==========================================================
EOF
