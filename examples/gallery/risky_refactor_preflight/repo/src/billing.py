STATUS_PAID = "paid"
STATUS_REFUNDED = "refunded"

def can_capture(invoice):
    return invoice.status == STATUS_PAID and not invoice.cancelled

def issue_refund(invoice):
    if invoice.status != STATUS_PAID:
        return "skip"
    invoice.status = STATUS_REFUNDED
    return "refunded"
