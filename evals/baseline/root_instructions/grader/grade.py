import importlib.util
import sys
from pathlib import Path


root = Path(sys.argv[1])
assert (root / "AGENTS.md").is_file(), "project instructions were removed"
spec = importlib.util.spec_from_file_location("identifiers", root / "identifiers.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.make_project_id("  Red Panda  ") == "red-panda"
assert module.make_project_id("ONE   SMALL Step") == "one-small-step"
assert module.make_project_id("solo") == "solo"
print("root project convention is followed")
