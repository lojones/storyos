import streamlit as st
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

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
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        background-color: #f0f2f6;
    }
    .user-message {
        background-color: #e3f2fd;
        margin-left: 2rem;
    }
    .dm-message {
        background-color: #f3e5f5;
        margin-right: 2rem;
    }
    .system-info {
        font-size: 0.8rem;
        color: #666;
        font-style: italic;
    }
    .scenario-card {
        border: 1px solid #ddd;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def initialize_services():
    """Initialize core services."""
    try:
        # Get API credentials (prioritize XAI, fallback to OpenAI)
        api_key = (st.secrets.get("XAI_API_KEY") or os.getenv("XAI_API_KEY") or 
                  st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))
        base_url = (st.secrets.get("XAI_BASE_URL") or os.getenv("XAI_BASE_URL") or
                   st.secrets.get("OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.x.ai/v1"))
        default_model = st.secrets.get("DEFAULT_MODEL") or os.getenv("DEFAULT_MODEL", "grok-beta")
        encryption_key = st.secrets.get("CHRONICLE_ENCRYPTION_KEY") or os.getenv("CHRONICLE_ENCRYPTION_KEY")
        
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

def render_scenario_selector(scenario_registry):
    """Render scenario selection interface."""
    st.sidebar.header("📖 Choose Your Story")
    
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
        
        return selected_scenario
    
    return None

def render_game_controls(game_engine, chronicle_manager):
    """Render game control buttons."""
    st.sidebar.header("🎮 Game Controls")
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("💾 Save Game", use_container_width=True):
            if st.session_state.chronicle:
                try:
                    filepath = chronicle_manager.save_chronicle(st.session_state.chronicle)
                    st.sidebar.success(f"Game saved to {Path(filepath).name}")
                except Exception as e:
                    st.sidebar.error(f"Save failed: {e}")
    
    with col2:
        if st.button("🔄 New Game", use_container_width=True):
            st.session_state.game_state = None
            st.session_state.chronicle = None
            st.session_state.chat_history = []
            st.session_state.initialized = False
            st.rerun()
    
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
    
    chat_container = st.container()
    
    with chat_container:
        for message in st.session_state.chat_history:
            if message["role"] == "user":
                st.markdown(f"""
                <div class="chat-message user-message">
                    <strong>You:</strong> {message["content"]}
                </div>
                """, unsafe_allow_html=True)
            
            elif message["role"] == "dm":
                st.markdown(f"""
                <div class="chat-message dm-message">
                    <strong>Dungeon Master:</strong><br>
                    {message["content"]}
                </div>
                """, unsafe_allow_html=True)
                
                # Show suggested actions
                if "suggested_actions" in message:
                    with st.expander("💡 Suggested Actions"):
                        for action in message["suggested_actions"]:
                            if st.button(f"➤ {action}", key=f"action_{hash(action)}_{len(st.session_state.chat_history)}"):
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
        
        # Process turn through game engine
        with st.spinner("🎲 The Dungeon Master is thinking..."):
            dm_response, new_game_state, new_chronicle = game_engine.process_turn(
                st.session_state.current_scenario,
                st.session_state.game_state,
                st.session_state.chronicle,
                user_input
            )
        
        # Update session state
        st.session_state.game_state = new_game_state
        st.session_state.chronicle = new_chronicle
        
        # Add DM response to history
        st.session_state.chat_history.append({
            "role": "dm",
            "content": dm_response.narrative,
            "suggested_actions": dm_response.suggested_actions,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error processing user input: {e}")
        st.error(f"Something went wrong: {e}")
        
        # Add error message to chat
        st.session_state.chat_history.append({
            "role": "system",
            "content": f"Error processing turn: {e}",
            "timestamp": datetime.now().isoformat()
        })

def initialize_new_game(scenario, game_engine):
    """Initialize a new game with the selected scenario."""
    try:
        with st.spinner("🌟 Starting your story..."):
            game_state, chronicle = game_engine.initialize_new_game(scenario)
            
            st.session_state.game_state = game_state
            st.session_state.chronicle = chronicle
            st.session_state.current_scenario = scenario
            st.session_state.chat_history = []
            st.session_state.initialized = True
            
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

def main():
    """Main application function."""
    
    st.title("📚 storyOS")
    st.subheader("Interactive Narrative Chat with Scenario-Defined DM")
    
    # Initialize services
    llm_service, chronicle_manager, scenario_registry, game_engine = initialize_services()
    
    # Initialize session state
    initialize_session_state()
    
    # Test LLM connection
    if st.sidebar.button("🔍 Test LLM Connection"):
        with st.sidebar:
            with st.spinner("Testing connection..."):
                success, message = llm_service.test_connection()
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
    
    # Scenario selection
    selected_scenario = render_scenario_selector(scenario_registry)
    
    # Initialize game if scenario selected and not initialized
    if selected_scenario and not st.session_state.initialized:
        if st.sidebar.button("🚀 Start Story", type="primary", use_container_width=True):
            initialize_new_game(selected_scenario, game_engine)
            st.rerun()
    
    # Render game controls and info if game is active
    if st.session_state.initialized:
        render_game_controls(game_engine, chronicle_manager)
        render_chronicle_info()
        render_game_state_info()
        
        # Main chat interface
        render_chat_interface(game_engine)
    
    else:
        # Welcome screen
        if selected_scenario:
            st.info("Click 'Start Story' in the sidebar to begin your adventure!")
        else:
            st.info("Select a scenario from the sidebar to get started.")
            
        # Show available scenarios
        scenarios = scenario_registry.list_scenarios()
        if scenarios:
            st.header("🎭 Available Stories")
            
            for scenario in scenarios[:3]:  # Show first 3
                with st.expander(f"📖 {scenario.name}"):
                    st.write(f"**Author:** {scenario.author}")
                    st.write(f"**Tags:** {', '.join(scenario.tags)}")
                    st.write(scenario.description)
                    
                    if scenario.safety.sfw_lock:
                        st.info("🔒 SFW Content")
                    
                    if scenario.safety.trigger_warnings:
                        st.warning(f"⚠️ Content warnings: {', '.join(scenario.safety.trigger_warnings)}")

if __name__ == "__main__":
    main()