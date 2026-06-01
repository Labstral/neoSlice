#!/bin/bash
# Injecte le contexte git au démarrage de chaque session

BRANCH=$(git branch --show-current 2>/dev/null || echo "inconnu")
MODIFIED=$(git status --short 2>/dev/null | wc -l | tr -d ' ')
LAST_COMMIT=$(git log --oneline -1 2>/dev/null || echo "aucun commit")
STASH_COUNT=$(git stash list 2>/dev/null | wc -l | tr -d ' ')

jq -n \
  --arg branch "$BRANCH" \
  --arg modified "$MODIFIED" \
  --arg last "$LAST_COMMIT" \
  --arg stash "$STASH_COUNT" \
  '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: ("=== Contexte neoSlice ===\nBranche : " + $branch + "\nFichiers modifiés : " + $modified + "\nDernier commit : " + $last + "\nStashs : " + $stash)
    }
  }'
