#!/usr/bin/env bash
# v0.51 demo recording script. Runs the lazy-mode trio so termtosvg can
# capture the actual terminal output. Sleeps add visual pacing between
# commands; remove them if you want a faster recording.
set -u

# Colorize prompt for visual clarity in the SVG
PS1='\[\033[1;36m\]$ \[\033[0m\]'

clear
sleep 0.5

# 1. Plan first — AI agents ask before they act (v0.50)
echo -e "\033[1;36m$ \033[0mresearch-hub plan \"I want to learn harness engineering\""
sleep 0.3
research-hub plan "I want to learn harness engineering" 2>/dev/null
sleep 1.5

# 2. Cached crystal answer (~1 KB, < 1s, no LLM call)
echo
echo -e "\033[1;36m$ \033[0mresearch-hub ask llm-evaluation-harness \"what is the SOTA?\""
sleep 0.3
research-hub ask llm-evaluation-harness "what is the SOTA?" 2>/dev/null | python -c "import sys, json; r = json.load(sys.stdin); print(r['answer'])"
sleep 1.5

# 3. New web-search backend (v0.51) — works without API key
echo
echo -e "\033[1;36m$ \033[0mresearch-hub websearch \"kepano obsidian bases\" --limit 3 --json"
sleep 0.3
research-hub websearch "kepano obsidian bases" --limit 3 --json 2>/dev/null | python -c "
import sys, json
results = json.load(sys.stdin)['results']
for r in results:
    print(f\"  [{r['venue']}] {r['title'][:65]}\")
"
sleep 1.5

echo
echo -e "\033[1;32m# Done. 3 lazy-mode entry points, 0 API key required.\033[0m"
sleep 1
