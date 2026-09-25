import importlib.util
import sys
from pathlib import Path


root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("config_text", root / "config_text.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.normalize_key("  API_Key ") == "api_key"
assert module.normalize_value("  KeepCase  ") == "KeepCase"
assert module.parse_entry(" Theme = DarkMode ") == ("theme", "DarkMode")
print("only configuration keys are case-folded")
