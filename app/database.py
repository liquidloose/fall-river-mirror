import sqlite3
import logging
from typing import List, Tuple, Optional, Union
from datetime import datetime

from app.data_classes import Committee


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
        self.logger.setLevel(logging.INFO)

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
            self.conn = sqlite3.connect(self.db_path)
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
            "title TEXT, "  # Transcript title
            "content TEXT, "  # Full transcript content
            "date TEXT, "  # Meeting date
            "category TEXT",
        )  # Transcript category

        # Journalists table - stores reporter information
        self._create_table(
            "journalists",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT UNIQUE NOT NULL, "  # Full journalist name (for enum sync)
            "first_name TEXT, "  # Journalist's first name
            "last_name TEXT, "  # Journalist's last name
            "organization TEXT, "  # News organization
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
            "description TEXT, "  # Committee description
            "created_date TEXT",
        )  # When committee was established

        # Tones table - stores available tones for articles
        self._create_table(
            "tones",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT UNIQUE NOT NULL, "  # Tone name (required, unique)
            "description TEXT, "  # Tone description
            "created_date TEXT",
        )  # When tone was added

        # Article Types table - stores available article types
        self._create_table(
            "article_types",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT UNIQUE NOT NULL, "  # Article type name (required, unique)
            "description TEXT, "  # Article type description
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

    def add_transcript(
        self, committee: str, title: str, content: str, date: str, category: str
    ) -> None:
        """
        Add a new transcript to the database.

        Args:
            committee: Name of the committee
            title: Title of the transcript
            content: Full transcript content
            date: Date of the meeting
            category: Category of the transcript
        """
        operation_details = {
            "committee": committee,
            "title": title,
            "date": date,
            "category": category,
        }
        self._log_operation("add_transcript", operation_details)

        try:
            self.cursor.execute(
                "INSERT INTO transcripts (committee, title, content, date, category) VALUES (?, ?, ?, ?, ?)",
                (committee, title, content, date, category),
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
            # Create a fresh connection for this operation to avoid threading issues
            fresh_conn = sqlite3.connect(self.db_path)
            fresh_cursor = fresh_conn.cursor()

            try:
                fresh_cursor.execute(
                    "SELECT COUNT(*) FROM transcripts WHERE title LIKE ?",
                    (f"%{youtube_id}%",),
                )
                count = fresh_cursor.fetchone()[0]
                exists = count > 0
                self.logger.info(
                    f"Transcript for YouTube ID '{youtube_id}' exists: {exists}"
                )
                return exists
            finally:
                fresh_cursor.close()
                fresh_conn.close()

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
            # Create a fresh connection for this operation to avoid threading issues
            fresh_conn = sqlite3.connect(self.db_path)
            fresh_cursor = fresh_conn.cursor()

            try:
                fresh_cursor.execute(
                    "SELECT * FROM transcripts WHERE title LIKE ?", (f"%{youtube_id}%",)
                )
                transcript = fresh_cursor.fetchone()
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
            finally:
                fresh_cursor.close()
                fresh_conn.close()

        except Exception as e:
            self._log_error(
                "get_transcript_by_youtube_id", e, {"youtube_id": youtube_id}
            )
            return None

    def add_youtube_transcript(
        self,
        youtube_id: str,
        transcript_content: str,
        committee: object = Committee.BOARD_OF_HEALTH,
        category: str = "YouTube Transcript",
    ) -> int:
        """
        Add a YouTube transcript to the database.

        Args:
            youtube_id: YouTube video ID
            transcript_content: Full transcript content
            committee: Committee name (default: "YouTube")
            category: Transcript category (default: "Video Transcript")

        Returns:
            int: The ID of the newly created transcript
        """
        operation_details = {
            "youtube_id": youtube_id,
            "committee": committee,
            "category": category,
            "content_length": len(transcript_content),
        }
        self._log_operation("add_youtube_transcript", operation_details)

        try:
            title = youtube_id
            date = datetime.now().isoformat()

            # Debug: Log the database path and operation details
            self.logger.info(f"Adding transcript to database: {self.db_path}")
            self.logger.info(f"Title: {title}")
            self.logger.info(f"Content length: {len(transcript_content)}")
            self.logger.info(f"Date: {date}")

            # Create a fresh connection for this operation to avoid threading issues
            fresh_conn = sqlite3.connect(self.db_path)
            fresh_cursor = fresh_conn.cursor()

            try:
                # Debug: Check if table exists
                fresh_cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts'"
                )
                table_exists = fresh_cursor.fetchone()
                self.logger.info(
                    f"Transcripts table exists: {table_exists is not None}"
                )

                if not table_exists:
                    self.logger.error("Transcripts table does not exist!")
                    # Create the table if it doesn't exist
                    self.logger.info("Creating transcripts table...")
                    fresh_cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS transcripts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            committee TEXT,
                            title TEXT,
                            content TEXT,
                            date TEXT,
                            category TEXT
                        )
                    """
                    )
                    fresh_conn.commit()
                    self.logger.info("Transcripts table created successfully")

                # Now insert the transcript
                self.logger.info(
                    f"Inserting transcript into database: {committee}, {title}, {transcript_content}, {date}, {category}"
                )
                fresh_cursor.execute(
                    "INSERT INTO transcripts (committee, title, content, date, category) VALUES (?, ?, ?, ?, ?)",
                    (committee, title, transcript_content, date, category),
                )
                fresh_conn.commit()

                # Verify the insert worked
                fresh_cursor.execute(
                    "SELECT COUNT(*) FROM transcripts WHERE title LIKE ?",
                    (f"%{youtube_id}%",),
                )
                count = fresh_cursor.fetchone()[0]
                self.logger.info(f"Transcripts in database after insert: {count}")

                transcript_id = fresh_cursor.lastrowid
                self.logger.info(
                    f"Added YouTube transcript for video '{youtube_id}' (ID: {transcript_id})"
                )
                return transcript_id
            finally:
                fresh_cursor.close()
                fresh_conn.close()

        except Exception as e:
            self._log_error("add_youtube_transcript", e, operation_details)
            raise

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
