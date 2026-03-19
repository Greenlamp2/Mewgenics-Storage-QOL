from catalogs.itemcatalog import item_catalog


class Item:
    def __init__(self, itemdict, trash=False):
        self.is_quest_item = False
        self.category = None

        self.name = itemdict.get('name')
        self.subname = itemdict.get('subname')
        self.charges = itemdict.get('charges')
        self.field1 = itemdict.get('field1')
        self.field2 = itemdict.get('field2')
        self.seqId = itemdict.get('seqId')
        self.tailByte = itemdict.get('tailByte')
        self.sep_flag = itemdict.get('sep_flag')
        self.broken = self.sep_flag == 5 and trash
        self.used   = self.sep_flag == 3

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
        # Syringe modifier items: use dedicated syringe icon
        name_resolved = (self.details.get('name_resolved') or '').lower()
        if self.category == 'modifiers' and (
            'syringe' in (self.name or '').lower() or 'syringe' in name_resolved
        ):
            self.icon_name = '../misc/sysinge.png'
        # SoulJar / SoulJar_Full: no SVG asset exists, use the dedicated PNG override
        if (self.name or '') in ('SoulJar', 'SoulJar_Full'):
            self.icon_name = '../misc/soul_jar.png'
        self.rarity = self.details.get('rarity')
        try:
            if 'consumable' in self.rarity:
                self.rarity = self.rarity.replace('consumable_', '')
        except Exception as e:
            self.rarity = 'common'
        self.price = item_catalog.get_price(self.rarity)


class GhostItem:
    """Lightweight item-like object for undiscovered items shown in the Pool."""
    locked        = True
    broken        = False
    is_quest_item = False
    subname       = ""
    charges       = -1

    def __init__(self, name: str, details: dict):
        self.name     = name
        self.details  = details or {}
        self.category = item_catalog.get_category(name)

        icon_name_raw = self.details.get("name_resolved") or self.details.get("desc")
        self.icon_name = item_catalog.solve_icon_name(icon_name_raw) if icon_name_raw else None
        # Syringe modifier items: use dedicated syringe icon
        name_resolved = (self.details.get('name_resolved') or '').lower()
        if self.category == 'modifiers' and (
            'syringe' in (self.name or '').lower() or 'syringe' in name_resolved
        ):
            self.icon_name = '../misc/sysinge.png'
        # SoulJar / SoulJar_Full: no SVG asset exists, use the dedicated PNG override
        if (self.name or '') in ('SoulJar', 'SoulJar_Full'):
            self.icon_name = '../misc/soul_jar.png'

        rarity = self.details.get("rarity", "common") or "common"
        if "consumable" in rarity:
            rarity = rarity.replace("consumable_", "")
        self.rarity = rarity
