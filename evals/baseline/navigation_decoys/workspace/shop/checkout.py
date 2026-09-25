from .shipping import shipping_cost


def total_due(subtotal: float) -> float:
    return subtotal + shipping_cost(subtotal)
