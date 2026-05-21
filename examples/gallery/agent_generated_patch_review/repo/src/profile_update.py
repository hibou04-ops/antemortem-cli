def apply_profile_patch(user, patch):
    allowed = {"display_name", "timezone"}
    for key, value in patch.items():
        if key not in allowed:
            raise ValueError(f"unsupported field: {key}")
        setattr(user, key, value)
    return user

def agent_patch(payload):
    return payload.get("patch", {})
