"""US-layout key maps and resolver for real CDP key-event typing.

Mapped characters are dispatched as keyDown (with text) + keyUp, with Shift
wrapping when needed. Unmapped characters (Unicode, emoji, dead-key output)
fall back to Input.insertText.
"""
from .. import cdp

KEYBOARD_LAYOUT = {
    "a": "KeyA", "b": "KeyB", "c": "KeyC", "d": "KeyD", "e": "KeyE", "f": "KeyF",
    "g": "KeyG", "h": "KeyH", "i": "KeyI", "j": "KeyJ", "k": "KeyK", "l": "KeyL",
    "m": "KeyM", "n": "KeyN", "o": "KeyO", "p": "KeyP", "q": "KeyQ", "r": "KeyR",
    "s": "KeyS", "t": "KeyT", "u": "KeyU", "v": "KeyV", "w": "KeyW", "x": "KeyX",
    "y": "KeyY", "z": "KeyZ",
    "0": "Digit0", "1": "Digit1", "2": "Digit2", "3": "Digit3", "4": "Digit4",
    "5": "Digit5", "6": "Digit6", "7": "Digit7", "8": "Digit8", "9": "Digit9",
    " ": "Space", "\n": "Enter", "\r": "Enter", "\t": "Tab",
    ".": "Period", ",": "Comma", "-": "Minus", "=": "Equal", "/": "Slash",
    "\\": "Backslash", ";": "Semicolon", "'": "Quote",
    "[": "BracketLeft", "]": "BracketRight", "`": "Backquote",
    "@": "Digit2", "!": "Digit1", "#": "Digit3", "$": "Digit4", "%": "Digit5",
    "^": "Digit6", "&": "Digit7", "*": "Digit8", "(": "Digit9", ")": "Digit0",
    "_": "Minus", "+": "Equal",
}

SHIFT_CHARS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+{}|:"<>?~')

VK_CODES = {
    "0": 48, "1": 49, "2": 50, "3": 51, "4": 52, "5": 53, "6": 54,
    "7": 55, "8": 56, "9": 57,
    "a": 65, "b": 66, "c": 67, "d": 68, "e": 69, "f": 70, "g": 71,
    "h": 72, "i": 73, "j": 74, "k": 75, "l": 76, "m": 77, "n": 78,
    "o": 79, "p": 80, "q": 81, "r": 82, "s": 83, "t": 84, "u": 85,
    "v": 86, "w": 87, "x": 88, "y": 89, "z": 90,
    " ": 32, "\n": 13, "\r": 13, "\t": 9,
    ".": 190, ",": 188, "-": 189, "=": 187, "/": 191, "\\": 220,
    ";": 186, "'": 222, "`": 192, "[": 219, "]": 221,
    "@": 50, "!": 49, "#": 51, "$": 52, "%": 53, "^": 54, "&": 55,
    "*": 56, "(": 57, ")": 48, "_": 189, "+": 187,
    "{": 219, "}": 221, "|": 220, ":": 186, '"': 222,
    "<": 188, ">": 190, "?": 191, "~": 192,
}


def resolve_key(char):
    """Return (code, key, vk, needs_shift) for a US-layout char, else None."""
    if char.isalpha():
        code = KEYBOARD_LAYOUT.get(char.lower())
    else:
        code = KEYBOARD_LAYOUT.get(char)
    if code is None:
        return None
    if char in ("\n", "\r"):
        return ("Enter", "Enter", 13, False)
    if char == "\t":
        return ("Tab", "Tab", 9, False)
    vk = VK_CODES[char.lower() if char.isalpha() else char]
    return (code, char, vk, char in SHIFT_CHARS)


def dispatch_key(tab, char):
    """Dispatch keyDown + keyUp (with Shift wrapping) for one mapped char."""
    code, key_val, vk, needs_shift = resolve_key(char)
    text_val = "\r" if char in ("\n", "\r") else char
    modifiers = 8 if needs_shift else 0
    if needs_shift:
        tab.send(
            cdp.input_.dispatch_key_event(
                "rawKeyDown",
                code="ShiftLeft",
                key="Shift",
                windows_virtual_key_code=16,
                native_virtual_key_code=16,
                modifiers=8,
                location=1,
            )
        )
    tab.send(
        cdp.input_.dispatch_key_event(
            "keyDown",
            text=text_val,
            unmodified_text=char,
            code=code,
            key=key_val,
            windows_virtual_key_code=vk,
            native_virtual_key_code=vk,
            modifiers=modifiers,
        )
    )
    tab.send(
        cdp.input_.dispatch_key_event(
            "keyUp",
            code=code,
            key=key_val,
            windows_virtual_key_code=vk,
            native_virtual_key_code=vk,
            modifiers=modifiers,
        )
    )
    if needs_shift:
        tab.send(
            cdp.input_.dispatch_key_event(
                "keyUp",
                code="ShiftLeft",
                key="Shift",
                windows_virtual_key_code=16,
                native_virtual_key_code=16,
                location=1,
            )
        )


def type_text(tab, text):
    """Type ``text`` via real key events, collapsing ``\\r\\n`` to one Enter."""
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        crlf = char == "\r" and i + 1 < n and text[i + 1] == "\n"
        if resolve_key(char) is None:
            tab.send(cdp.input_.insert_text(char))
        else:
            dispatch_key(tab, char)
        i += 2 if crlf else 1
