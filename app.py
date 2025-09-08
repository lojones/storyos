import streamlit as st
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import copy
from services.mongo import MongoSetup

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our modules
from dm.engine import GameEngine
from dm.models import GameState, Chronicle
from scenarios.registry import ScenarioRegistry
from services.llm import LLMService
from memory.chronicle import ChronicleManager

# Page config
st.set_page_config(
    page_title="storyOS - Interactive Narrative Chat",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS for better styling
st.markdown("""
<style>
    /* Dark mode tuned colors */
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        background-color: #1f2937; /* slate-800 */
        border: 1px solid #374151; /* slate-700 */
        color: #e5e7eb; /* gray-200 */
    }
    .chat-message strong { color: #f3f4f6; }

    .user-message {
        background-color: #1e3a5f; /* blue-900-ish */
        border: 1px solid #2b4c7e;
        margin-left: 2rem;
        color: #e8eef7;
    }
    .dm-message {
        background-color: #0b1020; /* near-black with blue tint */
        border: 1px solid #1f2937;
        margin-right: 2rem;
        color: #e5e7eb;
    }
    /* Typing / thinking indicator */
    .typing { display: inline-flex; align-items: center; gap: 0.35rem; }
    .typing .dots { display: inline-flex; gap: 0.15rem; }
    .typing .dots span {
        width: 6px; height: 6px; border-radius: 50%;
        display: inline-block; background: #9ca3af; opacity: 0.4;
        animation: typingBlink 1.2s infinite ease-in-out;
    }
    .typing .dots span:nth-child(2) { animation-delay: 0.2s; }
    .typing .dots span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typingBlink {
        0%, 80%, 100% { opacity: 0.2; transform: translateY(0px); }
        40% { opacity: 1; transform: translateY(-2px); }
    }
    .system-info {
        font-size: 0.8rem;
        color: #9ca3af; /* gray-400 */
        font-style: italic;
    }
    .scenario-card {
        background-color: #111827; /* gray-900 */
        border: 1px solid #1f2937; /* slate-800 */
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
        color: #e5e7eb;
    }

    /* Ensure links are legible */
    .chat-message a { color: #93c5fd; }
    .chat-message a:hover { color: #bfdbfe; }
</style>
""", unsafe_allow_html=True)

SERVICES_VERSION = "2025-09-07-streaming-v1"

@st.cache_resource
def initialize_services():
    """Initialize core services."""
    try:
        logger.info(f"Initializing services (version={SERVICES_VERSION})")
        # Helper to read from st.secrets at top-level or within [general]
        def _secret(name: str) -> Optional[str]:
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
                # Some Streamlit versions expose Mapping-like, support indexing
                return general[name]
            except Exception:
                return None

        # Get API credentials (prioritize XAI, fallback to OpenAI); support [general] section
        api_key = (
            _secret("XAI_API_KEY")
            or os.getenv("XAI_API_KEY")
            or _secret("OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        base_url = (
            _secret("XAI_BASE_URL")
            or os.getenv("XAI_BASE_URL")
            or _secret("OPENAI_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.x.ai/v1"
        )
        default_model = _secret("DEFAULT_MODEL") or os.getenv("DEFAULT_MODEL", "grok-beta")
        # Accept both new and legacy env names for encryption key
        encryption_key = (
            _secret("STORYOS_AES_KEY")
            or os.getenv("STORYOS_AES_KEY")
            or _secret("CHRONICLE_ENCRYPTION_KEY")
            or os.getenv("CHRONICLE_ENCRYPTION_KEY")
        )

        # MongoDB setup (ensure collections/indexes)
        mongo_uri = _secret("MONGODB_URI") or os.getenv("MONGODB_URI")
        mongo_user = _secret("MONGODB_USERNAME") or os.getenv("MONGODB_USERNAME")
        mongo_pass = _secret("MONGODB_PASSWORD") or os.getenv("MONGODB_PASSWORD")
        mongo_db = _secret("MONGODB_DATABASE_NAME") or os.getenv("MONGODB_DATABASE_NAME") or "storyos"
        if mongo_uri:
            try:
                # Replace placeholders if present
                if "<username>" in mongo_uri and mongo_user:
                    mongo_uri = mongo_uri.replace("<username>", str(mongo_user))
                if "<password>" in mongo_uri and mongo_pass:
                    mongo_uri = mongo_uri.replace("<password>", str(mongo_pass))
                ms = MongoSetup(uri=mongo_uri, db_name=mongo_db)
                ms.initialize_if_needed()
                # Optionally seed system prompt if empty (idempotent)
                try:
                    from dm.prompting import load_system_prompt
                    ms.seed_system_prompt_if_empty(load_system_prompt())
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Mongo setup failed: {e}")
                # Non-fatal; continue without Mongo
        
        if not api_key:
            st.error("API key not found. Please set XAI_API_KEY (for Grok) or OPENAI_API_KEY in secrets.toml or environment variables.")
            st.stop()
        
        # Initialize services
        llm_service = LLMService(api_key=api_key, base_url=base_url, default_model=default_model)
        chronicle_manager = ChronicleManager(encryption_key=encryption_key)
        scenario_registry = ScenarioRegistry()
        game_engine = GameEngine(llm_service, chronicle_manager)
        
        return llm_service, chronicle_manager, scenario_registry, game_engine
    
    except Exception as e:
        st.error(f"Failed to initialize services: {e}")
        st.stop()

def initialize_session_state():
    """Initialize Streamlit session state."""
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
    # Player/story label
    if "player_name" not in st.session_state:
        st.session_state.player_name = ""
    if "admin_mode" not in st.session_state:
        st.session_state.admin_mode = False
    if "admin_editor_text" not in st.session_state:
        st.session_state.admin_editor_text = None
    if "admin_selected_path" not in st.session_state:
        st.session_state.admin_selected_path = None
    # Token tracking
    if "token_sent_total" not in st.session_state:
        st.session_state.token_sent_total = 0  # cumulative prompt tokens sent
    if "token_total_overall" not in st.session_state:
        st.session_state.token_total_overall = 0  # cumulative prompt+completion tokens
    # Background job handles
    if "struct_future" not in st.session_state:
        st.session_state.struct_future = None
    if "struct_target_dm_index" not in st.session_state:
        st.session_state.struct_target_dm_index = None
    # Auth
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None
    if "auth_error" not in st.session_state:
        st.session_state.auth_error = None

@st.cache_resource
def get_executor() -> ThreadPoolExecutor:
    """Shared thread pool for background tasks (non-blocking UI)."""
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="storyos")

# Simple local-file auth helpers
_USERS_FILE = Path("data/users.json")
_AUTH_SALT = os.getenv("STORYOS_AUTH_SALT", "storyos_local_salt")

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

def _logout_and_reset():
    # Clear gameplay/session state on logout
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
    if st.session_state.auth_user:
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

def render_scenario_selector(scenario_registry):
    """Render scenario selection interface."""
    st.sidebar.header("📖 Choose Your Story")

    # Logged-in user and logout
    if st.session_state.get("auth_user"):
        with st.sidebar.expander("Account", expanded=True):
            st.caption(f"Logged in as: {st.session_state.auth_user}")
            if st.button("Logout", use_container_width=True):
                _logout_and_reset()

    # Admin full-screen toggle
    if st.sidebar.button("🛠️ Admin (full screen)", use_container_width=True):
        st.session_state.admin_mode = True
        st.rerun()
    
    scenarios = scenario_registry.list_scenarios()
    
    if not scenarios:
        st.sidebar.error("No scenarios found. Please add scenario files to scenarios/packs/")
        return None
    
    # Filter by tags
    all_tags = scenario_registry.get_tags()
    if all_tags:
        selected_tags = st.sidebar.multiselect("Filter by tags:", all_tags)
        if selected_tags:
            scenarios = [s for s in scenarios if any(tag in s.tags for tag in selected_tags)]
    
    # Scenario selection
    scenario_options = {f"{s.name} ({s.id})": s for s in scenarios}
    selected_name = st.sidebar.selectbox("Select Scenario:", list(scenario_options.keys()))
    
    if selected_name:
        selected_scenario = scenario_options[selected_name]
        
        # Show scenario details
        with st.sidebar.expander("📋 Scenario Details"):
            st.write(f"**Author:** {selected_scenario.author}")
            st.write(f"**Version:** {selected_scenario.version}")
            st.write(f"**Tags:** {', '.join(selected_scenario.tags)}")
            st.write(f"**Description:**")
            st.write(selected_scenario.description)
            
            if selected_scenario.safety.sfw_lock:
                st.info("🔒 This scenario enforces SFW mode")
            
            if selected_scenario.safety.trigger_warnings:
                st.warning(f"⚠️ Warnings: {', '.join(selected_scenario.safety.trigger_warnings)}")
        
        # Admin tools
        render_admin_tools(scenario_registry, selected_scenario)
        
        return selected_scenario
    
    return None

def render_game_controls(game_engine, chronicle_manager, scenario_registry):
    """Render game control buttons."""
    st.sidebar.header("🎮 Game Controls")
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("💾 Save Game", use_container_width=True):
            if st.session_state.chronicle:
                try:
                    # Prefer player/story name in filename
                    def _slug(s: str) -> str:
                        import re
                        s = s.strip()
                        s = re.sub(r"\s+", "-", s)
                        s = re.sub(r"[^A-Za-z0-9\-_]", "", s)
                        return s[:40] or "story"
                    name = _slug(st.session_state.get("player_name", "story"))
                    scen = getattr(st.session_state.get("current_scenario", None), "id", "scenario")
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{name}__{scen}__{ts}.json"
                    filepath = chronicle_manager.save_chronicle(st.session_state.chronicle, filename=filename)
                    st.sidebar.success(f"Game saved to {Path(filepath).name}")
                except Exception as e:
                    st.sidebar.error(f"Save failed: {e}")
    
    with col2:
        if st.button("🔄 New Game", use_container_width=True):
            st.session_state.game_state = None
            st.session_state.chronicle = None
            st.session_state.chat_history = []
            st.session_state.initialized = False
            st.session_state.token_sent_total = 0
            st.session_state.token_total_overall = 0
            st.rerun()

    # Model and content settings
    with st.sidebar.expander("⚙️ Model & Content Settings", expanded=False):
        st.session_state.streaming = st.checkbox("Streaming", value=st.session_state.streaming)
        st.session_state.images_enabled = st.checkbox("Images enabled", value=st.session_state.images_enabled)
        st.session_state.audio_enabled = st.checkbox("Audio enabled", value=st.session_state.audio_enabled)
        st.session_state.age_verified = st.checkbox("I am 18+ (age gate)", value=st.session_state.age_verified)
    
    # Export options
    if st.session_state.chronicle:
        with st.sidebar.expander("📤 Export Options"):
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Export Chronicle"):
                    export_data = chronicle_manager.export_chronicle(st.session_state.chronicle)
                    st.download_button(
                        "⬇️ Download Chronicle",
                        json.dumps(export_data, indent=2),
                        f"chronicle_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        "application/json"
                    )

    # Load moved to global sidebar (always visible)
            
            with col2:
                if st.button("Export Chat"):
                    chat_export = []
                    for msg in st.session_state.chat_history:
                        chat_export.append({
                            "role": msg["role"],
                            "content": msg["content"],
                            "timestamp": msg.get("timestamp", "")
                        })
                    
                    st.download_button(
                        "⬇️ Download Chat",
                        json.dumps(chat_export, indent=2),
                        f"chat_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        "application/json"
                    )

def render_chronicle_info():
    """Render chronicle information in sidebar."""
    if not st.session_state.chronicle:
        return
    
    chronicle = st.session_state.chronicle
    
    with st.sidebar.expander("📜 Chronicle Info"):
        st.write(f"**Session:** {chronicle.session_id[:8]}...")
        st.write(f"**Events:** {sum(len(p.events) for p in chronicle.timeline.phases)}")
        st.write(f"**Characters:** {len(chronicle.characters)}")
        st.write(f"**Updated:** {datetime.fromisoformat(chronicle.updated_at).strftime('%H:%M')}")
        
        # Recent events
        if chronicle.timeline.phases and chronicle.timeline.phases[-1].events:
            st.write("**Recent Events:**")
            for event in chronicle.timeline.phases[-1].events[-3:]:
                st.write(f"• {event.title}")

def render_game_state_info():
    """Render current game state info."""
    if not st.session_state.game_state:
        return
        
    state = st.session_state.game_state
    
    with st.sidebar.expander("🎯 Current Status"):
        st.write(f"**Location:** {state.current_location}")
        st.write(f"**Time:** {datetime.fromisoformat(state.current_time).strftime('%I:%M %p')}")
        st.write(f"**Mood:** {state.mood}")
        
        # Progress bars
        st.write("**Stress Level:**")
        st.progress(state.stress_level / 100)
        
        st.write("**Energy Level:**")  
        st.progress(state.energy_level / 100)
        
        # Academic status
        if state.academic_status:
            st.write("**Academic Status:**")
            for key, value in state.academic_status.items():
                st.write(f"• {key.title()}: {value}")

def render_chat_interface(game_engine):
    """Render the main chat interface."""
    
    # Chat history display
    st.header("💬 Story Chat")

    # Token usage summary (current turn + running totals)
    current_turn_in = current_turn_out = current_turn_total = None
    try:
        # Find the last DM message with token_usage
        for msg in reversed(st.session_state.chat_history):
            if msg.get("role") == "dm" and isinstance(msg.get("token_usage"), dict):
                usage = msg.get("token_usage") or {}
                current_turn_in = usage.get("prompt_tokens")
                current_turn_out = usage.get("completion_tokens")
                current_turn_total = usage.get("total_tokens")
                break
    except Exception:
        pass
    running_sent = st.session_state.get("token_sent_total", 0)
    running_total = st.session_state.get("token_total_overall", 0)
    with st.container():
        parts = []
        if current_turn_total is not None:
            parts.append(f"this turn: {current_turn_total} (in {current_turn_in or 0}, out {current_turn_out or 0})")
        parts.append(f"running sent: {running_sent}")
        parts.append(f"running total: {running_total}")
        st.caption("Tokens — " + " • ".join(parts))
    
    chat_container = st.container()
    
    with chat_container:
        for msg_idx, message in enumerate(st.session_state.chat_history):
            if message["role"] == "user":
                st.markdown(f"""
                <div class="chat-message user-message">
                    <strong>You:</strong> {_html_safe(message["content"])}
                </div>
                """, unsafe_allow_html=True)
            
            elif message["role"] == "dm":
                # Compose DM bubble with optional token info
                token_info_html = ""
                usage = message.get("token_usage") or {}
                turn_total = usage.get("total_tokens")
                turn_in = usage.get("prompt_tokens")
                turn_out = usage.get("completion_tokens")
                running_sent = message.get("running_token_sent_total")
                running_overall = message.get("running_token_total_overall")
                if turn_total is not None or running_sent is not None or running_overall is not None:
                    parts = []
                    if turn_total is not None:
                        stage = message.get("turn_stage")
                        label = "this turn (struct)" if stage == "struct" else "this turn"
                        parts.append(f"{label}: {turn_total} (in {turn_in or 0}, out {turn_out or 0})")
                    if running_sent is not None:
                        parts.append(f"running sent: {running_sent}")
                    if running_overall is not None:
                        parts.append(f"running total: {running_overall}")
                    token_info_html = f"<div class=\"system-info\">Tokens — {' • '.join(parts)}</div>"
                st.markdown(f"""
                <div class="chat-message dm-message">
                    <strong>Dungeon Master:</strong><br>
                    {_html_safe(message["content"])}
                    {token_info_html}
                </div>
                """, unsafe_allow_html=True)
                
                # Show suggested actions
                if "suggested_actions" in message:
                    with st.expander("💡 Suggested Actions"):
                        for act_idx, action in enumerate(message["suggested_actions"]):
                            # Ensure widget keys are unique across the page using message index + action index
                            if st.button(f"➤ {action}", key=f"action_{msg_idx}_{act_idx}"):
                                process_user_input(action, game_engine)
                                st.rerun()
            
            elif message["role"] == "system":
                st.info(f"System: {message['content']}")
    
    # Input area
    st.markdown("---")
    
    # Quick action buttons if available
    if (st.session_state.chat_history and 
        st.session_state.chat_history[-1]["role"] == "dm" and
        "suggested_actions" in st.session_state.chat_history[-1]):
        
        st.write("**Quick Actions:**")
        cols = st.columns(3)
        actions = st.session_state.chat_history[-1]["suggested_actions"][:3]
        
        for i, action in enumerate(actions):
            with cols[i]:
                if st.button(f"🎯 {action}", key=f"quick_{i}", use_container_width=True):
                    process_user_input(action, game_engine)
                    st.rerun()
        
        st.markdown("---")
    
    # Text input
    user_input = st.chat_input("What do you do next?")
    
    if user_input:
        process_user_input(user_input, game_engine)
        st.rerun()


def _read_scenario_file(path: Path) -> Dict[str, Any]:
    import yaml as _yaml
    with open(path, "r", encoding="utf-8") as f:
        if path.suffix.lower() == ".json":
            return json.load(f)
        else:
            return _yaml.safe_load(f)

def _write_scenario_file(path: Path, data: Dict[str, Any]):
    import yaml as _yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(_yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

def _get_mongo_db_from_env():
    """Return a Mongo DB handle if configured, else None."""
    try:
        def _s(name: str):
            try:
                v = st.secrets.get(name)
            except Exception:
                v = None
            if v:
                return v
            try:
                general = st.secrets.get("general") or st.secrets["general"]
                return general.get(name) if isinstance(general, dict) else general[name]
            except Exception:
                return os.getenv(name)
        uri = _s("MONGODB_URI") or os.getenv("MONGODB_URI")
        user = _s("MONGODB_USERNAME") or os.getenv("MONGODB_USERNAME")
        pw = _s("MONGODB_PASSWORD") or os.getenv("MONGODB_PASSWORD")
        dbname = _s("MONGODB_DATABASE_NAME") or os.getenv("MONGODB_DATABASE_NAME") or "storyos"
        if not uri:
            return None
        if "<username>" in uri and user:
            uri = uri.replace("<username>", str(user))
        if "<password>" in uri and pw:
            uri = uri.replace("<password>", str(pw))
        ms = MongoSetup(uri=uri, db_name=dbname)
        return ms.db
    except Exception:
        return None

def render_admin_screen(scenario_registry):
    st.title("🛠️ Scenario Admin")
    st.caption("Browse, edit, and save scenarios.")

    # Show current system prompt (rendered Markdown)
    with st.expander("📜 View System Prompt (Markdown)", expanded=False):
        try:
            db = _get_mongo_db_from_env()
            doc = None
            if db is not None:
                try:
                    col = db["sos_system_prompts"]
                    doc = col.find_one({"active": True}) or col.find_one(sort=[("updated_at", -1)])
                except Exception:
                    doc = None
            if doc and isinstance(doc.get("content"), str) and doc.get("content").strip():
                st.markdown(doc["content"])  # Prefer DB prompt
            else:
                prompt_path = Path("config/system_prompt.md")
                if prompt_path.exists():
                    st.markdown(prompt_path.read_text(encoding="utf-8"))
                else:
                    st.info("No system prompt found in DB or config/system_prompt.md.")
        except Exception as e:
            st.error(f"Failed to load system prompt: {e}")

    top = st.container()
    body = st.container()

    # Prefer MongoDB scenarios; fallback to filesystem
    db = _get_mongo_db_from_env()
    using_db = False
    docs: list[dict] = []
    labels_db: list[str] = []
    if db is not None:
        try:
            col = db["sos_scenario_templates"]
            # Exclude _id to keep JSON clean in the editor
            docs = list(col.find({}, {"_id": 0}).sort("name", 1))
            if docs:
                using_db = True
                labels_db = [f"{d.get('name', d.get('id',''))} ({d.get('id','')})" for d in docs]
        except Exception:
            using_db = False
            docs = []
            labels_db = []

    packs_dir = Path("scenarios/packs")
    files = sorted([*packs_dir.glob("*.json"), *packs_dir.glob("*.yaml"), *packs_dir.glob("*.yml")]) if not using_db else []
    labels_fs = [f"{p.stem} ({p.name})" for p in files]

    with top:
        cols = st.columns([3,1])
        with cols[0]:
            if using_db:
                selected_label = st.selectbox("Available Scenarios (MongoDB)", options=labels_db or ["(none found)"])
            else:
                selected_label = st.selectbox("Available Scenarios (files)", options=labels_fs or ["(none found)"])
        with cols[1]:
            if st.button("Exit Admin", use_container_width=True):
                st.session_state.admin_mode = False
                st.rerun()

    # Load selected scenario into the editor
    if using_db and labels_db and selected_label in labels_db:
        idx = labels_db.index(selected_label)
        doc = docs[idx]
        # Only reload editor if selection changed
        selected_key = f"db:{doc.get('id','')}"
        if st.session_state.get("admin_selected_path") != selected_key:
            try:
                st.session_state.admin_editor_text = json.dumps(doc, indent=2)
                st.session_state.admin_selected_path = selected_key
                # Seed simplified field editors
                st.session_state["admin_setting_text"] = str(doc.get("setting", ""))
                st.session_state["admin_dm_behaviour_text"] = str(doc.get("dungeon_master_behaviour", ""))
                st.session_state["admin_initial_location_text"] = str(doc.get("player_name", ""))
                st.session_state["admin_player_name_text"] = str(doc.get("player_name", ""))
                st.session_state["admin_role_text"] = str(doc.get("role", ""))
                st.session_state["admin_version_text"] = str(doc.get("version", "1.0.0"))
                st.session_state["admin_author_text"] = str(doc.get("author", "Unknown"))
                st.session_state["admin_created_at_text"] = str(doc.get("created_at", datetime.now().isoformat()))
            except Exception as e:
                st.error(f"Failed to load scenario from DB: {e}")
                st.session_state.admin_editor_text = "{}"
                st.session_state.admin_selected_path = selected_key
                st.session_state["admin_setting_text"] = ""
                st.session_state["admin_dm_behaviour_text"] = ""
                st.session_state["admin_initial_location_text"] = ""
                st.session_state["admin_player_name_text"] = ""
                st.session_state["admin_role_text"] = ""
                st.session_state["admin_version_text"] = "1.0.0"
                st.session_state["admin_author_text"] = "Unknown"
                st.session_state["admin_created_at_text"] = datetime.now().isoformat()

    elif not using_db and files and selected_label in labels_fs:
        idx = labels_fs.index(selected_label)
        path = files[idx]
        if st.session_state.admin_selected_path != str(path):
            # Load file into editor state on selection change
            try:
                data = _read_scenario_file(path)
                st.session_state.admin_editor_text = json.dumps(data, indent=2)
                st.session_state.admin_selected_path = str(path)
                # Seed simplified field editors
                st.session_state["admin_setting_text"] = str(data.get("setting", ""))
                st.session_state["admin_dm_behaviour_text"] = str(data.get("dungeon_master_behaviour", ""))
                st.session_state["admin_initial_location_text"] = str(data.get("player_name", ""))
                st.session_state["admin_player_name_text"] = str(data.get("player_name", ""))
                st.session_state["admin_role_text"] = str(data.get("role", ""))
                st.session_state["admin_version_text"] = str(data.get("version", "1.0.0"))
                st.session_state["admin_author_text"] = str(data.get("author", "Unknown"))
                st.session_state["admin_created_at_text"] = str(data.get("created_at", datetime.now().isoformat()))
            except Exception as e:
                st.error(f"Failed to load scenario: {e}")
                st.session_state.admin_editor_text = "{}"
                st.session_state.admin_selected_path = str(path)
                st.session_state["admin_setting_text"] = ""
                st.session_state["admin_dm_behaviour_text"] = ""
                st.session_state["admin_initial_location_text"] = ""
                st.session_state["admin_player_name_text"] = ""
                st.session_state["admin_role_text"] = ""
                st.session_state["admin_version_text"] = "1.0.0"
                st.session_state["admin_author_text"] = "Unknown"
                st.session_state["admin_created_at_text"] = datetime.now().isoformat()

    tabs = st.tabs(["Overview"])  # Keep existing editor behavior

    with tabs[0]:
        try:
            parsed = json.loads(st.session_state.admin_editor_text or "{}")
        except Exception:
            parsed = {}
        # Editable key fields (simplified schema)
        st.subheader("Details")
        colA, colB = st.columns(2)
        with colA:
            name = st.text_input("Name", value=str(parsed.get("name", "")))
            sid = st.text_input("ID", value=str(parsed.get("id", "")))
            author = st.text_input("Author", value=st.session_state.get("admin_author_text", "Unknown"))
            version = st.text_input("Version", value=st.session_state.get("admin_version_text", "1.0.0"))
        with colB:
            created_at = st.text_input("Created At (ISO)", value=st.session_state.get("admin_created_at_text", datetime.now().isoformat()))
            player_name = st.text_input("Player Name", value=st.session_state.get("admin_player_name_text", ""))
            role = st.text_input("Role", value=st.session_state.get("admin_role_text", ""))
            initial_location = st.text_input("Initial Location", value=st.session_state.get("admin_initial_location_text", ""))

        desc = st.text_area("Description", value=str(parsed.get("description", "")), height=120)

        st.markdown("---")
        st.subheader("Scenario Text Sections")
        setting_text = st.text_area("Setting (text)", value=st.session_state.get("admin_setting_text", ""), height=180, key="admin_setting_text_area")
        dm_behavior_text = st.text_area("Dungeon Master Behaviour (text)", value=st.session_state.get("admin_dm_behaviour_text", ""), height=220, key="admin_dm_behaviour_text_area")

        if st.button("Apply to JSON", type="secondary"):
            try:
                parsed["name"] = name
                parsed["id"] = sid
                parsed["author"] = author
                parsed["version"] = version
                parsed["description"] = desc
                parsed["created_at"] = created_at
                parsed["player_name"] = player_name
                parsed["role"] = role
                parsed["initial_location"] = initial_location
                parsed["setting"] = setting_text
                parsed["dungeon_master_behaviour"] = dm_behavior_text

                # Persist simplified fields to session
                st.session_state["admin_setting_text"] = setting_text
                st.session_state["admin_dm_behaviour_text"] = dm_behavior_text
                st.session_state["admin_initial_location_text"] = initial_location
                st.session_state["admin_player_name_text"] = player_name
                st.session_state["admin_role_text"] = role
                st.session_state["admin_version_text"] = version
                st.session_state["admin_author_text"] = author
                st.session_state["admin_created_at_text"] = created_at

                st.session_state.admin_editor_text = json.dumps(parsed, indent=2)
                st.success("Applied changes to JSON editor")
            except Exception as e:
                st.error(f"Failed to apply: {e}")

        st.markdown("---")
        st.subheader("Save from Overview")
        colsv = st.columns(2)
        with colsv[0]:
            if st.button("Save (validate)", type="primary", use_container_width=True, key="admin_overview_save"):
                try:
                    data = parsed
                    from scenarios.schema import validate_scenario_dict
                    validate_scenario_dict(data)
                    _write_scenario_file(Path(st.session_state.admin_selected_path), data)
                    scenario_registry.reload()
                    st.session_state.admin_editor_text = json.dumps(data, indent=2)
                    st.success("Saved scenario")
                except Exception as e:
                    st.error(f"Save failed: {e}")
        with colsv[1]:
            save_as2 = st.text_input("Save As (filename .json/.yaml)", value=Path(st.session_state.admin_selected_path).name, key="admin_overview_saveas")
            if st.button("Save As New (validate)", use_container_width=True, key="admin_overview_saveas_btn"):
                try:
                    data = parsed
                    from scenarios.schema import validate_scenario_dict
                    validate_scenario_dict(data)
                    target = Path("scenarios/packs") / save_as2
                    _write_scenario_file(target, data)
                    scenario_registry.reload()
                    st.session_state.admin_selected_path = str(target)
                    st.session_state.admin_editor_text = json.dumps(data, indent=2)
                    st.success(f"Saved as {target.name}")
                except Exception as e:
                    st.error(f"Save As failed: {e}")

        st.markdown("---")
        st.subheader("Quick View")
        st.json(parsed)

def _yaml_safe_load(text: str):
    import yaml as _yaml
    return _yaml.safe_load(text)

def _session_default_json(key: str, obj: Any) -> str:
    if key not in st.session_state:
        st.session_state[key] = json.dumps(obj, indent=2)
    return st.session_state[key]

def _html_safe(text: Any) -> str:
    """Escape HTML and preserve newlines as <br>."""
    import html as _html
    s = "" if text is None else str(text)
    s = _html.escape(s)
    return s.replace("\n", "<br>")

def _reconstruct_state_from_chronicle(scenario, chronicle) -> GameState:
    """Best-effort reconstruction of GameState from a saved Chronicle."""
    state = copy.deepcopy(scenario.initial_state)
    try:
        # Location/time
        if getattr(chronicle, "current", None):
            state.current_location = chronicle.current.location or state.current_location
            state.current_time = chronicle.current.time or state.current_time
        # Characters
        if chronicle.characters:
            if "Protagonist" in chronicle.characters:
                state.protagonist = chronicle.characters["Protagonist"]
                # Mirror inventory/relationships to top-level fields for convenience
                state.inventory = list(state.protagonist.inventory)
                state.relationships = dict(state.protagonist.relationships)
            # NPCs
            state.npcs = {k: v for k, v in chronicle.characters.items() if k != "Protagonist"}
        # Mood hints from current context
        if getattr(chronicle, "current", None) and chronicle.current.emotional_context:
            if "high stress" in chronicle.current.emotional_context:
                state.stress_level = max(state.stress_level, 70)
            elif "low stress" in chronicle.current.emotional_context:
                state.stress_level = min(state.stress_level, 30)
    except Exception:
        pass
    return state

def _load_saved_game(path: str, chronicle_manager: ChronicleManager, scenario_registry):
    loaded = chronicle_manager.load_chronicle(path)
    scenario = scenario_registry.get_scenario(loaded.scenario_id)
    if not scenario:
        st.error(f"Scenario '{loaded.scenario_id}' not found for this save.")
        return
    state = _reconstruct_state_from_chronicle(scenario, loaded)
    # Set session
    st.session_state.game_state = state
    st.session_state.chronicle = loaded
    st.session_state.current_scenario = scenario
    st.session_state.initialized = True
    # Try to infer player/story name from filename convention
    try:
        fname = Path(path).name
        if "__" in fname:
            base = fname.rsplit(".json", 1)[0]
            parts = base.split("__")
            if len(parts) >= 3:
                st.session_state.player_name = parts[0]
    except Exception:
        pass
    # Rebuild chat history from the chronicle timeline
    st.session_state.chat_history = _rebuild_chat_history_from_chronicle(loaded)

def _rebuild_chat_history_from_chronicle(chronicle) -> list[Dict[str, Any]]:
    messages: list[Dict[str, Any]] = []
    try:
        # System notice about resume
        messages.append({
            "role": "system",
            "content": f"Resuming saved session {chronicle.session_id[:8]}…",
            "timestamp": datetime.now().isoformat()
        })

        # Flatten and sort events by timestamp ascending
        all_events = []
        for phase in chronicle.timeline.phases:
            for ev in phase.events:
                all_events.append(ev)
        try:
            all_events.sort(key=lambda e: e.timestamp or "")
        except Exception:
            pass

        for ev in all_events:
            if getattr(ev, "player_action", None):
                messages.append({
                    "role": "user",
                    "content": ev.player_action,
                    "timestamp": getattr(ev, "timestamp", datetime.now().isoformat())
                })
            if getattr(ev, "dm_outcome", None):
                messages.append({
                    "role": "dm",
                    "content": ev.dm_outcome,
                    "timestamp": getattr(ev, "timestamp", datetime.now().isoformat())
                })

        # Attach current open choices to the last DM if available
        if messages and chronicle.current and chronicle.current.open_choices:
            # Find last DM message
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "dm":
                    messages[i]["suggested_actions"] = list(chronicle.current.open_choices)
                    break
            else:
                # No DM present; add a fresh prompt from snapshot
                messages.append({
                    "role": "dm",
                    "content": getattr(chronicle.current, "prompt", "What do you do next?"),
                    "suggested_actions": list(chronicle.current.open_choices),
                    "timestamp": chronicle.updated_at or datetime.now().isoformat()
                })

        # If there were no events at all, seed with snapshot prompt
        if len(messages) <= 1 and chronicle.current:
            messages.append({
                "role": "dm",
                "content": getattr(chronicle.current, "prompt", "What do you do next?"),
                "suggested_actions": list(chronicle.current.open_choices) if chronicle.current.open_choices else [],
                "timestamp": chronicle.updated_at or datetime.now().isoformat()
            })
    except Exception:
        # Fallback minimal message
        messages.append({
            "role": "system",
            "content": "Loaded save. Continue your adventure.",
            "timestamp": datetime.now().isoformat()
        })
    return messages

def render_load_game(chronicle_manager: ChronicleManager, scenario_registry):
    with st.sidebar.expander("📥 Load Game"):
        try:
            save_dir = chronicle_manager.saves_dir
            save_files = sorted([p for p in save_dir.glob("*.json")], key=lambda p: p.stat().st_mtime, reverse=True)
            display = [f"{p.name}" for p in save_files]
            selected = st.selectbox("Select a save to load", options=display if display else ["(no saves found)"])
            can_load = bool(save_files) and selected in display
            load_path = save_files[display.index(selected)] if can_load else None
            if st.button("Load Selected", disabled=not can_load, use_container_width=True):
                _load_saved_game(str(load_path), chronicle_manager, scenario_registry)
                st.success(f"Loaded {load_path.name}")
                st.rerun()
        except Exception as e:
            st.error(f"Failed to list saves: {e}")

def process_user_input(user_input: str, game_engine: GameEngine):
    """Process user input and get DM response."""
    
    if not st.session_state.game_state or not st.session_state.current_scenario:
        st.error("Game not initialized!")
        return
    
    try:
        # Add user message to history
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat()
        })
        
        # Stage 1: Stream narrative text only and render live
        placeholder = st.empty()
        # Show immediate feedback while connecting/awaiting first tokens
        placeholder.markdown(
            """
            <div class="chat-message dm-message">
                <strong>Dungeon Master:</strong><br>
                <div class="typing"><span>Dungeon Master is thinking</span><span class="dots"><span></span><span></span><span></span></span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        accumulated = ""
        try:
            stream_iter = game_engine.stream_narrative_text(
                st.session_state.current_scenario,
                st.session_state.game_state,
                st.session_state.chronicle,
                user_input,
            )
            for chunk in stream_iter:
                accumulated += chunk
                placeholder.markdown(f"""
                <div class="chat-message dm-message">
                    <strong>Dungeon Master:</strong><br>
                    {_html_safe(accumulated)}
                </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            # Fallback to non-stream call if needed
            with st.spinner("🎙️ The Dungeon Master is speaking..."):
                accumulated = game_engine.generate_narrative_text(
                    st.session_state.current_scenario,
                    st.session_state.game_state,
                    st.session_state.chronicle,
                    user_input,
                )
                placeholder.markdown(f"""
                <div class="chat-message dm-message">
                    <strong>Dungeon Master:</strong><br>
                    {_html_safe(accumulated)}
                </div>
                """, unsafe_allow_html=True)

        narrative_text = accumulated.strip() or "The story continues..."

        # Persist the streamed narrative into chat history
        st.session_state.chat_history.append({
            "role": "dm",
            "content": narrative_text,
            "timestamp": datetime.now().isoformat()
        })

        # Kick off background structured completion without blocking UI
        try:
            future = get_executor().submit(
                game_engine.complete_structured_with_narrative,
                st.session_state.current_scenario,
                st.session_state.game_state,
                st.session_state.chronicle,
                user_input,
                narrative_text,
            )
            st.session_state.struct_future = future
            st.session_state.struct_target_dm_index = len(st.session_state.chat_history) - 1
        except Exception as e:
            logger.error(f"Failed to schedule structured completion: {e}")
        # Let render continue; future will be handled in main()
        
    except Exception as e:
        logger.error(f"Error processing user input: {e}")
        st.error(f"Something went wrong: {e}")
        
        # Add error message to chat
        st.session_state.chat_history.append({
            "role": "system",
            "content": f"Error processing turn: {e}",
            "timestamp": datetime.now().isoformat()
        })

def initialize_new_game(scenario, game_engine, story_label: Optional[str] = None):
    """Initialize a new game with the selected scenario."""
    try:
        with st.spinner("🌟 Starting your story..."):
            game_state, chronicle = game_engine.initialize_new_game(scenario, story_label=story_label)
            
            st.session_state.game_state = game_state
            st.session_state.chronicle = chronicle
            st.session_state.current_scenario = scenario
            st.session_state.chat_history = []
            st.session_state.initialized = True
            # Reset token counters for a fresh session
            st.session_state.token_sent_total = 0
            st.session_state.token_total_overall = 0
            # Apply age gate setting to policy
            if st.session_state.chronicle and hasattr(st.session_state.chronicle, "policy"):
                st.session_state.chronicle.policy.age_verified = bool(st.session_state.age_verified)
            
            # Add initial system message
            st.session_state.chat_history.append({
                "role": "system",
                "content": f"Welcome to '{scenario.name}'! {scenario.description}",
                "timestamp": datetime.now().isoformat()
            })
            
            # Add initial DM message
            initial_prompt = f"""Welcome to {scenario.name}!

{scenario.description}

You find yourself {game_state.current_location.lower()}. {chronicle.current.emotional_context}

What would you like to do first?"""
            
            st.session_state.chat_history.append({
                "role": "dm",
                "content": initial_prompt,
                "suggested_actions": chronicle.current.open_choices,
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"Initialized new game with scenario {scenario.id}")
            
    except Exception as e:
        st.error(f"Failed to initialize game: {e}")
        logger.error(f"Game initialization error: {e}")

def _list_save_files(chronicle_manager: ChronicleManager):
    try:
        save_dir = chronicle_manager.saves_dir
        files = sorted([p for p in save_dir.glob("*.json")], key=lambda p: p.stat().st_mtime, reverse=True)
        labels = [f"{p.name}" for p in files]
        return files, labels
    except Exception:
        return [], []

def render_home_portal(scenario_registry: ScenarioRegistry, chronicle_manager: ChronicleManager, game_engine: GameEngine):
    st.header("Welcome")
    st.caption("Choose an action to begin.")

    # Top-level actions
    top_cols = st.columns([1, 1, 1])
    with top_cols[0]:
        if st.button("🛠️ Open Admin", use_container_width=True):
            st.session_state.admin_mode = True
            st.rerun()
    with top_cols[1]:
        pass
    with top_cols[2]:
        # Show current account and a logout shortcut
        if st.session_state.get("auth_user"):
            st.info(f"Logged in as: {st.session_state.auth_user}")

    st.markdown("---")
    col_left, col_right = st.columns([3, 2])

    # New Game pane
    with col_left:
        st.subheader("Start a New Game")
        scenarios = scenario_registry.list_scenarios()
        if not scenarios:
            st.error("No scenarios found. Add files to scenarios/packs/ to begin.")
        else:
            options = {f"{s.name} ({s.id})": s for s in scenarios}
            choice = st.selectbox("Scenario", list(options.keys()), key="home_scenario_select")
            selected = options[choice] if choice else None
            if selected:
                with st.expander("Scenario Details", expanded=False):
                    st.write(f"**Author:** {selected.author}")
                    st.write(f"**Version:** {selected.version}")
                    st.write(selected.description)
            placeholder_text = (
                f"e.g., {st.session_state.auth_user}'s Campus Adventure" if st.session_state.get("auth_user") else "e.g., Alex's Campus Adventure"
            )
            story_name = st.text_input("Story name", value=st.session_state.get("player_name", ""), placeholder=placeholder_text, key="home_story_name")
            start_disabled = not bool(story_name.strip()) or selected is None
            if st.button("🚀 Start New Game", type="primary", use_container_width=True, disabled=start_disabled):
                try:
                    st.session_state.player_name = story_name.strip()
                    initialize_new_game(selected, game_engine, story_label=st.session_state.player_name)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to start game: {e}")

    # Load Game pane
    with col_right:
        st.subheader("Load a Saved Game")
        files, labels = _list_save_files(chronicle_manager)
        if not files:
            st.info("No saves found yet.")
        else:
            selected_label = st.selectbox("Saved files", options=labels, key="home_save_select")
            can_load = selected_label in labels
            if st.button("📥 Load Selected", use_container_width=True, disabled=not can_load):
                try:
                    path = files[labels.index(selected_label)]
                    _load_saved_game(str(path), chronicle_manager, scenario_registry)
                    st.success(f"Loaded {path.name}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Load failed: {e}")

def main():
    """Main application function."""
    
    st.title("📚 storyOS")
    st.subheader("Interactive Narrative Chat with Scenario-Defined DM")
    
    # Initialize session state early and enforce auth
    initialize_session_state()
    if not ensure_authenticated():
        return
    
    # Initialize services (after auth)
    llm_service, chronicle_manager, scenario_registry, game_engine = initialize_services()
    
    # If admin requested, render admin full screen
    if st.session_state.admin_mode:
        render_admin_screen(scenario_registry)
        return

    # If no active game, show main hub (not sidebar-driven)
    if not st.session_state.initialized:
        render_home_portal(scenario_registry, chronicle_manager, game_engine)
        return

    # Render game controls and info if game is active
    render_game_controls(game_engine, chronicle_manager, scenario_registry)
    render_chronicle_info()
    render_game_state_info()
    render_chat_interface(game_engine)

if __name__ == "__main__":
    main()
