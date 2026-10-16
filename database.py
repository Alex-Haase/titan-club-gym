import sys

from src.gym import database as _database

sys.modules[__name__] = _database
