import os


def detect_steam_save_folder():
    appdata = os.getenv("APPDATA")
    mewgenics_root = os.path.join(appdata, "Glaiel Games", "Mewgenics")
    if not os.path.exists(mewgenics_root):
        return None
    for folder in os.listdir(mewgenics_root):
        path = os.path.join(mewgenics_root, folder)
        if folder.isdigit():
            saves_path = os.path.join(path, "saves")
            if os.path.exists(saves_path):
                return saves_path
    return None

WATCH_FOLDER = detect_steam_save_folder()
TARGET_FILE  = "steamcampaign01.sav"
TARGET_PATH  = os.path.join(WATCH_FOLDER, TARGET_FILE)
CUSTOM_FOLDER         = os.path.join(WATCH_FOLDER, "custom")
TOKENS_BANK_PATH  = os.path.join(CUSTOM_FOLDER, "tokens_bank.json")
ITEMS_POOL_PATH  = os.path.join(CUSTOM_FOLDER, "items_pool.json")