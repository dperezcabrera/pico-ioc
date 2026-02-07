from typing import Dict, List, Tuple, Union

from .config_registrar import ConfigurationManager
from .factory import Provider, ProviderMetadata

KeyT = Union[str, type]


class ProviderSelector:
    def __init__(self, config_manager: ConfigurationManager):
        self._config_manager = config_manager

    def _rank_provider(self, item: Tuple[bool, Provider, ProviderMetadata]) -> Tuple[int, int, int]:
        _, md = item[1], item[2]

        is_present = 1 if self._config_manager.prefix_exists(md) else 0

        pref = str(md.pico_name or "")
        pref_len = len(pref)

        is_primary = 1 if item[0] else 0

        return (is_present, pref_len, is_primary)

    def select_providers(
        self,
        candidates: Dict[KeyT, List[Tuple[bool, Provider, ProviderMetadata]]],
    ) -> Dict[KeyT, Tuple[Provider, ProviderMetadata]]:

        winners: Dict[KeyT, Tuple[Provider, ProviderMetadata]] = {}

        for key, lst in candidates.items():
            lst_sorted = sorted(lst, key=self._rank_provider, reverse=True)
            chosen = lst_sorted[0]
            winners[key] = (chosen[1], chosen[2])

        return winners
