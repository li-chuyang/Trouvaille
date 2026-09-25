def normalize_key(value: str) -> str:
    return value.strip()


def normalize_value(value: str) -> str:
    return value.strip()


def parse_entry(line: str) -> tuple[str, str]:
    key, value = line.split("=", 1)
    return normalize_key(key), normalize_value(value)
