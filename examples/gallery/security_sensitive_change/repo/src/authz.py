def can_rotate_api_key(actor, target):
    if actor.is_admin:
        return True
    return actor.id == target.owner_id

def audit_rotation(actor, target):
    return {"actor": actor.id, "target": target.id}
