import json
import re

from utils.utils import format_item_name

filenames = {
    'armor_sets': 'armor_sets.json',
    'consumables': 'consumables.json',
    'cursed': 'cursed_items.json',
    'enemy': 'enemy_items.json',
    'face': 'face_items.json',
    'head': 'head_items.json',
    'legendary': 'legendary_items.json',
    'modifiers': 'modifiers.json',
    'neck': 'neck_items.json',
    'parasites': 'parasites.json',
    'special_class': 'special_class_items.json',
    'trinket_slot': 'trinkets.json',
    'weapons': 'weapons.json',
}

quests_filenames = [
    'beanies_quest_items.json', 'legacy_quest_items.json'
]

class ItemCatalog:
    def __init__(self):
        self.categories = []
        catalog = json.loads(open('data/items.json', encoding="utf-8").read())
        for key, value in catalog.items():
            if key == 'meta':
                continue
            setattr(self, key, value)
            self.categories.append(key)

    def is_quest_item(self, name):
        return name in getattr(self, 'quest')

    def get_category(self, name):
        if name not in getattr(self, 'all'):
            return None
        for category in self.categories:
            if category == 'all' or category == 'quest':
                continue
            if name in getattr(self, category):
                return category
        return None

    def get_item_quest_full(self, category, name):
        for filename in quests_filenames:
            url = 'data/items/' + filename
            items = json.loads(open(url, encoding="utf-8").read())
            item = items.get(name, None)
            if item is not None:
                return item
        return None

    def get_item_full(self, category, name):
        if name not in getattr(self, 'all'):
            return None
        if category == 'quest':
            return self.get_item_quest_full(category, name)
        filename = filenames.get(category, None)
        if filename is None:
            return None
        url = 'data/items/' + filename
        items = json.loads(open(url, encoding="utf-8").read())
        item = items.get(name, None)
        return item

    def get_item_ability(self, ability_name):
        url = 'data/item_abilities.json'
        abilities = json.loads(open(url, encoding="utf-8").read())
        ability = abilities.get(ability_name, None)
        return ability

    def solve_icon_name(self, name):
        solved_name = name.replace('_DESC', '').replace('_FIXED', '').replace('ITEM_', '')
        return 'ITEM_' + format_item_name(solved_name) + '.svg'


item_catalog = ItemCatalog()
