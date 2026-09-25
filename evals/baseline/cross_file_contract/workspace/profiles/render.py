from .normalize import normalize_profile


def render_profile(first_name: str, last_name: str) -> str:
    profile = normalize_profile(first_name, last_name)
    return f"{profile['name']} ({profile['initials']})"
