def delete_user(actor, target):
    if not actor.is_admin:
        raise PermissionError("admin required")
    delete(target)
