import importlib.util
import sys
from pathlib import Path


root = Path(sys.argv[1])
source = root / "calculator.py"
assert source.is_file(), "calculator.py was removed"
spec = importlib.util.spec_from_file_location("calculator", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
cases = [(-8, 0, 10, 0), (0, 0, 10, 0), (4, 0, 10, 4), (10, 0, 10, 10), (18, 0, 10, 10)]
for value, lower, upper, expected in cases:
    assert module.clamp(value, lower, upper) == expected, (value, expected)
print("clamp behavior is correct")
