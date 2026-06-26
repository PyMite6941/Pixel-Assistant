"""
Text utility tools for Pixel Assistant.
Encode/decode, regex testing, diff, flip, lorem ipsum.
"""
import base64
import difflib
import re
import urllib.parse
from pathlib import Path

_HERE = Path(__file__).parent

_LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
    "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
    "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
    "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in "
    "culpa qui officia deserunt mollit anim id est laborum."
)

_FLIP_MAP = str.maketrans({
    "a": "ɐ", "b": "q", "c": "ɔ", "d": "p", "e": "ǝ", "f": "ɟ",
    "g": "ɓ", "h": "ɥ", "i": "ᴉ", "j": "ɾ", "k": "ʞ", "l": "l",
    "m": "ɯ", "n": "u", "o": "o", "p": "d", "q": "b", "r": "ɹ",
    "s": "s", "t": "ʇ", "u": "n", "v": "ʌ", "w": "ʍ", "x": "x",
    "y": "ʎ", "z": "z",
    "A": "∀", "B": "q", "C": "Ɔ", "D": "p", "E": "Ǝ", "F": "Ⅎ",
    "G": "⅁", "H": "H", "I": "I", "J": "ſ", "K": "ʞ", "L": "˥",
    "M": "W", "N": "N", "O": "O", "P": "Ԁ", "Q": "Q", "R": "R",
    "S": "S", "T": "┴", "U": "∩", "V": "Λ", "W": "M", "X": "X",
    "Y": "⅄", "Z": "Z",
    "0": "0", "1": "Ꞁ", "2": "ᘔ", "3": "Ɛ", "4": "ᔭ",
    "5": "S", "6": "9", "7": "ㄥ", "8": "8", "9": "6",
    ".": "˙", ",": "'", "'": ",", '"': "„",
    "!": "¡", "?": "¿", "(": ")", ")": "(",
    "[": "]", "]": "[", "{": "}", "}": "{",
    "<": ">", ">": "<", "_": "‾",
})


def encode_text(method: str, text: str) -> str:
    """Encode text using base64, url, or hex encoding."""
    m = method.lower()
    if m == "base64":
        return base64.b64encode(text.encode()).decode()
    if m == "url":
        return urllib.parse.quote(text)
    if m == "hex":
        return text.encode().hex()
    return f"Unknown method '{method}'. Use: base64  url  hex"


def decode_text(method: str, text: str) -> str:
    """Decode text using base64, url, or hex encoding."""
    m = method.lower()
    try:
        if m == "base64":
            return base64.b64decode(text).decode()
        if m == "url":
            return urllib.parse.unquote(text)
        if m == "hex":
            return bytes.fromhex(text).decode()
    except (ValueError, base64.binascii.Error, UnicodeDecodeError) as e:
        return f"Decode error: {e}"
    return f"Unknown method '{method}'. Use: base64  url  hex"


def test_regex(pattern: str, text: str) -> str:
    """Test a regex pattern against text and return matches."""
    try:
        matches = re.findall(pattern, text)
        if matches:
            return f"Pattern: {pattern}\nMatches ({len(matches)}): {matches}"
        return f"Pattern: {pattern}\nNo matches found."
    except re.error as e:
        return f"Regex error: {e}"


def text_diff(a: str, b: str) -> str:
    """Return a unified diff between two strings."""
    diff = list(difflib.unified_diff(
        a.splitlines(), b.splitlines(),
        fromfile="text1", tofile="text2", lineterm="",
    ))
    if not diff:
        return "No differences found."
    return "\n".join(diff[:40])


def flip_text(text: str) -> str:
    """Flip text upside down using Unicode characters."""
    return text.translate(_FLIP_MAP)[::-1]


def lorem_ipsum(paragraphs: int = 3) -> str:
    """Generate lorem ipsum placeholder text."""
    n = max(1, min(paragraphs, 20))
    return "\n\n".join(_LOREM for _ in range(n))
