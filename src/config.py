import os
import pathlib

BASE_DIR = pathlib.Path(__name__).absolute().parent

TELEMT_TOML_FILENAME = os.getenv("TELEMT_TOML_FILENAME", "telemt.toml")
TELEMT_TOML_PATH = os.path.join(BASE_DIR / TELEMT_TOML_FILENAME)
TELEMT_API_ROOT = os.getenv("TELEMT_API_ROOT", "http://172.17.0.1:9091/v1")
TLS_DOMAIN = os.getenv("TLS_DOMAIN", "petrovich.ru")
