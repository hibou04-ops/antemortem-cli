MAX_UPLOAD_BYTES = 1048576

def accept_upload(payload):
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("too large")
    return store(payload)

def store(payload):
    return payload
