import sys
from pathlib import Path


root = Path(sys.argv[1])
assert (root / "AGENTS.md").is_file()
assert (root / "billing" / "AGENTS.md").is_file()
sys.path.insert(0, str(root))
from billing.service import invoice_summary

assert invoice_summary(7, "1.005", 1) == {"number": "INV-000007", "total": "1.01"}
assert invoice_summary(42, "2.675", 2) == {"number": "INV-000042", "total": "5.35"}
assert invoice_summary(999999, "0.10", 3) == {"number": "INV-999999", "total": "0.30"}
print("integrated invoice behavior follows scoped conventions")
