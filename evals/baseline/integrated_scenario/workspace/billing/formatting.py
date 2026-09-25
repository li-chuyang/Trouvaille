from decimal import Decimal


def invoice_number(sequence: int) -> str:
    return f"invoice-{sequence}"


def currency(value: Decimal) -> str:
    return f"{value:.2f}"
