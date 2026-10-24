import re
from pathlib import Path

# Accept the source path so this works both on the VPS (its own tree) and in CI
# (a fresh clone under a temp dir). Hardcoding /opt/angt-glorytun meant the
# build silently targeted a path that does not exist on a runner.
import argparse

_ap = argparse.ArgumentParser()
_ap.add_argument("--src", default="/opt/angt-glorytun/mud/mud.c")
_args = _ap.parse_args()

p = Path(_args.src)
if not p.exists():
    raise SystemExit(f"not found: {p}")
src = p.read_text(encoding="utf-8", errors="replace")

if "int on = 0;" in src:
    print("  002: already has the fixed runtime switch, skipping")
    raise SystemExit(0)

start = src.index("static int\nmud_redundant_enabled(void)")
brace = src.index("{", start)
depth = 0
i = brace
while i < len(src):
    if src[i] == "{":
        depth += 1
    elif src[i] == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
end = i + 1

lines = [
    "static int",
    "mud_redundant_enabled(void)",
    "{",
    "    static int cached = 0;",
    "    static int initialised = 0;",
    "    static time_t last = 0;",
    "",
    "    time_t now = time(NULL);",
    "",
    "    /* Startup default comes from the environment. */",
    "    if (!initialised) {",
    "        const char *env = getenv(\"MUD_REDUNDANT\");",
    "        cached = (env && env[0] == '1') ? 1 : 0;",
    "        initialised = 1;",
    "        last = now;",
    "        return cached;",
    "    }",
    "",
    "    /* Live override: /tmp/mud-redundant containing \"1\" turns duplication",
    "     * on, anything else (or a missing file) turns it off. Re-reading per",
    "     * packet would be far too expensive at a few hundred packets per",
    "     * second, and time() has 1 s resolution, so this costs at most one",
    "     * open per second. */",
    "    if (now == last)",
    "        return cached;",
    "    last = now;",
    "",
    "    /* Recompute from scratch: the file is the only authority.",
    "     *",
    "     * The first version assigned cached only when fgets() succeeded, which",
    "     * made two transitions unreachable:",
    "     *",
    "     *   empty file   -> fgets returns NULL -> cached keeps its old value, so",
    "     *                   `touch /tmp/mud-redundant` never enabled duplication",
    "     *                   (the controller created the flag with `: >`, and",
    "     *                   duplication had never once engaged on this link);",
    "     *   file removed -> fopen returns NULL -> cached keeps 1 for ever, so",
    "     *                   removing the flag never disabled it either.",
    "     *",
    "     * Both directions stuck silently. An explicit 0 each tick makes",
    "     * missing and not-1 both mean OFF, which is what the flag expresses. */",
    "    int on = 0;",
    "    FILE *f = fopen(\"/tmp/mud-redundant\", \"r\");",
    "    if (f) {",
    "        char buf[8];",
    "        memset(buf, 0, sizeof buf);",
    "        if (fgets(buf, sizeof buf, f) && buf[0] == '1')",
    "            on = 1;",
    "        fclose(f);",
    "    }",
    "    cached = on;",
    "",
    "    return cached;",
    "}",
]
new = "\n".join(lines)

src = src[:start] + new + src[end:]
p.write_text(src, encoding="utf-8")
print("patched mud_redundant_enabled")

head = p.read_text(encoding="utf-8")[:3000]
for inc in ("<time.h>", "<stdio.h>", "<string.h>"):
    print("  include %s: %s" % (inc, "yes" if inc in head else "MISSING"))
