#!/bin/bash
# One-time setup for the Smithsonian POC demo. Safe to run again: it skips whatever is already done.
#
#   ./bootstrap.sh                    # set up in ~/smithsonian-poc
#   SI_WORKDIR=~/code/si ./bootstrap.sh
#   ./bootstrap.sh --rebuild          # rebuild the app even if it is already built
#
# It checks your tools, gets the ThinkingSense Server code, builds it, downloads the three small models, and
# creates a launcher called "demo" that always runs the demo with Java 21. When it finishes it tells you the one
# command to run next. Needs a Mac (Homebrew) or Linux with the same tools; the fixes it prints are Homebrew commands.
set -u
WORK="${SI_WORKDIR:-$HOME/smithsonian-poc}"
MODELS="${OMNIGATE_MODELS_DIR:-$HOME/.cache/omnigate-models}"
REBUILD=0; [ "${1:-}" = "--rebuild" ] && REBUILD=1
MISSING=0
say() { printf '%s\n' "$*"; }
ok()  { say "  ok       $1"; }
bad() { say "  MISSING  $1"; say "           fix: $2"; MISSING=1; }

say "ThinkingSense Smithsonian POC: one-time setup"
say "Working folder: $WORK"
say ""
say "1. Checking your tools"

# Java 21 specifically. The demo is built and tested on 21; a newer default Java (for example 25 or 27) is a common cause of
# confusing failures, so we find a 21 and use it for everything, whatever your default Java is.
JAVA21=""
for c in "${JAVA_HOME:-}" "$(/usr/libexec/java_home -v 21 2>/dev/null)" "$(brew --prefix openjdk@21 2>/dev/null)" /opt/homebrew/opt/openjdk@21 /usr/local/opt/openjdk@21 /usr/lib/jvm/java-21-openjdk-amd64 /usr/lib/jvm/java-21-openjdk-arm64; do
  [ -n "$c" ] && [ -x "$c/bin/java" ] && "$c/bin/java" -version 2>&1 | head -1 | grep -q '"21' && { JAVA21="$c"; break; }
done
if [ -n "$JAVA21" ]; then ok "Java 21 ($JAVA21)"; else bad "Java 21" "brew install openjdk@21"; fi
command -v mvn >/dev/null && ok "Maven" || bad "Maven" "brew install maven"
if command -v node >/dev/null; then
  NV="$(node -v | sed 's/v\([0-9]*\).*/\1/')"; [ "$NV" -ge 20 ] && ok "Node $(node -v)" || bad "Node 20 or later (you have $(node -v))" "brew install node"
else bad "Node" "brew install node"; fi
command -v git >/dev/null && ok "git" || bad "git" "xcode-select --install"
command -v curl >/dev/null && ok "curl" || bad "curl" "brew install curl"
command -v python3 >/dev/null && ok "python3" || bad "python3" "brew install python"
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then ok "Docker (runs the local MinIO that stands in for object storage)"; else bad "Docker, installed and running" "install Docker Desktop and start it"; fi
command -v llama-server >/dev/null && ok "llama-server" || bad "llama-server (llama.cpp)" "brew install llama.cpp"
command -v psql >/dev/null || { [ -x /opt/homebrew/opt/postgresql@16/bin/psql ] && export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"; }
if command -v psql >/dev/null; then
  if psql -h 127.0.0.1 -d postgres -Atc "select 1" >/dev/null 2>&1; then ok "PostgreSQL is running and lets you in without a password"
  else bad "PostgreSQL on 127.0.0.1:5432 that lets your own user in without a password" "brew install postgresql@16 && brew services start postgresql@16   (then test: psql -h 127.0.0.1 -d postgres -c 'select 1')"; fi
else bad "PostgreSQL (the psql command)" "brew install postgresql@16 && brew services start postgresql@16"; fi
if [ "$MISSING" = 1 ]; then say ""; say "Fix the MISSING items above, then run ./bootstrap.sh again."; exit 1; fi

say ""; say "2. Getting the ThinkingSense Server code"
mkdir -p "$WORK"
if [ -d "$WORK/Server/.git" ]; then ok "already at $WORK/Server (branch $(git -C "$WORK/Server" branch --show-current))"
else
  git clone https://github.com/thinkingsense-ai/Server.git "$WORK/Server" 2>&1 | tail -2
  [ -d "$WORK/Server/.git" ] || { say "  The clone failed. The Server repository is private: you need access to github.com/thinkingsense-ai/Server and to be signed in (run: gh auth login)."; exit 1; }
fi
DEMO="$WORK/Server/demo-smithsonian-poc"
[ -x "$DEMO/demo.sh" ] || chmod +x "$DEMO"/*.sh 2>/dev/null
[ -f "$DEMO/demo.sh" ] || { say "  $DEMO/demo.sh is missing: this branch of Server does not have the Smithsonian demo."; exit 1; }

say ""; say "3. Building the app (about 5 to 10 minutes the first time)"
if [ -f "$WORK/Server/target/omnigate.jar" ] && [ "$REBUILD" = 0 ]; then ok "already built ($WORK/Server/target/omnigate.jar). Use --rebuild to build again."
else
  export JAVA_HOME="$JAVA21"; export PATH="$JAVA_HOME/bin:$PATH"
  ( cd "$WORK/Server/web" && npm ci --no-audit --no-fund && npm run build ) >"$WORK/build-web.log" 2>&1 && ok "web screens built" || { say "  The web build failed. See $WORK/build-web.log"; exit 1; }
  ( cd "$WORK/Server" && mvn -q -DskipTests package ) >"$WORK/build-app.log" 2>&1 && ok "app built" || { say "  The app build failed. See $WORK/build-app.log"; exit 1; }
fi

say ""; say "4. Downloading the three small models (about 1.6 GB, once)"
mkdir -p "$MODELS"
for pair in "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf|Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF" "qwen2.5-0.5b-instruct-q4_k_m.gguf|Qwen/Qwen2.5-0.5B-Instruct-GGUF" "nomic-embed-text-v1.5.Q4_K_M.gguf|nomic-ai/nomic-embed-text-v1.5-GGUF"; do
  f="${pair%%|*}"; repo="${pair##*|}"
  if [ -s "$MODELS/$f" ] && [ ! -e "$MODELS/$f.part" ]; then ok "$f"
  else
    say "  downloading $f ..."
    curl -fL --retry 3 -C - -s -S -o "$MODELS/$f.part" "https://huggingface.co/$repo/resolve/main/$f" && mv "$MODELS/$f.part" "$MODELS/$f" && ok "$f" || { say "  The download of $f failed. Run ./bootstrap.sh again to resume."; exit 1; }
  fi
done

say ""; say "5. Creating the launcher"
cat > "$WORK/demo" <<L
#!/bin/bash
# Runs the demo helper with Java 21, from the right folder, whatever your default Java is.
export JAVA_HOME="$JAVA21"
export PATH="\$JAVA_HOME/bin:/opt/homebrew/opt/postgresql@16/bin:\$PATH"
cd "$DEMO" || exit 1
exec ./demo.sh "\$@"
L
chmod +x "$WORK/demo"; ok "$WORK/demo"

say ""
say "All set. Next:"
say "    $WORK/demo check     # optional: confirms everything"
say "    $WORK/demo up        # starts the demo (about 30 seconds)"
say "Then open the addresses it prints. Stop with:  $WORK/demo stop"
