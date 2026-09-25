def mean(values: list[int]) -> float:
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values) // len(values)
