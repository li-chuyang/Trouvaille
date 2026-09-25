def normalize_profile(first_name: str, last_name: str) -> dict[str, str]:
    """Return the stable profile contract with `full_name` and `initials`."""
    first = first_name.strip()
    last = last_name.strip()
    return {"full_name": f"{first} {last}", "initials": f"{first[0]}{last[0]}".upper()}
