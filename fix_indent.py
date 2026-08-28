"""fix_indent.py - repair a Python file that picked up a leading indent
on the way into an editor.

Two things go wrong when code is pasted rather than uploaded:

  every line indented   the paste landed inside an indented block, so
                        the whole file shifted right by the same amount

  only line 1 indented  the editor auto-indented the first line and
                        left the rest alone

Both produce "IndentationError: unexpected indent" pointing at line 1,
because line 1 is simply where Python trips first. They need different
repairs, so this checks which one happened before touching anything.

    python3 fix_indent.py _theme.py
"""
import ast
import sys


def main(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()

    # A byte order mark is a different failure with a different message,
    # but it costs nothing to clear it while we are here.
    if src.startswith("﻿"):
        src = src.lstrip("﻿")
        print("removed a byte order mark")

    lines = src.split("\n")
    body = [l for l in lines if l.strip()]
    if not body:
        print("file is empty")
        return 1

    common = min(len(l) - len(l.lstrip()) for l in body)

    if common > 0:
        # the whole file shifted: take the same amount off every line so
        # the internal indentation is preserved
        lines = [l[common:] if l[:common].strip() == "" else l.lstrip()
                 for l in lines]
        print("the whole file was indented by %d spaces, removed from "
              "every line" % common)
    elif lines[0][:1] in (" ", "\t"):
        lines[0] = lines[0].lstrip()
        print("only line 1 was indented, stripped it")
    else:
        print("no leading indent found, the problem is somewhere else")

    out = "\n".join(lines)
    try:
        ast.parse(out)
    except SyntaxError as e:
        print("STILL BROKEN: line %s: %s" % (e.lineno, e.msg))
        print("not writing the file, so nothing is made worse")
        return 1

    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print("repaired, and the file now parses")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "_theme.py"))
