def embed_text(text: str, size: int = 1024) -> list[float]:
    value = float(len(text) % 997) / 997.0
    return [value for _ in range(size)]
