from catalogs.itemcatalog import item_catalog


class Item:
    def __init__(self, itemdict):
        self.is_quest_item = False
        self.category = None

        self.name = itemdict.get('name')
        self.subname = itemdict.get('subname')
        self.charges = itemdict.get('charges')
        self.field1 = itemdict.get('field1')
        self.field2 = itemdict.get('field2')
        self.seqId = itemdict.get('seqId')
        self.tailByte = itemdict.get('tailByte')
        self.sef_flag = itemdict.get('sefFlag')

        self.complete()

    def complete(self):
        self.is_quest_item = item_catalog.is_quest_item(self.name)
        self.category = item_catalog.get_category(self.name)
        self.details = item_catalog.get_item_full('quest' if self.is_quest_item else self.category, self.name)
        self.ability = self.details.get('ability', None)
        if self.ability is not None:
            self.ability_details = item_catalog.get_item_ability(self.ability)
        self.passives = self.details.get('passives', {})
        icon_name_raw = self.details.get('name_resolved', None) or self.details.get('desc')
        self.icon_name = item_catalog.solve_icon_name(icon_name_raw)
        self.rarity = self.details.get('rarity')
        if 'consumable' in self.rarity:
            self.rarity = self.rarity.replace('consumable_', '')
        self.price = item_catalog.get_price(self.rarity)
