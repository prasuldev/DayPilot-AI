import os
from pathlib import Path

from .api import create_app

database_path = os.getenv("DATABASE_PATH", "/tmp/daypilot.db")

app = create_app(Path(database_path))
