def issue_session(user):
    token = create_token(user.id)
    audit("issued")
    return token
