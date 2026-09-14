def normalize_name(name: str) -> str:
    """Trim and collapse whitespace in a human-readable name."""
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    normalized = " ".join(name.split())
    if not normalized:
        raise ValueError("name must not be blank")
    return normalized
