import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import os

os.environ['PATH'] = str(Path(__file__).parent) + ':' + str(Path(__file__).parents[2] / 't3-maintenance/scripts') + ':' + os.environ['PATH']
