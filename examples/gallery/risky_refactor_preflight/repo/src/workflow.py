STATUS_APPROVED = "approved"
STATUS_REVERTED = "reverted"

def can_execute(task):
    return task.status == STATUS_APPROVED and not task.cancelled

def revert_task(task):
    if task.status != STATUS_APPROVED:
        return "skip"
    task.status = STATUS_REVERTED
    return "reverted"
