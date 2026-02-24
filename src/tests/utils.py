import toml

from src import config


def get_toml_file_data() -> dict:
    with open(config.TELEMT_TOML_PATH, "r", encoding="utf-8") as file:
        return toml.loads(file.read())
