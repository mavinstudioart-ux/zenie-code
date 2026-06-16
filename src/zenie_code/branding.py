from __future__ import annotations

import os
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[38;5;51m"
BLUE = "\033[38;5;39m"
PURPLE = "\033[38;5;135m"
MAGENTA = "\033[38;5;207m"
GREEN = "\033[38;5;82m"
YELLOW = "\033[38;5;220m"


ASCII_LINES = [
    "███████╗███████╗███╗   ██╗██╗███████╗",
    "╚══███╔╝██╔════╝████╗  ██║██║██╔════╝",
    "  ███╔╝ █████╗  ██╔██╗ ██║██║█████╗  ",
    " ███╔╝  ██╔══╝  ██║╚██╗██║██║██╔══╝  ",
    "███████╗███████╗██║ ╚████║██║███████╗",
    "╚══════╝╚══════╝╚═╝  ╚═══╝╚═╝╚══════╝",
    "               C  O  D  E              ",
]

GRADIENT = [CYAN, BLUE, PURPLE, MAGENTA, PURPLE, BLUE, CYAN]


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def paint(text: str, color: str, *, bold: bool = False) -> str:
    if not color_enabled():
        return text
    prefix = (BOLD if bold else "") + color
    return prefix + text + RESET


def banner(version: str) -> str:
    if color_enabled():
        art = "\n".join(
            f"{GRADIENT[index]}{line}{RESET}"
            for index, line in enumerate(ASCII_LINES)
        )
    else:
        art = "\n".join(ASCII_LINES)

    subtitle = (
        paint("Local Agentic Coding CLI", CYAN, bold=True)
        + paint(f"  v{version}", PURPLE)
    )
    hint = paint("Type /help to view commands.", DIM)
    return f"{art}\n\n{subtitle}\n{hint}"


def prompt() -> str:
    if not color_enabled():
        return "zenie > "
    return f"{BOLD}{CYAN}zenie{RESET} {PURPLE}❯{RESET} "


def success(text: str) -> str:
    return paint(text, GREEN)


def warning(text: str) -> str:
    return paint(text, YELLOW)


def heading(text: str) -> str:
    return paint(text, CYAN, bold=True)
