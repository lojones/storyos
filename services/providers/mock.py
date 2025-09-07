from typing import List, Dict, Any, Optional, Iterable, Union
import json
import time
from .base import ProviderBase


class MockProvider(ProviderBase):
    def __init__(self):
        super().__init__(name="mock", model="mock-1", caps={
            "allows_explicit_adult_text": False,
            "json_mode_strict": True,
            "supports_streaming": True,
            "max_output_tokens": 2048,
            "tool_use": False,
            "cost_rank": 0,
            "latency_rank": 0,
        })

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
        response_format_json: bool = True,
        stream: bool = False,
    ) -> Union[Dict[str, Any], Iterable[str]]:
        # Produce a deterministic, contract-compliant JSON payload
        content = {
            "narrative": (
                "You take a moment to orient yourself, noticing small details in the setting. "
                "People move around you with purpose as time advances slightly."
            ),
            "suggested_actions": [
                "Look around",
                "Greet someone nearby",
                "Check your schedule",
            ],
            "state_patch": {
                "mood": "focused",
                "stress_level": 42,
            },
            "scene_tags": ["campus", "setup"],
            "meta": {"image_prompt": None},
        }

        if stream:
            def gen():
                text = json.dumps(content)
                # stream in chunks
                for i in range(0, len(text), 32):
                    yield text[i:i+32]
                    time.sleep(0.005)
            return gen()
        else:
            return content

