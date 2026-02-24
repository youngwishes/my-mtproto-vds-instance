import os
import pathlib

BASE_DIR = pathlib.Path(__name__).absolute().parent

TLS_DOMAIN = os.getenv("TLS_DOMAIN", "petrovich.ru")


TELEMT_TOML_FILENAME = os.getenv("TELEMT_TOML_FILENAME", "telemt.toml")
TELEMT_TOML_PATH = os.path.join(BASE_DIR / TELEMT_TOML_FILENAME)
