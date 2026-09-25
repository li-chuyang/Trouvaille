import sys
from pathlib import Path


root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from profiles.normalize import normalize_profile
from profiles.render import render_profile

profile = normalize_profile(" Ada ", " Lovelace ")
assert profile == {"full_name": "Ada Lovelace", "initials": "AL"}
assert render_profile(" Ada ", " Lovelace ") == "Ada Lovelace (AL)"
print("profile contract is preserved")
