def refund(balance, amount):
    return balance + amount


def fee(amount):
    return max(0, amount) * 0.02
