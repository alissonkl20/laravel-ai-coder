#!/usr/bin/env bash
# Inicia o DRAXY (agent CLI) com venv ativado.
# Uso:
#   ./initial.sh my-app              # abre agent no projeto my-app
#   ./initial.sh -p my-app
#   ./initial.sh -w ~/Documentos/my-app
#   ./initial.sh --here              # terminal atual

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ -f ".env" ]]; then
  # shellcheck source=/dev/null
  set -a
  source ".env"
  set +a
fi
AGENT_NAME="${AGENT_NAME:-DRAXY}"

FORCE_HERE=false
AGENT_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --here)
      FORCE_HERE=true
      ;;
    *)
      AGENT_ARGS+=("$arg")
      ;;
  esac
done

# Primeiro argumento sem "-" = nome do projeto em ~/Documentos
if [[ ${#AGENT_ARGS[@]} -gt 0 && "${AGENT_ARGS[0]}" != -* ]]; then
  AGENT_ARGS=(-p "${AGENT_ARGS[0]}" "${AGENT_ARGS[@]:1}")
fi

_run_agent() {
  if [[ ! -d ".venv" ]]; then
    echo "Erro: .venv não encontrado em ${PROJECT_DIR}"
    echo "Crie o ambiente virtual (veja README.md — Instalação)."
    return 1
  fi

  # shellcheck source=/dev/null
  source ".venv/bin/activate"

  if [[ ! -f "agent_cli.py" ]]; then
    echo "Erro: agent_cli.py não encontrado."
    return 1
  fi

  # Boot limpo: sem path/python/Unsloth — só splash ASCII + banner no agent_cli
  exec python agent_cli.py "${AGENT_ARGS[@]}"
}

_open_terminal() {
  local cmd
  cmd="cd '${PROJECT_DIR}' && bash '${PROJECT_DIR}/initial.sh' --here"
  if [[ ${#AGENT_ARGS[@]} -gt 0 ]]; then
  cmd+=" $(printf '%q ' "${AGENT_ARGS[@]}")"
  fi
  cmd+="; echo; read -p 'Pressione Enter para fechar...'"

  if command -v gnome-terminal >/dev/null 2>&1; then
    exec gnome-terminal --working-directory="${PROJECT_DIR}" --title="${AGENT_NAME}" -- bash -c "${cmd}"
  fi

  if command -v konsole >/dev/null 2>&1; then
    exec konsole --workdir "${PROJECT_DIR}" -p tabtitle="${AGENT_NAME}" -e bash -c "${cmd}"
  fi

  if command -v xfce4-terminal >/dev/null 2>&1; then
    exec xfce4-terminal --working-directory="${PROJECT_DIR}" --title="${AGENT_NAME}" -e bash -c "${cmd}"
  fi

  if command -v x-terminal-emulator >/dev/null 2>&1; then
    exec x-terminal-emulator -e bash -c "${cmd}"
  fi

  echo "Nenhum emulador de terminal encontrado (gnome-terminal, konsole, xfce4-terminal)."
  echo "Rodando no shell atual..."
  _run_agent
}

chmod_self() {
  chmod +x "${PROJECT_DIR}/initial.sh" 2>/dev/null || true
}

chmod_self

if [[ "${FORCE_HERE}" == true ]] || [[ -t 0 && -t 1 ]]; then
  _run_agent
else
  _open_terminal
fi
