FINDING_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "finding": {"type": "string"},
        "metric": {"type": "string"},
        "value": {"type": "number"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["finding", "metric", "value", "confidence"],
    "additionalProperties": False,
}


def validate_finding(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["output is not an object"]
    errors: list[str] = []
    required = {"finding", "metric", "value", "confidence"}
    missing = required - value.keys()
    extra = value.keys() - required
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    if extra:
        errors.append(f"unexpected keys: {sorted(extra)}")
    if "finding" in value and not isinstance(value["finding"], str):
        errors.append("finding is not a string")
    if "metric" in value and not isinstance(value["metric"], str):
        errors.append("metric is not a string")
    if "value" in value and not isinstance(value["value"], int | float):
        errors.append("value is not a number")
    if value.get("confidence") not in {"low", "medium", "high"}:
        errors.append("confidence is not low, medium, or high")
    return errors

