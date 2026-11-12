def refund(balance, amount):
    if amount < 0 or amount > balance:
        raise ValueError('invalid refund')
    return balance - amount
