import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import streamlit as st

_USERS_FILE = Path("data/users.json")
_AUTH_SALT = "storyos_local_salt"

def _ensure_users_file():
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _USERS_FILE.exists():
        _USERS_FILE.write_text("{}", encoding="utf-8")

def _load_users() -> Dict[str, Any]:
    try:
        _ensure_users_file()
        return json.loads(_USERS_FILE.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}

def _save_users(data: Dict[str, Any]):
    try:
        _ensure_users_file()
        _USERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        st.error(f"Failed to save users: {e}")

def _hash_password(username: str, password: str) -> str:
    h = hashlib.sha256()
    h.update(f"{_AUTH_SALT}:{username}:{password}".encode("utf-8"))
    return h.hexdigest()

def logout_and_reset():
    st.session_state.auth_user = None
    st.session_state.player_name = ""
    st.session_state.initialized = False
    st.session_state.game_state = None
    st.session_state.chronicle = None
    st.session_state.current_scenario = None
    st.session_state.chat_history = []
    st.session_state.struct_future = None
    st.session_state.struct_target_dm_index = None
    st.rerun()

def ensure_authenticated() -> bool:
    if st.session_state.get("auth_user"):
        return True
    st.markdown("---")
    st.title("🔐 Login to play")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        login_clicked = col1.form_submit_button("Login", type="primary")
        register_clicked = col2.form_submit_button("Register")
    if login_clicked:
        users = _load_users()
        rec = users.get(username)
        if not username or not password:
            st.error("Enter username and password.")
            return False
        if not rec:
            st.error("User not found.")
            return False
        if rec.get("password_hash") != _hash_password(username, password):
            st.error("Invalid credentials.")
            return False
        st.session_state.auth_user = username
        st.success(f"Welcome, {username}!")
        st.rerun()
        return True
    if register_clicked:
        users = _load_users()
        if not username or not password:
            st.error("Enter username and password.")
            return False
        if username in users:
            st.error("Username already exists.")
            return False
        users[username] = {
            "password_hash": _hash_password(username, password),
            "created_at": datetime.now().isoformat(),
        }
        _save_users(users)
        st.session_state.auth_user = username
        st.success(f"Account created. Welcome, {username}!")
        st.rerun()
        return True
    st.info("Create an account or log in to continue.")
    return False
