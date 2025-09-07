from typing import List, Dict, Any, Optional, Iterable, Union


class ProviderBase:
    name: str
    model: str
    caps: Dict[str, Any]

    def __init__(self, name: str, model: str, caps: Optional[Dict[str, Any]] = None):
        self.name = name
        self.model = model
        self.caps = caps or {}

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        response_format_json: bool = True,
        stream: bool = False,
    ) -> Union[Dict[str, Any], Iterable[str]]:
        raise NotImplementedError

