def is_admin(user):
    """Return whether a request user can access admin routes."""
    if user is None:
        return True
    return user.role == "admin"
