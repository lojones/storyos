from __future__ import annotations

from typing import Optional
from datetime import datetime
import logging
from pathlib import Path
import json

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid

logger = logging.getLogger(__name__)


class MongoSetup:
    """
    Ensures MongoDB collections and indexes exist for storyOS.

    Collections:
    - users: local authentication and profile
      { _id:ObjectId, username:str, password_hash:str, created_at:iso, last_login:iso, roles:[str] }
      Indexes: unique(username)

    - scenario_templates: simplified scenario definitions used by the app
      { _id:ObjectId, id:str, name:str, description:str, version:str,
        setting:str, dungeon_master_behaviour:str, initial_location:str,
        player_name:str, role:str, author:str, created_at:iso, tags:[str] }
      Indexes: unique(id), name, tags

    - system_prompts: markdown prompts (can keep versions; one active at a time)
      { _id:ObjectId, name:str, content:str, version:str, active:bool,
        created_at:iso, updated_at:iso }
      Indexes: unique(name), active

    - game_sessions: ongoing game state instead of explicit saves
      { _id:ObjectId, session_id:str, user_id:str, scenario_id:str,
        status:str,  # active|archived|completed
        game_state:dict, chronicle:dict,
        created_at:iso, updated_at:iso }
      Indexes: unique(session_id), user_id, scenario_id, status, updated_at(desc)
    """

    def __init__(self, uri: str, db_name: str):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]

    def is_initialized(self) -> bool:
        """Check whether required collections exist and have baseline data."""
        try:
            names = set(self.db.list_collection_names())
            have_cols = {
                "sos_users" in names,
                "sos_scenario_templates" in names,
                "sos_system_prompts" in names,
                "sos_game_sessions" in names,
            }
            if not all(have_cols):
                return False
            scen_cnt = self.db["sos_scenario_templates"].count_documents({})
            prompt_cnt = self.db["sos_system_prompts"].count_documents({})
            # Users/sessions may be zero initially
            return scen_cnt > 0 and prompt_cnt > 0
        except Exception:
            return False

    def initialize_if_needed(self) -> None:
        """Ensure schema and seed baseline data if not already present."""
        if self.is_initialized():
            logger.info("Mongo already initialized; skipping seeding.")
            return
        # Create collections/indexes, then seed
        self.ensure_collections_and_indexes()
        self.seed_from_local_files()
        logger.info("Mongo initialization completed.")

    def ensure_collections_and_indexes(self) -> None:
        self._ensure_users()
        self._ensure_scenarios()
        self._ensure_system_prompts()
        self._ensure_game_sessions()
        logger.info("Mongo collections and indexes ensured.")

    # -- Helpers -------------------------------------------------------------

    def _ensure_collection(self, name: str) -> None:
        if name in self.db.list_collection_names():
            return
        try:
            self.db.create_collection(name)
            logger.info(f"Created collection: {name}")
        except CollectionInvalid:
            # already exists (race)
            pass

    def _ensure_users(self) -> None:
        name = "sos_users"
        self._ensure_collection(name)
        col = self.db[name]
        # Indexes
        col.create_index([("username", ASCENDING)], name="uniq_username", unique=True)
        col.create_index([("created_at", DESCENDING)], name="by_created")
        col.create_index([("last_login", DESCENDING)], name="by_last_login")

    def _ensure_scenarios(self) -> None:
        name = "sos_scenario_templates"
        self._ensure_collection(name)
        col = self.db[name]
        col.create_index([("id", ASCENDING)], name="uniq_id", unique=True)
        col.create_index([("name", ASCENDING)], name="by_name")
        col.create_index([("tags", ASCENDING)], name="by_tags")

    def _ensure_system_prompts(self) -> None:
        name = "sos_system_prompts"
        self._ensure_collection(name)
        col = self.db[name]
        col.create_index([("name", ASCENDING)], name="uniq_name", unique=True)
        col.create_index([("active", ASCENDING)], name="by_active")
        col.create_index([("updated_at", DESCENDING)], name="by_updated")

    def _ensure_game_sessions(self) -> None:
        name = "sos_game_sessions"
        self._ensure_collection(name)
        col = self.db[name]
        col.create_index([("session_id", ASCENDING)], name="uniq_session_id", unique=True)
        col.create_index([("user_id", ASCENDING)], name="by_user")
        col.create_index([("scenario_id", ASCENDING)], name="by_scenario")
        col.create_index([("status", ASCENDING)], name="by_status")
        col.create_index([("updated_at", DESCENDING)], name="by_updated_desc")

    # Optional seeding convenience ------------------------------------------

    def seed_system_prompt_if_empty(self, content: str, name: str = "default", version: str = "1.0.0") -> None:
        col = self.db["sos_system_prompts"]
        if col.count_documents({}) == 0:
            now = datetime.now().isoformat()
            col.insert_one({
                "name": name,
                "content": content,
                "version": version,
                "active": True,
                "created_at": now,
                "updated_at": now,
            })
            logger.info("Seeded default system prompt in MongoDB.")

    def seed_from_local_files(self) -> None:
        """Seed initial data from local files.
        - Scenario templates: scenarios/packs/campus_freshman2.json (upsert by id)
        - System prompt: config/system_prompt.md (if empty)
        Users/game_sessions: no-op
        """
        # Scenario template
        scen_path = Path("scenarios/packs/campus_freshman2.json")
        try:
            if scen_path.exists():
                data = json.loads(scen_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("id"):
                    # Ensure timestamps
                    data.setdefault("created_at", datetime.now().isoformat())
                    col = self.db["sos_scenario_templates"]
                    res = col.update_one({"id": data["id"]}, {"$setOnInsert": data}, upsert=True)
                    if res.upserted_id:
                        logger.info(f"Seeded scenario template '{data['id']}' from local file.")
        except Exception as e:
            logger.warning(f"Failed to seed scenario from file: {e}")
        
        # System prompt
        prompt_path = Path("config/system_prompt.md")
        try:
            if prompt_path.exists():
                content = prompt_path.read_text(encoding="utf-8")
                self.seed_system_prompt_if_empty(content, name="default", version="1.0.0")
        except Exception as e:
            logger.warning(f"Failed to seed system prompt from file: {e}")

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
