def submit(hooks, amount):
    charged = 0
    for hook in hooks:
        if hook in {'submit', 'legacy_submit'}:
            charged += amount
    return charged
