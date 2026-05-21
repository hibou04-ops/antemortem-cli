def load(key):
    if key in CACHE:
        return CACHE[key]
    return fetch(key)
