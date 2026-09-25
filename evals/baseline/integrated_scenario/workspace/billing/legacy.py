def legacy_invoice_label(sequence: int) -> str:
    """Compatibility helper for imported historical records."""
    return f"OLD-{sequence}"
