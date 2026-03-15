from utils.loaders import load_inventories
from utils.versions import is_app_up_most_to_date


if __name__ == "__main__":
    path = 'steamcampaign01.sav'
    if not is_app_up_most_to_date('steamcampaign01.sav'):
        raise Exception("App is NOT up to date!")

    inventories = load_inventories(path)
    print('ok')
