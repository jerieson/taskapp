"""Print the OpenAPI schema as JSON to stdout. Used by `make types`."""

import json
import sys

from app.main import app

if __name__ == "__main__":
    json.dump(app.openapi(), sys.stdout, indent=2)
    sys.stdout.write("\n")
