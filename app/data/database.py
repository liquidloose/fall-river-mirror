import sqlite3
import logging
from typing import List, Tuple, Optional, Union
from datetime import datetime

from .data_classes import AIAgent, Committee


class Database:
    """
    Database management class for handling SQLite operations.

    This class provides CRUD (Create, Read, Update, Delete) operations for:
    - Committees: Government committees and boards
    - Journalists: News reporters and writers
    - Transcripts: Meeting transcripts and records
    - Articles: News articles and content

    The database uses foreign key relationships to maintain data integrity
    and prevent orphaned records.
    """

    def __init__(self, db_name: str) -> None:
        """
        Initialize database connection and create tables if they don't exist.

        Args:
            db_name: Name of the database file (without .db extension)
        """
        # Set up logging
        self.logger = logging.getLogger(f"Database_{db_name}")
        self.logger.setLevel(logging.DEBUG)

        # Create console handler if none exists
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.db_path: str = db_name + ".db"
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None
        self.is_connected: bool = False
        self.tables_created: bool = False

        self.logger.info(f"Initializing database: {self.db_path}")
        self._connect()
        self._create_all_tables()
        self.logger.info("Database initialization completed")

    def _connect(self) -> None:
        """
        Establish database connection and update state.
        """
        try:
            # Enable threading mode for SQLite
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.is_connected = True
            self.logger.info(f"Successfully connected to database: {self.db_path}")
        except Exception as e:
            self.is_connected = False
            self.logger.error(f"Failed to connect to database {self.db_path}: {str(e)}")
            raise

    def _create_table(self, table_name: str, columns: str) -> None:
        """
        Create a table if it doesn't exist.

        Args:
            table_name: Name of the table to create
            columns: SQL column definitions
        """
        try:
            self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")
            self.conn.commit()
            self.logger.info(f"Table '{table_name}' created/verified successfully")
        except Exception as e:
            self.logger.error(f"Failed to create table '{table_name}': {str(e)}")
            raise

    def _create_all_tables(self) -> None:
        """
        Create all required tables for the application.

        Tables created:
        - committees: Government committees and boards
        - journalists: News reporters and writers
        - transcripts: Meeting transcripts and records
        - articles: News articles with foreign key relationships
        - tones: Available tones for articles
        - article_types: Available article types
        """
        self.logger.info("Creating/verifying all database tables...")

        # Transcripts table - stores meeting transcripts with committee reference
        self._create_table(
            "transcripts",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "committee TEXT, "  # Committee name as text
            "youtube_id TEXT, "  # YouTube video ID
            "content TEXT, "  # Full transcript content
            "meeting_date TEXT, "  # YouTube video description
            "yt_published_date TEXT, "  # YouTube video published date
            "fetch_date TEXT, "  # Date when transcript was fetched
            "model TEXT, "  # Transcript model
            "video_title TEXT, "  # YouTube video title
            "video_duration_seconds INTEGER, "  # Video duration in seconds
            "video_duration_formatted TEXT, "  # Video duration in readable format (e.g., "19:03")
            "video_channel TEXT"  # YouTube channel name
        )

        # Journalists table - stores reporter information
        self._create_table(
            "journalists",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "full_name TEXT UNIQUE NOT NULL, "  # Full journalist name (for enum sync)
            "first_name TEXT, "  # Journalist's first name
            "last_name TEXT, "  # Journalist's last name
            "bio TEXT, "  # Journalist biography
            "articles TEXT, "  # List of articles (could be JSON)
            "description TEXT, "  # Additional description
            "created_date TEXT",  # When journalist was added
        )

        # Articles table - stores news articles with foreign key relationships
        self._create_table(
            "articles",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "committee_id INTEGER, "  # Foreign key to committees table
            "youtube_id TEXT, "  # YouTube video ID
            "journalist_id INTEGER, "  # Foreign key to journalists table
            "content TEXT, "  # Article content
            "transcript_id INTEGER, "  # Foreign key to transcripts table
            "date TEXT, "  # Article publication date
            "category TEXT, "  # Article category
            "FOREIGN KEY(committee_id) REFERENCES committees(id), "
            "FOREIGN KEY(journalist_id) REFERENCES journalists(id), "
            "FOREIGN KEY(transcript_id) REFERENCES transcripts(id)",
        )

        # Committees table - stores government committees
        self._create_table(
            "committees",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL, "  # Committee name (required)
            "created_date TEXT",
        )  # When committee was established

        # Tones table - stores available tones for articles
        self._create_table(
            "tones",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT UNIQUE NOT NULL, "  # Tone name (required, unique)
            "created_date TEXT",
        )  # When tone was added

        # Article Types table - stores available article types
        self._create_table(
            "categories",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT UNIQUE NOT NULL, "  # Article type name (required, unique)
            "created_date TEXT",
        )  # When article type was added

        self.tables_created = True
        self.logger.info("All tables created/verified successfully")

    def get_database_state(self) -> dict:
        """
        Get current database state information.

        Returns:
            dict: Dictionary containing database state information
        """
        state = {
            "database_path": self.db_path,
            "is_connected": self.is_connected,
            "tables_created": self.tables_created,
            "connection_status": "Connected" if self.is_connected else "Disconnected",
            "timestamp": datetime.now().isoformat(),
        }

        if self.is_connected and self.cursor:
            try:
                # Get table counts
                tables = [
                    "committees",
                    "journalists",
                    "transcripts",
                    "articles",
                    "tones",
                    "article_types",
                ]
                table_counts = {}

                for table in tables:
                    try:
                        self.cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = self.cursor.fetchone()[0]
                        table_counts[table] = count
                    except sqlite3.OperationalError:
                        table_counts[table] = "Table not found"

                state["table_counts"] = table_counts

                # Get database file size
                import os

                if os.path.exists(self.db_path):
                    file_size_bytes = os.path.getsize(self.db_path)
                    state["file_size_mb"] = round(file_size_bytes / (1024 * 1024), 2)
                    state["file_size_bytes"] = file_size_bytes
                else:
                    state["file_size_mb"] = "File not found"
                    state["file_size_bytes"] = "File not found"

                # Get database schema information
                try:
                    self.cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                    existing_tables = [row[0] for row in self.cursor.fetchall()]
                    state["existing_tables"] = existing_tables
                except Exception as e:
                    state["existing_tables"] = f"Error retrieving tables: {str(e)}"

            except Exception as e:
                state["error"] = f"Failed to get detailed state: {str(e)}"

        return state

    def log_database_state(self) -> None:
        """
        Log current database state information.
        """
        state = self.get_database_state()
        self.logger.info(f"Database state: {state}")

    def get_table_info(self, table_name: str) -> dict:
        """
        Get detailed information about a specific table.

        Args:
            table_name: Name of the table to get info for

        Returns:
            dict: Dictionary containing table information
        """
        if not self.is_connected:
            self.logger.error("Cannot get table info - database not connected")
            return {"error": "Database not connected"}

        try:
            # Get table schema
            self.cursor.execute(f"PRAGMA table_info({table_name})")
            columns = self.cursor.fetchall()

            # Get row count
            self.cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = self.cursor.fetchone()[0]

            table_info = {
                "table_name": table_name,
                "row_count": row_count,
                "columns": [
                    {
                        "name": col[1],
                        "type": col[2],
                        "not_null": bool(col[3]),
                        "primary_key": bool(col[5]),
                    }
                    for col in columns
                ],
            }

            self.logger.info(
                f"Retrieved table info for '{table_name}': {row_count} rows, {len(columns)} columns"
            )
            return table_info

        except Exception as e:
            error_msg = f"Failed to get table info for '{table_name}': {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg}

    def check_database_health(self) -> dict:
        """
        Perform a comprehensive health check on the database.

        Returns:
            dict: Dictionary containing health check results
        """
        health_status = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "unknown",
            "checks": {},
        }

        # Check connection
        if not self.is_connected:
            health_status["checks"]["connection"] = {
                "status": "failed",
                "message": "Database not connected",
            }
            health_status["overall_status"] = "unhealthy"
        else:
            health_status["checks"]["connection"] = {
                "status": "passed",
                "message": "Database connected",
            }

        # Check if tables exist
        if self.is_connected:
            try:
                self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing_tables = [row[0] for row in self.cursor.fetchall()]
                expected_tables = [
                    "committees",
                    "journalists",
                    "transcripts",
                    "articles",
                    "tones",
                    "article_types",
                ]

                missing_tables = [
                    table for table in expected_tables if table not in existing_tables
                ]

                if missing_tables:
                    health_status["checks"]["tables"] = {
                        "status": "failed",
                        "message": f"Missing tables: {missing_tables}",
                        "existing_tables": existing_tables,
                    }
                else:
                    health_status["checks"]["tables"] = {
                        "status": "passed",
                        "message": "All expected tables exist",
                        "existing_tables": existing_tables,
                    }

            except Exception as e:
                health_status["checks"]["tables"] = {
                    "status": "error",
                    "message": f"Error checking tables: {str(e)}",
                }

        # Determine overall status
        failed_checks = [
            check
            for check in health_status["checks"].values()
            if check["status"] == "failed"
        ]
        error_checks = [
            check
            for check in health_status["checks"].values()
            if check["status"] == "error"
        ]

        if failed_checks:
            health_status["overall_status"] = "unhealthy"
        elif error_checks:
            health_status["overall_status"] = "error"
        else:
            health_status["overall_status"] = "healthy"

        self.logger.info(
            f"Database health check completed: {health_status['overall_status']}"
        )
        return health_status

    def _log_operation(self, operation: str, details: dict = None) -> None:
        """
        Log database operations with consistent formatting.

        Args:
            operation: Name of the operation being performed
            details: Additional details about the operation
        """
        log_message = f"Database operation: {operation}"
        if details:
            log_message += f" - Details: {details}"
        self.logger.info(log_message)

    def _log_error(
        self, operation: str, error: Exception, details: dict = None
    ) -> None:
        """
        Log database errors with consistent formatting.

        Args:
            operation: Name of the operation that failed
            error: The exception that occurred
            details: Additional details about the operation
        """
        log_message = f"Database operation failed: {operation} - Error: {str(error)}"
        if details:
            log_message += f" - Details: {details}"
        self.logger.error(log_message)

    def test_write_permissions(self) -> bool:
        """
        Test if the database file is writable by attempting a simple write operation.

        Returns:
            bool: True if writable, False otherwise
        """
        try:
            # Try to create a test table and drop it
            self.cursor.execute("CREATE TABLE IF NOT EXISTS test_write (id INTEGER)")
            self.cursor.execute("DROP TABLE test_write")
            self.conn.commit()
            self.logger.info("Database write permissions test passed")
            return True
        except Exception as e:
            self.logger.error(f"Database write permissions test failed: {str(e)}")
            return False

    def add_transcript(
        self,
        committee: str,
        title: str,
        content: str,
        date: str,
        category: str,
        video_title: str = None,
        video_duration_seconds: int = None,
        video_duration_formatted: str = None,
        video_channel: str = None,
        video_description: str = None,
        youtube_id: str = None,
        fetch_date: str = None,
        model: str = None,
    ) -> None:
        """
        Add a new transcript to the database with optional video metadata.

        Args:
            committee: Name of the committee
            title: Title of the transcript
            content: Full transcript content
            date: Date of the meeting (yt_published_date)
            category: Category of the transcript
            video_title: YouTube video title
            video_duration_seconds: Video duration in seconds
            video_duration_formatted: Video duration in readable format
            video_channel: YouTube channel name
            video_description: YouTube video description
            youtube_id: YouTube video ID
            fetch_date: Date when transcript was fetched
            model: Transcript model used
        """
        operation_details = {
            "committee": committee,
            "title": title,
            "date": date,
            "category": category,
            "video_title": video_title,
            "video_duration_seconds": video_duration_seconds,
            "video_duration_formatted": video_duration_formatted,
            "video_channel": video_channel,
            "youtube_id": youtube_id,
        }
        self._log_operation("add_transcript", operation_details)

        try:
            self.cursor.execute(
                """INSERT INTO transcripts 
                (committee, youtube_id, content, yt_published_date, fetch_date, model, 
                 video_title, video_duration_seconds, video_duration_formatted, 
                 video_channel, video_description) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    committee,
                    youtube_id,
                    content,
                    date,
                    fetch_date,
                    model,
                    video_title,
                    video_duration_seconds,
                    video_duration_formatted,
                    video_channel,
                    video_description,
                ),
            )
            self.conn.commit()
            transcript_id = self.cursor.lastrowid
            self.logger.info(
                f"Added transcript '{title}' for committee '{committee}' (ID: {transcript_id})"
            )
        except Exception as e:
            self._log_error("add_transcript", e, operation_details)
            raise

    def add_journalist(
        self,
        first_name: str,
        last_name: str,
        organization: Optional[str],
        bio: Optional[str],
        articles: Optional[str],
    ) -> None:
        """
        Add a new journalist to the database.

        Args:
            first_name: Journalist's first name
            last_name: Journalist's last name
            organization: News organization (optional)
            bio: Journalist biography (optional)
            articles: List of articles as JSON string (optional)
        """
        operation_details = {
            "first_name": first_name,
            "last_name": last_name,
            "organization": organization,
        }
        self._log_operation("add_journalist", operation_details)

        try:
            self.cursor.execute(
                "INSERT INTO journalists (first_name, last_name, organization, bio, articles) VALUES (?, ?, ?, ?, ?)",
                (first_name, last_name, organization, bio, articles),
            )
            self.conn.commit()
            journalist_id = self.cursor.lastrowid
            self.logger.info(
                f"Added journalist '{first_name} {last_name}' (ID: {journalist_id})"
            )
        except Exception as e:
            self._log_error("add_journalist", e, operation_details)
            raise

    def add_article(
        self,
        committee_id: int,
        youtube_id: str,
        journalist_id: int,
        content: str,
        transcript_id: int,
        date: str,
        category: Optional[str],
    ) -> None:
        """
        Add a new article to the database.

        Note: This method uses foreign key relationships, so all referenced IDs
        must exist in their respective tables.

        Args:
            committee_id: ID of the committee (from committees table)
            youtube_id: YouTube video ID
            journalist_id: ID of the journalist (from journalists table)
            content: Article content
            transcript_id: ID of the transcript (from transcripts table)
            date: Article publication date
            category: Article category (optional)

        Raises:
            sqlite3.IntegrityError: If any foreign key references don't exist
        """
        operation_details = {
            "committee_id": committee_id,
            "youtube_id": youtube_id,
            "journalist_id": journalist_id,
            "transcript_id": transcript_id,
            "date": date,
            "category": category,
        }
        self._log_operation("add_article", operation_details)

        try:
            self.cursor.execute(
                "INSERT INTO articles (committee_id, youtube_id, journalist_id, content, transcript_id, date, category) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    committee_id,
                    youtube_id,
                    journalist_id,
                    content,
                    transcript_id,
                    date,
                    category,
                ),
            )
            self.conn.commit()
            article_id = self.cursor.lastrowid
            self.logger.info(
                f"Added article (ID: {article_id}) for committee_id: {committee_id}, journalist_id: {journalist_id}"
            )
        except Exception as e:
            self._log_error("add_article", e, operation_details)
            raise

    def add_committee(
        self, name: str, description: Optional[str], created_date: Optional[str]
    ) -> None:
        """
        Add a new committee to the database.

        Args:
            name: Name of the committee
            description: Description of the committee (optional)
            created_date: Date when committee was established (optional)
        """
        operation_details = {
            "name": name,
            "description": description,
            "created_date": created_date,
        }
        self._log_operation("add_committee", operation_details)

        try:
            self.cursor.execute(
                "INSERT INTO committees (name, description, created_date) VALUES (?, ?, ?)",
                (name, description, created_date),
            )
            self.conn.commit()
            committee_id = self.cursor.lastrowid
            self.logger.info(f"Added committee '{name}' (ID: {committee_id})")
        except Exception as e:
            self._log_error("add_committee", e, operation_details)
            raise

    def get_transcripts(self) -> List[Tuple[Union[int, str]]]:
        """
        Retrieve all transcripts from the database.

        Returns:
            List of tuples containing transcript data.
            Each tuple contains: (id, committee, title, content, date, category)
        """
        self._log_operation("get_transcripts")

        try:
            self.cursor.execute("SELECT * FROM transcripts")
            transcripts = self.cursor.fetchall()
            self.logger.info(f"Retrieved {len(transcripts)} transcripts from database")
            return transcripts
        except Exception as e:
            self._log_error("get_transcripts", e)
            raise

    def transcript_exists_by_youtube_id(
        self,
        youtube_id: str,
    ) -> bool:
        """
        Check if a transcript exists for a given YouTube video ID.

        Args:
            youtube_id: YouTube video ID to check

        Returns:
            bool: True if transcript exists, False otherwise
        """
        self._log_operation(
            "transcript_exists_by_youtube_id",
            {"youtube_id": youtube_id},
        )

        try:
            # Use the existing thread-safe connection
            self.cursor.execute(
                "SELECT COUNT(*) FROM transcripts WHERE youtube_id = ?",
                (youtube_id,),
            )
            count = self.cursor.fetchone()[0]
            exists = count > 0
            self.logger.info(
                f"Transcript for YouTube ID '{youtube_id}' exists: {exists}"
            )
            return exists

        except Exception as e:
            self._log_error(
                "transcript_exists_by_youtube_id", e, {"youtube_id": youtube_id}
            )
            return False

    def get_transcript_by_youtube_id(
        self, youtube_id: str
    ) -> Optional[Tuple[Union[int, str]]]:
        """
        Retrieve a transcript by YouTube video ID.

        Args:
            youtube_id: YouTube video ID to retrieve

        Returns:
            Tuple containing transcript data if found, None otherwise.
            Each tuple contains: (id, committee, title, content, date, category)
        """
        self._log_operation("get_transcript_by_youtube_id", {"youtube_id": youtube_id})

        try:
            # Use the existing thread-safe connection
            self.cursor.execute(
                "SELECT * FROM transcripts WHERE youtube_id = ?", (youtube_id,)
            )
            transcript = self.cursor.fetchone()
            if transcript:
                self.logger.info(
                    f"Retrieved transcript for YouTube ID '{youtube_id}' from database"
                )
                return transcript
            else:
                self.logger.info(
                    f"No transcript found for YouTube ID '{youtube_id}' in database"
                )
                return None

        except Exception as e:
            self._log_error(
                "get_transcript_by_youtube_id", e, {"youtube_id": youtube_id}
            )
            return None

    def get_transcript_by_id(self, transcript_id: int) -> Optional[Tuple]:
        """
        Retrieve a transcript by its ID.

        Args:
            transcript_id: The ID of the transcript to retrieve

        Returns:
            Tuple containing transcript data if found, None otherwise.
            Each tuple contains: (id, committee, title, content, date, category)
        """
        self._log_operation("get_transcript_by_id", {"transcript_id": transcript_id})

        try:
            # Use the existing thread-safe connection
            self.cursor.execute(
                "SELECT * FROM transcripts WHERE id = ?", (transcript_id,)
            )
            transcript = self.cursor.fetchone()
            if transcript:
                self.logger.info(
                    f"Retrieved transcript with ID '{transcript_id}' from database"
                )
                return transcript
            else:
                self.logger.info(
                    f"No transcript found with ID '{transcript_id}' in database"
                )
                return None

        except Exception as e:
            self._log_error("get_transcript_by_id", e, {"transcript_id": transcript_id})
            return None

    def close(self) -> None:
        """
        Close the database connection.

        Call this method when you're done using the database to free up resources.
        """
        if self.is_connected and self.conn:
            self.conn.close()
            self.is_connected = False
            self.cursor = None
            self.logger.info("Database connection closed")
        else:
            self.logger.warning("Attempted to close database that was already closed")

    def reconnect(self) -> None:
        """
        Reopen the database connection after it has been closed.

        This method creates a new connection to the same database file.
        Useful when you need to close and reopen the connection.
        """
        if self.is_connected:
            self.logger.warning(
                "Attempted to reconnect to database that was already connected"
            )
            return

        self.logger.info("Reconnecting to database...")
        self._connect()
        self.logger.info("Database reconnection completed")

    def delete_transcript_by_id(self, transcript_id: int) -> bool:
        """
        Delete a transcript by its ID.

        Args:
            transcript_id: The ID of the transcript to delete

        Returns:
            bool: True if transcript was deleted, False if not found

        Raises:
            Exception: If database operation fails
        """
        operation_details = {"transcript_id": transcript_id}
        self._log_operation("delete_transcript_by_id", operation_details)

        try:
            # Use the existing thread-safe connection
            # First check if transcript exists
            self.cursor.execute(
                "SELECT id FROM transcripts WHERE id = ?", (transcript_id,)
            )
            if not self.cursor.fetchone():
                self.logger.warning(f"Transcript with ID {transcript_id} not found")
                return False

            # Delete the transcript
            self.cursor.execute(
                "DELETE FROM transcripts WHERE id = ?", (transcript_id,)
            )
            self.conn.commit()

            # Check if deletion was successful
            rows_affected = self.cursor.rowcount
            if rows_affected > 0:
                self.logger.info(
                    f"Successfully deleted transcript with ID {transcript_id}"
                )
                return True
            else:
                self.logger.warning(f"No transcript was deleted for ID {transcript_id}")
                return False

        except Exception as e:
            self._log_error("delete_transcript_by_id", e, operation_details)
            raise
