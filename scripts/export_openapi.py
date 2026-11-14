"""Write the FastAPI OpenAPI document to docs/openapi.json (source for generated TS types)."""

import json
import sys
from pathlib import Path

from lunarnav_api.main import create_app

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/openapi.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out}")
