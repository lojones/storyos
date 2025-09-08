import json
from pathlib import Path
from typing import Dict, Any, List

from services.init import get_mongo_db_from_env


def read_scenario_file(path: Path) -> Dict[str, Any]:
    import yaml as _yaml
    with open(path, "r", encoding="utf-8") as f:
        if path.suffix.lower() == ".json":
            return json.load(f)
        else:
            return _yaml.safe_load(f)


def write_scenario_file(path: Path, data: Dict[str, Any]):
    import yaml as _yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(_yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def list_scenarios_from_mongo() -> List[Dict[str, Any]]:
    db = get_mongo_db_from_env()
    if not db:
        return []
    col = db["sos_scenario_templates"]
    return list(col.find({}, {"_id": 0}).sort("name", 1))
