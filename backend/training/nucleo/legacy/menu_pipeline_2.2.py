import sys
import pathlib

# Ensure the backend root is in sys.path for imports
BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Import the run function from the pipeline orchestrator
import importlib.util, os

# Load the run function from the file with a dot in its name
run_path = os.path.join(os.path.dirname(__file__), 'run_pipeline_2.0.py')
spec = importlib.util.spec_from_file_location('run_pipeline_2_0', run_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
pipeline_run = module.run

def main():
    """Entry point for the menu based pipeline execution.

    This script forwards execution to the existing ``run`` function
    defined in ``run_pipeline_2.0.py``. Keeping the logic in a single
    place avoids duplication and ensures future updates are reflected
    automatically.
    """
    pipeline_run()

if __name__ == "__main__":
    main()

