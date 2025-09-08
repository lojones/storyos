import json
from pathlib import Path
import streamlit as st


def yaml_safe_load(text: str):
    import yaml as _yaml
    return _yaml.safe_load(text)


def session_default_json(key: str, obj) -> str:
    if key not in st.session_state:
        st.session_state[key] = json.dumps(obj, indent=2)
    return st.session_state[key]


def html_safe(text) -> str:
    import html as _html
    s = "" if text is None else str(text)
    s = _html.escape(s)
    return s.replace("\n", "<br>")
