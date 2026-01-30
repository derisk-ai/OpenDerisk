def list_to_dict(items, key_attr: str) -> dict:
    result = {}
    for obj in items:
        key = getattr(obj, key_attr)
        if key in result:
            raise ValueError(f"Duplicate key found: {key}")
        result[key] = obj
    return result