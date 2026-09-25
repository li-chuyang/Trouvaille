import sys
from pathlib import Path


root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from shop.checkout import total_due
from shop.shipping import shipping_cost

assert shipping_cost(49.99) == 6.5
assert shipping_cost(50.0) == 0.0
assert shipping_cost(75.0) == 0.0
assert total_due(50.0) == 50.0
print("shipping boundary is correct")
