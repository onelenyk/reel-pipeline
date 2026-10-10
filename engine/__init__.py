"""The reel pipeline's engine: raw takes in, a project document and a rendered video out."""
import os
from pathlib import Path

# Where projects, uploaded takes, saved styles and temporary files live. The end-to-end tests point this at their own folder.
HOME = Path(os.environ.get("REEL_HOME", "/work"))
