import os
import sys

# Permite importar config y helpers del pipeline de modelado.
MODELING = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "training", "nucleo", "modeling")
)
EXPERIMENTAL = os.path.join(MODELING, "experimental")
for p in (MODELING, EXPERIMENTAL):
    if p not in sys.path:
        sys.path.insert(0, p)