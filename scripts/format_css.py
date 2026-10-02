"""One-time readable formatting for the project's dependency-free CSS files."""
from pathlib import Path


def format_css(source):
    output, line = [], []
    indent = depth = 0
    quote = None
    comment = False
    escaped = False
    i = 0

    def flush():
        text = "".join(line).strip()
        if text:
            output.append("  " * indent + text)
        line.clear()

    while i < len(source):
        char = source[i]
        if comment:
            line.append(char)
            if source[i:i + 2] == "*/":
                line.append("/")
                i += 1
                comment = False
                flush()
        elif quote:
            line.append(char)
            if char == quote and not escaped:
                quote = None
            escaped = char == "\\" and not escaped
        elif source[i:i + 2] == "/*":
            flush()
            line.extend(["/", "*"])
            i += 1
            comment = True
        elif char in "\"'":
            quote = char
            escaped = False
            line.append(char)
        elif char == "(":
            depth += 1
            line.append(char)
        elif char == ")":
            depth -= 1
            line.append(char)
        elif char == "{" and not depth:
            line.append(" {")
            flush()
            indent += 1
        elif char == "}" and not depth:
            flush()
            indent = max(0, indent - 1)
            output.append("  " * indent + "}")
        elif char == ";" and not depth:
            line.append(char)
            flush()
        elif char in "\r\n":
            if line:
                line.append(" ")
        else:
            line.append(char)
        i += 1
    flush()
    return "\n".join(output) + "\n"


if __name__ == "__main__":
    import sys
    for name in sys.argv[1:]:
        path = Path(name)
        path.write_text(format_css(path.read_text()))
