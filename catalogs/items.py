import json


class Items:
    def __init__(self):
        catalog = json.loads(open('data/items.json').read())
        for key, value in catalog.items():
            if key == 'meta':
                continue
            setattr(self, key, value)
