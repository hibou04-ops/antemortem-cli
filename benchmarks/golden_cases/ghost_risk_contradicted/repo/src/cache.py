CACHE_TTL_SECONDS = 60

def cache_headers():
    return {"Cache-Control": f"max-age={CACHE_TTL_SECONDS}"}
