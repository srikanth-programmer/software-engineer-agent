# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
import asyncpg
from dotenv import load_dotenv
from typing import List, Optional, Any
from uuid import uuid4

# Note the change in the import path to match the official ADK structure
from google.adk.sessions import Session, BaseSessionService
from google.adk.events.event import Event
from pydantic import BaseModel
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

class GetSessionConfig(BaseModel):
  """The configuration of getting a session."""

  num_recent_events: Optional[int] = None
  after_timestamp: Optional[float] = None

class ListSessionsResponse(BaseModel):
  """The response of listing sessions.

  The events and states are not set within each Session object.
  """

  sessions: list[Session] = Field(default_factory=list)

class PostgresSessionService(BaseSessionService):
    """
    A complete and robust asynchronous implementation of BaseSessionService that
    persists agent state and events in a PostgreSQL database using asyncpg.
    """
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Establishes the asynchronous database connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                host=os.getenv("DB_HOST"),
                port=os.getenv("DB_PORT"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD")
            )
            await self.init_db()
            print("Successfully connected to PostgreSQL database and created connection pool.")
        except Exception as e:
            print(f"Error: Could not connect to PostgreSQL database.\n{e}")
            raise

    async def init_db(self):
        """Creates the necessary tables if they do not exist."""
        print("Initializing database tables...")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    app_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    state JSONB NOT NULL,
                    PRIMARY KEY (app_name, user_id, session_id)
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    timestamp FLOAT NOT NULL,
                    event JSONB NOT NULL,
                    FOREIGN KEY (app_name, user_id, session_id) REFERENCES sessions (app_name, user_id, session_id)
                );
            ''')
        print("Tables created or already exist.")

    async def close(self):
        """Closes the database connection pool."""
        if self.pool:
            await self.pool.close()
            print("PostgreSQL connection pool closed.")

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """Explicitly creates a new, empty session in the database."""
        session_id = session_id or str(uuid4())
        initial_state = state or {}
        sql = """
            INSERT INTO sessions (app_name, user_id, session_id, state)
            VALUES ($1, $2, $3, $4);
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql, app_name, user_id, session_id, json.dumps(initial_state))
            print(f"Session '{session_id}' created successfully.")
            return Session(session_id=session_id, state=initial_state)
        except asyncpg.exceptions.UniqueViolationError:
            raise ValueError(f"Session with id '{session_id}' already exists for this app and user.")

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        """Retrieves a session from the database. Returns None if not found."""
        sql = """
            SELECT state FROM sessions
            WHERE app_name = $1 AND user_id = $2 AND session_id = $3;
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(sql, app_name, user_id, session_id)
            if not result:
                return None
            state = json.loads(result['state'])
            events = []
            if config is not None:
                params = [app_name, user_id, session_id]
                sql_events = """
                    SELECT timestamp, event FROM events
                    WHERE app_name = $1 AND user_id = $2 AND session_id = $3
                """
                if config.after_timestamp is not None:
                    sql_events += " AND timestamp > $4"
                    params.append(config.after_timestamp)
                sql_events += " ORDER BY timestamp DESC"
                if config.num_recent_events is not None:
                    sql_events += f" LIMIT {config.num_recent_events}"
                rows = await conn.fetch(sql_events, *params)
                sorted_rows = sorted(rows, key=lambda r: r['timestamp'])
                events = [Event(**json.loads(row['event'])) for row in sorted_rows]
            return Session(session_id=session_id, state=state, events=events)

    async def add_event(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        event: Event
    ) -> None:
        """Adds an event to the database."""
        if event.partial:
            return
        sql = """
            INSERT INTO events (app_name, user_id, session_id, timestamp, event)
            VALUES ($1, $2, $3, $4, $5);
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, app_name, user_id, session_id, event.timestamp, json.dumps(event.dict()))

    async def update_session(self, session: Session, *, app_name: str, user_id: str):
        """Saves or updates a session's state in the database using an UPSERT operation."""
        sql = """
            INSERT INTO sessions (app_name, user_id, session_id, state)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (app_name, user_id, session_id)
            DO UPDATE SET state = EXCLUDED.state;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                sql, app_name, user_id, session.session_id, json.dumps(session.state)
            )

    async def list_sessions(self, *, app_name: str, user_id: str) -> ListSessionsResponse:
        """Lists all sessions for a given app and user."""
        sql = """
            SELECT session_id FROM sessions
            WHERE app_name = $1 AND user_id = $2;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, app_name, user_id)
        
        sessions = [
            Session(session_id=row['session_id'])
            for row in rows
        ]
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        """Deletes a session from the database."""
        async with self.pool.acquire() as conn:
            sql_events = "DELETE FROM events WHERE app_name = $1 AND user_id = $2 AND session_id = $3;"
            await conn.execute(sql_events, app_name, user_id, session_id)
            sql = "DELETE FROM sessions WHERE app_name = $1 AND user_id = $2 AND session_id = $3;"
            await conn.execute(sql, app_name, user_id, session_id)
        print(f"Session '{session_id}' deleted.")