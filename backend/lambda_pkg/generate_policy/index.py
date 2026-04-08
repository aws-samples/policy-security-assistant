# Re-export from actual Lambda location for testability
import sys
import os

# Add the actual Lambda directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda", "generate_policy"))
from index import *  # noqa: F401, F403, E402
from index import lambda_handler  # noqa: F401, E402
