import os
import logging
import streamlit as st
from typing import Optional, Tuple

from config.settings import secret, SERVICES_VERSION
from services.mongo import MongoSetup
from services.llm import LLMService
from memory.chronicle import ChronicleManager
from scenarios.registry import ScenarioRegistry
from dm.engine import GameEngine
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@st.cache_resource
def get_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="storyos")


def get_mongo_db_from_env():
    try:
        uri = secret("MONGODB_URI") or os.getenv("MONGODB_URI")
        user = secret("MONGODB_USERNAME") or os.getenv("MONGODB_USERNAME")
        pw = secret("MONGODB_PASSWORD") or os.getenv("MONGODB_PASSWORD")
        dbname = secret("MONGODB_DATABASE_NAME") or os.getenv("MONGODB_DATABASE_NAME") or "storyos"
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


@st.cache_resource
def initialize_services() -> Tuple[LLMService, ChronicleManager, ScenarioRegistry, GameEngine]:
    try:
        logger.info(f"Initializing services (version={SERVICES_VERSION})")
        # LLM creds
        api_key = secret("XAI_API_KEY") or os.getenv("XAI_API_KEY") or secret("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = secret("XAI_BASE_URL") or os.getenv("XAI_BASE_URL") or secret("OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.x.ai/v1"
        default_model = secret("DEFAULT_MODEL") or os.getenv("DEFAULT_MODEL", "grok-beta")
        # Encryption
        encryption_key = secret("STORYOS_AES_KEY") or os.getenv("STORYOS_AES_KEY") or secret("CHRONICLE_ENCRYPTION_KEY") or os.getenv("CHRONICLE_ENCRYPTION_KEY")
        # Mongo init
        mongo_uri = secret("MONGODB_URI") or os.getenv("MONGODB_URI")
        mongo_user = secret("MONGODB_USERNAME") or os.getenv("MONGODB_USERNAME")
        mongo_pass = secret("MONGODB_PASSWORD") or os.getenv("MONGODB_PASSWORD")
        mongo_db = secret("MONGODB_DATABASE_NAME") or os.getenv("MONGODB_DATABASE_NAME") or "storyos"
        if mongo_uri:
            try:
                if "<username>" in mongo_uri and mongo_user:
                    mongo_uri = mongo_uri.replace("<username>", str(mongo_user))
                if "<password>" in mongo_uri and mongo_pass:
                    mongo_uri = mongo_uri.replace("<password>", str(mongo_pass))
                ms = MongoSetup(uri=mongo_uri, db_name=mongo_db)
                ms.initialize_if_needed()
            except Exception as e:
                logger.error(f"Mongo setup failed: {e}")
        if not api_key:
            st.error("API key not found. Please set XAI_API_KEY (for Grok) or OPENAI_API_KEY.")
            st.stop()
        llm_service = LLMService(api_key=api_key, base_url=base_url, default_model=default_model)
        chronicle_manager = ChronicleManager(encryption_key=encryption_key)
        scenario_registry = ScenarioRegistry()
        game_engine = GameEngine(llm_service, chronicle_manager)
        return llm_service, chronicle_manager, scenario_registry, game_engine
    except Exception as e:
        st.error(f"Failed to initialize services: {e}")
        st.stop()
