#!/usr/bin/env bash
# =============================================================================
#  modal_service.sh — Manage the Modal service (pricer-service)
# =============================================================================
#
# Usage:
#   ./tools/modal_service.sh deploy     → Deploy (or update) the service
#   ./tools/modal_service.sh status     → Show the status of Modal apps
#   ./tools/modal_service.sh logs       → Stream live logs
#   ./tools/modal_service.sh stop       → Stop the app on Modal
#   ./tools/modal_service.sh warm       → Keep the instance warm (loop)
#   ./tools/modal_service.sh ping       → Send a single wake-up ping
#   ./tools/modal_service.sh help       → Show this help message
#
# =============================================================================

set -euo pipefail

# --- Colors ---
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

APP_NAME="pricer-service"
SERVICE_FILE="pricer_service.py"

# Change to the exercise root directory (one level above tools/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXERCISE_DIR="$(dirname "$SCRIPT_DIR")"
cd "$EXERCISE_DIR"

print_header() {
    echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════${RESET}"
    echo -e "${BOLD}${CYAN}  Modal Service Manager — ${APP_NAME}${RESET}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════${RESET}\n"
}

cmd_deploy() {
    echo -e "${GREEN}🚀 Deploying '${APP_NAME}' to Modal...${RESET}"
    echo -e "${YELLOW}   This may take several minutes on first run.${RESET}\n"
    modal deploy "$SERVICE_FILE"
    echo -e "\n${GREEN}✅ Service deployed successfully.${RESET}"
    echo -e "${CYAN}   🌐 View at: https://modal.com/apps/repson0/main/deployed/${APP_NAME}${RESET}"
}

cmd_status() {
    echo -e "${CYAN}📊 Current status of Modal apps:${RESET}\n"
    modal app list
}

cmd_logs() {
    echo -e "${CYAN}📋 Streaming live logs for '${APP_NAME}' (Ctrl+C to exit):${RESET}\n"
    modal app logs "$APP_NAME"
}

cmd_stop() {
    echo -e "${RED}🛑 Stopping '${APP_NAME}' on Modal...${RESET}"
    modal app stop "$APP_NAME"
    echo -e "${GREEN}✅ App stopped.${RESET}"
}

cmd_warm() {
    echo -e "${YELLOW}🔥 Keeping instance warm (Ctrl+C to exit)...${RESET}\n"
    python keep_warm.py
}

cmd_ping() {
    echo -e "${CYAN}🏓 Sending a single ping to the Modal service...${RESET}"
    python - <<'EOF'
import modal
Pricer = modal.Cls.from_name("pricer-service", "Pricer")
pricer = Pricer()
reply = pricer.wake_up.remote()
print(f"✅ Service response: {reply}")
EOF
}

print_help() {
    echo -e "${BOLD}Usage:${RESET}"
    echo -e "  ${CYAN}./tools/modal_service.sh${RESET} ${YELLOW}<command>${RESET}\n"
    echo -e "${BOLD}Available commands:${RESET}"
    echo -e "  ${YELLOW}deploy${RESET}   → Deploy or update the service on Modal"
    echo -e "  ${YELLOW}status${RESET}   → List all active apps in your Modal account"
    echo -e "  ${YELLOW}logs${RESET}     → Stream live logs from the app"
    echo -e "  ${YELLOW}stop${RESET}     → Stop the app (frees GPU resources and avoids costs)"
    echo -e "  ${YELLOW}warm${RESET}     → Keep the instance warm in a loop (every 30s)"
    echo -e "  ${YELLOW}ping${RESET}     → Send a single wake_up test call"
    echo -e "  ${YELLOW}help${RESET}     → Show this help message\n"
}

# --- Entry point ---
print_header

COMMAND="${1:-help}"

case "$COMMAND" in
    deploy) cmd_deploy ;;
    status) cmd_status ;;
    logs)   cmd_logs   ;;
    stop)   cmd_stop   ;;
    warm)   cmd_warm   ;;
    ping)   cmd_ping   ;;
    help|*) print_help ;;
esac
