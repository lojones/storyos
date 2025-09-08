import os
import streamlit as st
from typing import Optional

SERVICES_VERSION = "2025-09-07-streaming-v1"


def secret(name: str) -> Optional[str]:
    try:
        val = st.secrets.get(name)
    except Exception:
        val = None
    if val:
        return val
    try:
        general = st.secrets.get("general") or st.secrets["general"]
        if isinstance(general, dict):
            return general.get(name)
        return general[name]
    except Exception:
        return os.getenv(name)
