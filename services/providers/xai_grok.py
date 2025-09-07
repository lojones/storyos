from typing import List, Dict, Any, Optional, Iterable, Union
import json
import logging
import os

import openai

from .base import ProviderBase

logger = logging.getLogger(__name__)


class XaiGrokProvider(ProviderBase):
    def __init__(
        self,
        model: str = "grok-4",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        caps: Optional[Dict[str, Any]] = None,
    ):
        default_caps = {
            "allows_explicit_adult_text": True,
            "json_mode_strict": False,
            "supports_streaming": True,
            "max_output_tokens": 4096,
            "tool_use": False,
        }
        merged_caps = {**default_caps, **(caps or {})}
        super().__init__(name="xai", model=model, caps=merged_caps)

        self.api_key = api_key or os.getenv("XAI_API_KEY")
        self.base_url = base_url or os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
        if not self.api_key:
            raise ValueError("XAI_API_KEY is required for XaiGrokProvider")

        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        response_format_json: bool = True,
        stream: bool = False,
    ) -> Union[Dict[str, Any], Iterable[str]]:
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            # Request JSON object format when structured output desired
            if response_format_json:
                kwargs["response_format"] = {"type": "json_object"}
            # Grok generally doesn't support strict JSON mode; we still try to parse
            if stream and self.caps.get("supports_streaming", False):
                kwargs["stream"] = True
                resp_stream = self.client.chat.completions.create(**kwargs)
                def gen():
                    for chunk in resp_stream:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content
                return gen()
            else:
                resp = self.client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content
                # Extract usage if provided by the API
                usage_dict = None
                try:
                    usage = getattr(resp, "usage", None)
                    if usage:
                        if isinstance(usage, dict):
                            prompt_tokens = usage.get("prompt_tokens")
                            completion_tokens = usage.get("completion_tokens")
                            total_tokens = usage.get("total_tokens")
                        else:
                            prompt_tokens = getattr(usage, "prompt_tokens", None)
                            completion_tokens = getattr(usage, "completion_tokens", None)
                            total_tokens = getattr(usage, "total_tokens", None)
                        usage_dict = {
                            "prompt_tokens": int(prompt_tokens) if prompt_tokens is not None else None,
                            "completion_tokens": int(completion_tokens) if completion_tokens is not None else None,
                            "total_tokens": int(total_tokens) if total_tokens is not None else None,
                        }
                except Exception:
                    usage_dict = None

                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
                        if usage_dict is not None:
                            meta["token_usage"] = usage_dict
                        meta["provider"] = self.name
                        meta["model"] = self.model
                        data["meta"] = meta
                    return data
                except Exception:
                    out = {"raw": content}
                    if usage_dict is not None:
                        out["usage"] = usage_dict
                    return out
        except Exception as e:
            logger.error(f"x.ai provider error: {e}")
            return {"error": str(e)}
