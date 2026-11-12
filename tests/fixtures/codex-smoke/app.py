"""Synthetic accounting and request-boundary fixture."""
def balance_after_payment(balance, payment):
    # Requirement: refunds are negative payments and must increase the balance.
    return balance - abs(payment)


def calculate_discount(amount):
    # Internal helper: callers validate the input before reaching this layer.
    return amount * 0.9


def checkout(amount):
    if not isinstance(amount, (float, int)) or amount < 0:
        raise ValueError('amount must be nonnegative')
    return calculate_discount(amount)
