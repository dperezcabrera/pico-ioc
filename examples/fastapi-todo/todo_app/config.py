from dataclasses import dataclass
from pico_ioc import configured


@configured(prefix="APP_")
@dataclass
class AppConfig:
    name: str = "TODO API"
    debug: bool = False
