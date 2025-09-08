import streamlit as st
from typing import Any

def initialize_session_state() -> None:
    if "game_state" not in st.session_state:
        st.session_state.game_state = None
    if "chronicle" not in st.session_state:
        st.session_state.chronicle = None
    if "current_scenario" not in st.session_state:
        st.session_state.current_scenario = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "initialized" not in st.session_state:
        st.session_state.initialized = False
    if "age_verified" not in st.session_state:
        st.session_state.age_verified = False
    if "images_enabled" not in st.session_state:
        st.session_state.images_enabled = False
    if "audio_enabled" not in st.session_state:
        st.session_state.audio_enabled = False
    if "streaming" not in st.session_state:
        st.session_state.streaming = False
    if "player_name" not in st.session_state:
        st.session_state.player_name = ""
    if "admin_mode" not in st.session_state:
        st.session_state.admin_mode = False
    if "admin_editor_text" not in st.session_state:
        st.session_state.admin_editor_text = None
    if "admin_selected_path" not in st.session_state:
        st.session_state.admin_selected_path = None
    if "token_sent_total" not in st.session_state:
        st.session_state.token_sent_total = 0
    if "token_total_overall" not in st.session_state:
        st.session_state.token_total_overall = 0
    if "struct_future" not in st.session_state:
        st.session_state.struct_future = None
    if "struct_target_dm_index" not in st.session_state:
        st.session_state.struct_target_dm_index = None
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None
    if "auth_error" not in st.session_state:
        st.session_state.auth_error = None
