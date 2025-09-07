from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
import json
import logging
import os

from .providers.base import ProviderBase
from .providers.openai_chat import OpenAIChatProvider
from .providers.xai_grok import XaiGrokProvider
from .providers.mistral_chat import MistralChatProvider
from .providers.mock import MockProvider

logger = logging.getLogger(__name__)


class RouteDecision:
    def __init__(self, provider: str, model: str, tier: str):
        self.provider = provider
        self.model = model
        self.tier = tier


class LLMRouter:
    def __init__(self):
        self.providers: Dict[str, ProviderBase] = {}
        self._init_registry()

    def _init_registry(self):
        # Always include mock fallback
        self.providers["mock"] = MockProvider()

        # XAI Grok (T2 allowed)
        try:
            if os.getenv("XAI_API_KEY"):
                self.providers["xai.grok-4"] = XaiGrokProvider(model="grok-4")
        except Exception as e:
            logger.warning(f"XAI provider unavailable: {e}")

        # OpenAI
        try:
            if os.getenv("OPENAI_API_KEY"):
                self.providers["openai.gpt-4o-mini"] = OpenAIChatProvider(model="gpt-4o-mini")
        except Exception as e:
            logger.warning(f"OpenAI provider unavailable: {e}")

        # Mistral (requires OpenAI-compatible base URL)
        try:
            if os.getenv("MISTRAL_API_KEY") and os.getenv("MISTRAL_BASE_URL"):
                self.providers["mistral.mistral-large-latest"] = MistralChatProvider(
                    model="mistral-large-latest"
                )
        except Exception as e:
            logger.warning(f"Mistral provider unavailable: {e}")

    def _cheap_provider(self) -> ProviderBase:
        try:
            return XaiGrokProvider(model="grok-3-mini")
        except Exception:
            return MockProvider()
