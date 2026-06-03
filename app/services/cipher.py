"""Phone number cipher decoding for JustDial encoded HTML."""

CIPHER_MAP: dict[str, str] = {
    "c": "0",
    "d": "1",
    "e": "2",
    "f": "3",
    "g": "4",
    "h": "5",
    "i": "6",
    "j": "7",
    "k": "8",
    "l": "9",
}


def decode_phone(encoded: str) -> str:
    """Decode JustDial cipher-encoded phone string to digits."""
    if not encoded:
        return ""
    digits = []
    for char in encoded.strip().lower():
        if char in CIPHER_MAP:
            digits.append(CIPHER_MAP[char])
        elif char.isdigit():
            digits.append(char)
    return "".join(digits)


def is_valid_indian_phone(digits: str) -> bool:
    """Return True if digits form a valid 10-digit Indian mobile number."""
    cleaned = "".join(c for c in digits if c.isdigit())
    if cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    return len(cleaned) == 10 and cleaned.isdigit()
