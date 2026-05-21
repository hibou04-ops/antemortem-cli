def can_delete(user):
    if user.role == "admin":
        return True
    return False
