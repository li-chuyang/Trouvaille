def make_user_id(display_name: str) -> str:
    cleaned = "".join(character for character in display_name if character.isalnum())
    return "USR-" + cleaned.upper()
