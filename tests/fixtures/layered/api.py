from service import divide


def handle(payload):
    denominator = int(payload['denominator'])
    if denominator == 0:
        return {'error': 'zero denominator'}, 400
    return {'value': divide(int(payload['numerator']), denominator)}, 200
