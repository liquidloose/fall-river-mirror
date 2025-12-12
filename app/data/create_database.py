import sqlite3
import logging
from typing import List, Tuple, Optional, Union
from datetime import datetime


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

    def _add_column_if_not_exists(
        self, table_name: str, column_name: str, column_type: str
    ) -> None:
        """
        Add a column to a table if it doesn't already exist.

        Args:
            table_name: Name of the table
            column_name: Name of the column to add
            column_type: SQL type of the column (e.g., 'TEXT', 'INTEGER')
        """
        try:
            self.cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in self.cursor.fetchall()]
            if column_name not in columns:
                self.cursor.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )
                self.conn.commit()
                self.logger.info(
                    f"Added column '{column_name}' to table '{table_name}'"
                )
        except Exception as e:
            self.logger.error(
                f"Failed to add column '{column_name}' to '{table_name}': {str(e)}"
            )

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
        - art: AI-generated artwork
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
            "video_channel TEXT, "  # YouTube channel name
            "view_count INTEGER, "  # YouTube video view count
            "like_count INTEGER, "  # YouTube video like count
            "comment_count INTEGER",  # YouTube video comment count
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
            "committee TEXT, "  # Foreign key to committees table
            "youtube_id TEXT, "  # YouTube video ID
            "journalist_id INTEGER, "  # Foreign key to journalists table
            "title TEXT, "  # Article title
            "content TEXT, "  # Article content
            "transcript_id INTEGER, "  # Foreign key to transcripts table
            "date TEXT, "  # Article publication date
            "tone TEXT, "  # Article tone
            "article_type TEXT, "  # Article type
            "bullet_points TEXT, "  # Bullet point summary
            "FOREIGN KEY(committee) REFERENCES committees(id), "
            "FOREIGN KEY(journalist_id) REFERENCES journalists(id), "
            "FOREIGN KEY(transcript_id) REFERENCES transcripts(id)",
        )
        # Migration: add bullet_points column if it doesn't exist
        self._add_column_if_not_exists("articles", "bullet_points", "TEXT")

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

        # Video Queue table - stores discovered YouTube videos
        self._create_table(
            "video_queue",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "youtube_id TEXT UNIQUE NOT NULL, "  # YouTube video ID
            "transcript_available INTEGER DEFAULT 0",  # Boolean: 0=false, 1=true
        )

        # Art table - stores AI-generated artwork
        self._create_table(
            "art",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "artist_name TEXT, "  # Name of the AI artist
            "title TEXT, "  # Artwork title
            "prompt TEXT, "  # Generation prompt
            "medium TEXT, "  # e.g., "digital", "watercolor"
            "aesthetic TEXT, "  # e.g., "surrealist", "minimalist"
            "image_url TEXT, "  # Original URL from xAI
            "image_data BLOB, "  # Actual image binary data
            "snippet TEXT, "  # AI-generated short summary for image prompt
            "transcript_id INTEGER, "  # If linked to a transcript
            "article_id INTEGER, "  # If linked to an article
            "created_date TEXT, "  # When artwork was generated
            "FOREIGN KEY(transcript_id) REFERENCES transcripts(id), "
            "FOREIGN KEY(article_id) REFERENCES articles(id)",
        )
        # Migration: add artist_name column if it doesn't exist (replaces artist_id)
        self._add_column_if_not_exists("art", "artist_name", "TEXT")
        # Migration: add snippet column if it doesn't exist
        self._add_column_if_not_exists("art", "snippet", "TEXT")
        # Migration: add model column if it doesn't exist
        self._add_column_if_not_exists("art", "model", "TEXT")

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
                    "video_queue",
                    "art",
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
                    "video_queue",
                    "art",
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
        ArticleType: str,
        video_title: str,
        video_duration_seconds: int,
        video_duration_formatted: str,
        video_channel: str,
        video_description: str,
        youtube_id: str,
        fetch_date: str,
        model: str,
        view_count: int,
        like_count: int,
        comment_count: int,
    ) -> None:
        """
        Add a new transcript to the database with video metadata.

        Args:
            committee: Name of the committee
            title: Title of the transcript
            content: Full transcript content
            date: Date of the meeting (yt_published_date)
            ArticleType: ArticleType of the transcript
            video_title: YouTube video title
            video_duration_seconds: Video duration in seconds
            video_duration_formatted: Video duration in readable format
            video_channel: YouTube channel name
            video_description: YouTube video description
            youtube_id: YouTube video ID
            fetch_date: Date when transcript was fetched
            model: Transcript model used
            view_count: YouTube video view count
            like_count: YouTube video like count
            comment_count: YouTube video comment count
        """
        operation_details = {
            "committee": committee,
            "title": title,
            "date": date,
            "ArticleType": ArticleType,
            "video_title": video_title,
            "video_duration_seconds": video_duration_seconds,
            "video_duration_formatted": video_duration_formatted,
            "video_channel": video_channel,
            "youtube_id": youtube_id,
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": comment_count,
        }
        self._log_operation("add_transcript", operation_details)

        try:
            self.cursor.execute(
                """INSERT INTO transcripts 
                (committee, youtube_id, content, yt_published_date, fetch_date, model, 
                 video_title, video_duration_seconds, video_duration_formatted, 
                 video_channel, video_description, view_count, like_count, comment_count) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    view_count,
                    like_count,
                    comment_count,
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
        committee: str,
        youtube_id: str,
        journalist_id: int,
        content: str,
        transcript_id: int,
        date: str,
        article_type: Optional[str],
        tone: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        """
        Add a new article to the database.

        Note: This method uses foreign key relationships, so all referenced IDs
        must exist in their respective tables.

        Args:
            committee: ID of the committee (from committees table)
            youtube_id: YouTube video ID
            journalist_id: ID of the journalist (from journalists table)
            content: Article content
            transcript_id: ID of the transcript (from transcripts table)
            date: Article publication date
           ArticleType: ArticleType (optional)

        Raises:
            sqlite3.IntegrityError: If any foreign key references don't exist
        """
        operation_details = {
            "committee": committee,
            "youtube_id": youtube_id,
            "journalist_id": journalist_id,
            "transcript_id": transcript_id,
            "date": date,
            "article_type": article_type,
            "tone": tone,
            "title": title,
        }
        self._log_operation("add_article", operation_details)

        try:
            self.cursor.execute(
                "INSERT INTO articles (committee, youtube_id, journalist_id, title, content, transcript_id, date, tone, article_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    committee,
                    youtube_id,
                    journalist_id,
                    title,
                    content,
                    transcript_id,
                    date,
                    tone,
                    article_type,
                ),
            )
            self.conn.commit()
            article_id = self.cursor.lastrowid
            self.logger.info(
                f"Added article (ID: {article_id}) for committee: {committee}, journalist_id: {journalist_id}"
            )
        except Exception as e:
            self._log_error("add_article", e, operation_details)
            raise

    def get_article_by_id(self, article_id: int) -> Optional[dict]:
        """
        Retrieve an article by its ID.

        Args:
            article_id: The unique identifier of the article

        Returns:
            Dict with article data or None if not found
        """
        self._log_operation("get_article_by_id", {"article_id": article_id})

        try:
            self.cursor.execute(
                "SELECT id, committee, youtube_id, journalist_id, title, content, transcript_id, date, tone, article_type, bullet_points FROM articles WHERE id = ?",
                (article_id,),
            )
            result = self.cursor.fetchone()

            if result:
                return {
                    "id": result[0],
                    "committee": result[1],
                    "youtube_id": result[2],
                    "journalist_id": result[3],
                    "title": result[4],
                    "content": result[5],
                    "transcript_id": result[6],
                    "date": result[7],
                    "tone": result[8],
                    "article_type": result[9],
                    "bullet_points": result[10],
                }
            return None
        except Exception as e:
            self._log_error("get_article_by_id", e, {"article_id": article_id})
            return None

    def update_article_bullet_points(self, article_id: int, bullet_points: str) -> bool:
        """
        Update bullet points for an existing article.

        Args:
            article_id: The unique identifier of the article
            bullet_points: The bullet point summary text

        Returns:
            True if update succeeded, False otherwise
        """
        self._log_operation(
            "update_article_bullet_points",
            {"article_id": article_id, "bullet_points_len": len(bullet_points)},
        )

        try:
            self.cursor.execute(
                "UPDATE articles SET bullet_points = ? WHERE id = ?",
                (bullet_points, article_id),
            )
            self.conn.commit()
            updated = self.cursor.rowcount > 0
            if updated:
                self.logger.info(f"Updated bullet points for article ID: {article_id}")
            else:
                self.logger.warning(f"No article found with ID: {article_id}")
            return updated
        except Exception as e:
            self._log_error(
                "update_article_bullet_points", e, {"article_id": article_id}
            )
            return False

    def add_art(
        self,
        prompt: str,
        image_url: str,
        image_data: bytes,
        medium: Optional[str] = None,
        aesthetic: Optional[str] = None,
        title: Optional[str] = None,
        artist_name: Optional[str] = None,
        snippet: Optional[str] = None,
        transcript_id: Optional[int] = None,
        article_id: Optional[int] = None,
        model: Optional[str] = None,
    ) -> int:
        """
        Add a new artwork to the database.

        Args:
            prompt: The generation prompt used
            image_url: Original URL from xAI
            image_data: The actual image binary data
            medium: Artistic medium (e.g., "digital")
            aesthetic: Aesthetic style (e.g., "surrealist")
            title: Artwork title (optional)
            artist_name: Name of the AI artist (optional)
            snippet: AI-generated short summary for image prompt (optional)
            transcript_id: ID of linked transcript (optional)
            article_id: ID of linked article (optional)
            model: Image generation model used (optional)

        Returns:
            int: The ID of the newly created art record
        """
        operation_details = {
            "prompt": prompt[:100],  # Truncate for logging
            "image_url": image_url,
            "article_id": article_id,
            "artist_name": artist_name,
            "model": model,
        }
        self._log_operation("add_art", operation_details)

        try:
            created_date = datetime.now().isoformat()
            self.cursor.execute(
                "INSERT INTO art (artist_name, title, prompt, medium, aesthetic, image_url, image_data, snippet, transcript_id, article_id, created_date, model) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artist_name,
                    title,
                    prompt,
                    medium,
                    aesthetic,
                    image_url,
                    image_data,
                    snippet,
                    transcript_id,
                    article_id,
                    created_date,
                    model,
                ),
            )
            self.conn.commit()
            art_id = self.cursor.lastrowid
            self.logger.info(f"Added art (ID: {art_id})")
            return art_id
        except Exception as e:
            self._log_error("add_art", e, operation_details)
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
            committee = self.cursor.lastrowid
            self.logger.info(f"Added committee '{name}' (ID: {committee})")
        except Exception as e:
            self._log_error("add_committee", e, operation_details)
            raise

    def get_transcripts(self) -> List[Tuple[Union[int, str]]]:
        """
        Retrieve all transcripts from the database.

        Returns:
            List of tuples containing transcript data.
            Each tuple contains: (id, committee, title, content, date,ArticleType)
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
            Each tuple contains: (id, committee, title, content, date,ArticleType)
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
            Each tuple contains: (id, committee, title, content, date,ArticleType)
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

    def get_all_articles(self) -> List[dict]:
        """
        Retrieve all articles from the database.

        Returns:
            List of dictionaries containing article data.
            Each dictionary contains: (id, committee, youtube_id, journalist_id, title, content, transcript_id, date, tone, article_type, bullet_points)
        """
        self._log_operation("get_all_articles", {})
        try:
            self.cursor.execute(
                "SELECT id, committee, youtube_id, journalist_id, title, content, "
                "transcript_id, date, tone, article_type, bullet_points FROM articles"
            )
            results = self.cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "committee": row[1],
                    "youtube_id": row[2],
                    "journalist_id": row[3],
                    "title": row[4],
                    "content": row[5],
                    "transcript_id": row[6],
                    "date": row[7],
                    "tone": row[8],
                    "article_type": row[9],
                    "bullet_points": row[10],
                }
                for row in results
            ]
        except Exception as e:
            self._log_error("get_all_articles", e, {})
            return []

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

    def delete_art_by_id(self, art_id: int) -> bool:
        """
        Delete an art record by its ID.

        Args:
            art_id: The ID of the art record to delete

        Returns:
            bool: True if art was deleted, False if not found

        Raises:
            Exception: If database operation fails
        """
        operation_details = {"art_id": art_id}
        self._log_operation("delete_art_by_id", operation_details)

        try:
            # First check if art exists
            self.cursor.execute("SELECT id FROM art WHERE id = ?", (art_id,))
            if not self.cursor.fetchone():
                self.logger.warning(f"Art with ID {art_id} not found")
                return False

            # Delete the art record
            self.cursor.execute("DELETE FROM art WHERE id = ?", (art_id,))
            self.conn.commit()

            # Check if deletion was successful
            rows_affected = self.cursor.rowcount
            if rows_affected > 0:
                self.logger.info(f"Successfully deleted art with ID {art_id}")
                return True
            else:
                self.logger.warning(f"No art was deleted for ID {art_id}")
                return False

        except Exception as e:
            self._log_error("delete_art_by_id", e, operation_details)
            raise

    def get_art_by_id(self, art_id: int) -> Optional[dict]:
        """Retrieve an art record by its ID."""
        self._log_operation("get_art_by_id", {"art_id": art_id})

        try:
            self.cursor.execute(
                "SELECT id, artist_name, title, prompt, medium, aesthetic, image_data, snippet, transcript_id, article_id, created_date, model FROM art WHERE id = ?",
                (art_id,),
            )
            result = self.cursor.fetchone()

            if result:
                return {
                    "id": result[0],
                    "artist_name": result[1],
                    "title": result[2],
                    "prompt": result[3],
                    "medium": result[4],
                    "aesthetic": result[5],
                    "image_data": result[6],
                    "snippet": result[7],
                    "transcript_id": result[8],
                    "article_id": result[9],
                    "created_date": result[10],
                    "model": result[11],
                }
            return None
        except Exception as e:
            self._log_error("get_art_by_id", e, {"art_id": art_id})
            return None
