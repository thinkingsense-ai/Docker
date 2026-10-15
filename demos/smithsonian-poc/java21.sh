#!/bin/bash
# Prints the path of a Java 21 `java` binary, or nothing (and exits 1) when there is none.
# Looks at, in order: $JAVA_HOME, macOS's /usr/libexec/java_home -v 21, then `java` on the PATH.
# Sourced/run by demo.sh and launch.sh so `check` and the real launch use the same Java.
is21() { [ -x "$1" ] && "$1" -version 2>&1 | head -1 | grep -Eq '"21(\.|")'; }
for candidate in "${JAVA_HOME:+$JAVA_HOME/bin/java}" \
                 "$( [ -x /usr/libexec/java_home ] && /usr/libexec/java_home -v 21 2>/dev/null | sed 's|$|/bin/java|' )" \
                 "$(command -v java 2>/dev/null)"; do
  [ -n "$candidate" ] && is21 "$candidate" && { printf '%s\n' "$candidate"; exit 0; }
done
exit 1
