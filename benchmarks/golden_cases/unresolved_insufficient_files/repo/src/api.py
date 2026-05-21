def create_invoice(request):
    payload = request.json()
    return {"status": "queued", "payload": payload}
