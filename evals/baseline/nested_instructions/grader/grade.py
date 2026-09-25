import sys
from pathlib import Path


root = Path(sys.argv[1])
assert (root / "AGENTS.md").is_file()
assert (root / "accounts" / "AGENTS.md").is_file()
sys.path.insert(0, str(root))
from accounts.user_ids import make_user_id

assert make_user_id("Ada Lovelace") == "usr_adalovelace"
assert make_user_id("  User-42! ") == "usr_user42"
assert make_user_id("ALPHA") == "usr_alpha"
assert make_user_id("Zoë") == "usr_zo"
print("nested account convention is followed")
