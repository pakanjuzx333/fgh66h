#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR="/opt/telegram-ai-manager"; SERVICE="telegram-ai-manager"
[[ $EUID -eq 0 ]] || { echo "Run as root: sudo bash setup.sh"; exit 1; }
source /etc/os-release
case "${ID:-}" in ubuntu|debian) ;; *) echo "This installer supports Ubuntu/Debian."; exit 1;; esac
apt-get update
apt-get install -y python3 python3-venv python3-pip postgresql postgresql-contrib git build-essential cmake libopenblas-dev wget curl
if ! command -v python3.11 >/dev/null; then
  if [[ "${ID:-}" == "ubuntu" ]]; then
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa; apt-get update; apt-get install -y python3.11 python3.11-venv
  else
    apt-get install -y python3.11 python3.11-venv
  fi
fi
command -v python3.11 >/dev/null || { echo "Python 3.11 could not be installed."; exit 1; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$INSTALL_DIR"; cp -a "$SCRIPT_DIR/." "$INSTALL_DIR/"; cd "$INSTALL_DIR"
read -rp "Telegram bot token: " TOKEN
read -rp "Target group/channel ID: " GROUP_ID
read -rp "Admin Telegram IDs (comma-separated): " ADMINS
read -rp "LLM mode [local/api]: " MODE; MODE="${MODE:-local}"
[[ "$MODE" == local || "$MODE" == api ]] || { echo "LLM mode must be local or api"; exit 1; }
read -rp "Community name: " COMMUNITY; read -rp "Project description: " DESCRIPTION
DB_PASSWORD="$(openssl rand -hex 20)"; DB_NAME=telegram_bot_db; DB_USER=botuser
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD'; END IF; END \$\$;
SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
SQL
GEMINI=""; OPENAI=""
if [[ "$MODE" == local ]]; then
 mkdir -p models; MODEL=models/phi-3-mini-q4.gguf
 [[ -f "$MODEL" ]] || wget -O "$MODEL" "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf"
else
 read -rp "Provider [gemini/openai]: " PROVIDER
 if [[ "$PROVIDER" == gemini ]]; then read -rsp "Gemini API key: " GEMINI; echo; else read -rsp "OpenAI API key: " OPENAI; echo; fi
fi
cat > .env <<ENV
TELEGRAM_BOT_TOKEN=$TOKEN
TELEGRAM_GROUP_ID=$GROUP_ID
ADMIN_USER_IDS=$ADMINS
LLM_MODE=$MODE
LOCAL_MODEL_PATH=./models/phi-3-mini-q4.gguf
LOCAL_MODEL_CONTEXT_LENGTH=4096
LOCAL_MODEL_MAX_TOKENS=512
LOCAL_MODEL_TEMPERATURE=0.7
LOCAL_MODEL_THREADS=4
GOOGLE_GEMINI_API_KEY=$GEMINI
OPENAI_API_KEY=$OPENAI
OPENAI_BASE_URL=https://api.openai.com/v1
DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
MAX_CHAT_HISTORY=50
SESSION_TIMEOUT_MINUTES=60
MUTE_DURATION_MINUTES=60
LOG_LEVEL=INFO
LOG_FILE=logs/telegram-ai-manager.log
ENV
python3.11 -m venv .venv; .venv/bin/pip install --upgrade pip
CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" .venv/bin/pip install -r requirements.txt
.venv/bin/python - <<PY
import yaml
p='config.yaml'; d=yaml.safe_load(open(p)); d['community']['name']=${COMMUNITY@Q}; d['community']['project_description']=${DESCRIPTION@Q}; yaml.safe_dump(d, open(p,'w'), sort_keys=False)
PY
useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin botuser 2>/dev/null || true
chown -R botuser:botuser "$INSTALL_DIR"; chmod 600 .env
.venv/bin/python -c 'import asyncio; from src.db.database import init_database; asyncio.run(init_database())'
cp systemd/telegram-ai-manager.service /etc/systemd/system/"$SERVICE".service
systemctl daemon-reload; systemctl enable --now "$SERVICE"
systemctl --no-pager --full status "$SERVICE" || true
echo "Installation complete. Check logs with: journalctl -u $SERVICE -f"
