from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def validate_group(schema_name: str, pattern: str) -> None:
    schema_path = ROOT / "contracts" / "schemas" / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    paths = sorted(ROOT.glob(pattern))
    if not paths:
        raise AssertionError(f"no contracts matched {pattern}")
    for path in paths:
        errors = sorted(validator.iter_errors(load_yaml(path)), key=lambda item: list(item.path))
        if errors:
            detail = "; ".join(f"{list(error.path)}: {error.message}" for error in errors)
            raise AssertionError(f"{path.relative_to(ROOT)}: {detail}")


def validate_acceptance() -> None:
    document = load_yaml(ROOT / "contracts" / "acceptance.yaml")
    schema = json.loads((ROOT / "contracts" / "schemas" / "acceptance.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(document))
    assert not errors, "; ".join(error.message for error in errors)
    assert document["schema_version"] == "reweft.acceptance/v1"
    checks = document["checks"]
    ids = [check["id"] for check in checks]
    assert len(ids) == len(set(ids)), "acceptance IDs must be unique"
    valid_statuses = set(document["status_definitions"])
    for check in checks:
        assert check["execution"]["status"] in valid_statuses
        assert isinstance(check["release_blocking"], bool)
        if check["execution"]["status"] == "passed":
            assert check["evidence_artifact"], f"{check['id']} passed without evidence"


if __name__ == "__main__":
    validate_group("connector-manifest.schema.json", "contracts/connector-manifests/*.yaml")
    validate_group("target-capability.schema.json", "contracts/target-capabilities/*.yaml")
    validate_group("config.schema.json", "examples/configurations/*.yaml")
    validate_acceptance()
    print("Contract schemas and acceptance registry validated.")
