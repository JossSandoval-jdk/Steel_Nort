import sys
import pathlib
import importlib.util, os

# Ensure backend root is in sys.path
BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Dynamically load run_pipeline_2.0
run_path = os.path.join(os.path.dirname(__file__), 'run_pipeline_2.0.py')
spec = importlib.util.spec_from_file_location('run_pipeline_2_0', run_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
pipeline_run = module.run

def main():
    """Execute the original pipeline orchestrator.
    This wrapper provides a convenient entry‑point without altering the
    original ``run_pipeline_2.0.py`` script.
    """
    pipeline_run()

if __name__ == "__main__":
    main()

