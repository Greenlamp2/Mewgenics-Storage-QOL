from catalogs.items import Items
from utils.loaders import load_inventories
from utils.savers import save_inventories
from utils.versions import is_app_up_most_to_date


def parse_all(path):
    inventories = load_inventories(path)
    save_inventories(path, inventories)

if __name__ == "__main__":
    items = Items()
    print('ok')
    # if is_app_up_most_to_date('steamcampaign01.sav'):
    #     print("AppUpMost is up to date!")
    #     parse_all('steamcampaign01.sav')
    # else:
    #     print("AppUpMost is NOT up to date!")
