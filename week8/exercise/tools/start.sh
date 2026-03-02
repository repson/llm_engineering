#!/usr/bin/env bash
# =============================================================================
#  start.sh — Launch the full "The Price is Right" application
# =============================================================================
#
# Usage:
#   ./tools/start.sh            → Launch the full UI (Gradio + agents)
#   ./tools/start.sh headless   → Run the agent framework only, without UI
#   ./tools/start.sh warm       → Launch UI and keep Modal warm in parallel
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

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXERCISE_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$(dirname "$(dirname "$EXERCISE_DIR")")/.venv"   # llm_engineering/.venv

print_header() {
    echo -e "\n${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
    echo -e "${BOLD}${CYAN}       The Price is Right — Agent Framework   ${RESET}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}\n"
}

check_env() {
    echo -e "${CYAN}Checking environment...${RESET}"

    # Activate venv if not already active
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        if [[ -f "$VENV_DIR/bin/activate" ]]; then
            echo -e "   Activating virtual environment: ${YELLOW}${VENV_DIR}${RESET}"
            source "$VENV_DIR/bin/activate"
        else
            echo -e "${RED}   Virtual environment not found at: ${VENV_DIR}${RESET}"
            echo -e "${YELLOW}   Activate it manually: source .venv/bin/activate${RESET}"
            exit 1
        fi
    else
        echo -e "   Virtual environment active: ${GREEN}${VIRTUAL_ENV}${RESET}"
    fi

    # Check that .env file exists
    ENV_FILE="$(dirname "$(dirname "$EXERCISE_DIR")")/.env"
    if [[ -f "$ENV_FILE" ]]; then
        echo -e "   .env file found: ${GREEN}${ENV_FILE}${RESET}"
    else
        echo -e "${YELLOW}   .env file not found at: ${ENV_FILE}${RESET}"
    fi

    # Check that the Modal service is deployed
    echo -e "   Checking Modal service (pricer-service)..."
    if modal app list 2>/dev/null | grep -q "pricer-service"; then
        echo -e "   Modal service: ${GREEN}Deployed${RESET}"
    else
        echo -e "   Modal service: ${YELLOW}Not detected — run: ./tools/modal_service.sh deploy${RESET}"
    fi

    echo ""
}

start_ui() {
    echo -e "${GREEN}Launching Gradio UI...${RESET}"
    echo -e "${YELLOW}   The UI will open automatically in your browser.${RESET}"
    echo -e "${CYAN}   Local access: http://127.0.0.1:7860${RESET}\n"
    cd "$EXERCISE_DIR"
    python price_is_right_final.py
}

start_headless() {
    echo -e "${GREEN}Running agent framework (headless, no UI)...${RESET}\n"
    cd "$EXERCISE_DIR"
    python deal_agent_framework.py
}

start_with_warm() {
    echo -e "${GREEN}Starting UI + keep_warm in parallel...${RESET}"
    echo -e "${YELLOW}   Press Ctrl+C to stop both processes.${RESET}\n"
    cd "$EXERCISE_DIR"

    # Start keep_warm in the background
    python keep_warm.py &
    WARM_PID=$!
    echo -e "${CYAN}   keep_warm started (PID: ${WARM_PID})${RESET}"

    # Cleanup on exit: kill keep_warm when the script is interrupted
    trap "echo -e '\n${RED}Shutting down...${RESET}'; kill $WARM_PID 2>/dev/null; exit 0" INT TERM

    # Start the UI in the foreground
    python price_is_right_final.py

    # If the UI exits normally, kill keep_warm too
    kill $WARM_PID 2>/dev/null || true
}

# --- Entry point ---
print_header
check_env

MODE="${1:-ui}"

case "$MODE" in
    ui|"")      start_ui        ;;
    headless)   start_headless  ;;
    warm)       start_with_warm ;;
    *)
        echo -e "${RED}Unknown mode: '$MODE'${RESET}"
        echo -e "${YELLOW}Available modes: ui, headless, warm${RESET}"
        exit 1
        ;;
esac
