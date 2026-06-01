#!/bin/bash
# Bloque uniquement les commandes vraiment destructives
# Utilise Python pour parser le JSON (jq non requis sur Windows)

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | python -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get('tool_input', {}).get('command', ''))
except Exception:
    pass
" 2>/dev/null)

[ -z "$COMMAND" ] && exit 0

deny() {
  python -c "
import json, sys
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': sys.argv[1]}}))" "$1" 2>/dev/null
  exit 2
}

# ── Règle 1 : rm -rf seulement (pas rm -f) ───────────────────────────────
# Autorisé : "rm -f dist/neoSlice.exe"
# Bloqué   : "rm -rf ..." hors /tmp
case "$COMMAND" in
  *"rm -rf"*|*"rm -rF"*|*"rm -Rf"*|*"rm -RF"*)
    case "$COMMAND" in
      *"/tmp/"*|*"/temp/"*) ;;  # autorisé dans /tmp
      *) deny "rm -rf bloque - suppression recursive interdite hors /tmp" ;;
    esac
    ;;
esac

# ── Règle 2 : git push --force vers main/master ───────────────────────────
case "$COMMAND" in
  *"git push"*"--force"*)
    case "$COMMAND" in
      *" main"*|*" master"*|*"/main"*|*"/master"*)
        deny "Force push vers main/master bloque" ;;
    esac
    ;;
esac

exit 0
