from decimal import Decimal

from .formatting import currency, invoice_number


def invoice_summary(sequence: int, unit_price: str, quantity: int) -> dict[str, str]:
    total = Decimal(unit_price) * quantity
    return {"number": invoice_number(sequence), "total": currency(total)}
