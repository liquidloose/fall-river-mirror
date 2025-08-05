import sqlite3
from typing import List, Tuple, Optional, Union

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
        self.db_path: str = db_name + ".db"
        self.conn: sqlite3.Connection = sqlite3.connect(self.db_path)
        self.cursor: sqlite3.Cursor = self.conn.cursor()
        self._create_all_tables()   

    def _create_table(self, table_name: str, columns: str) -> None:
        """
        Create a table if it doesn't exist.
        
        Args:
            table_name: Name of the table to create
            columns: SQL column definitions
        """
        self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")
        self.conn.commit()

    def _create_all_tables(self) -> None:
        """
        Create all required tables for the application.
        
        Tables created:
        - committees: Government committees and boards
        - journalists: News reporters and writers  
        - transcripts: Meeting transcripts and records
        - articles: News articles with foreign key relationships
        """
        # Transcripts table - stores meeting transcripts with committee reference
        self._create_table("transcripts", 
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "committee TEXT, "  # Committee name as text
            "title TEXT, "      # Transcript title
            "content TEXT, "    # Full transcript content
            "date TEXT, "       # Meeting date
            "category TEXT")    # Transcript category
        
        # Journalists table - stores reporter information
        self._create_table("journalists", 
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "first_name TEXT, "     # Journalist's first name
            "last_name TEXT, "      # Journalist's last name
            "organization TEXT, "   # News organization
            "bio TEXT, "           # Journalist biography
            "articles TEXT")       # List of articles (could be JSON)
        
        # Articles table - stores news articles with foreign key relationships
        self._create_table("articles", 
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "committee_id INTEGER, "    # Foreign key to committees table
            "youtube_id TEXT, "        # YouTube video ID
            "journalist_id INTEGER, "  # Foreign key to journalists table
            "content TEXT, "           # Article content
            "transcript_id INTEGER, "  # Foreign key to transcripts table
            "date TEXT, "              # Article publication date
            "category TEXT, "          # Article category
            "FOREIGN KEY(committee_id) REFERENCES committees(id), "
            "FOREIGN KEY(journalist_id) REFERENCES journalists(id), "
            "FOREIGN KEY(transcript_id) REFERENCES transcripts(id)")
        
        # Committees table - stores government committees
        self._create_table("committees", 
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL, "     # Committee name (required)
            "description TEXT, "       # Committee description
            "created_date TEXT")       # When committee was established
    
    def add_transcript(self, committee: str, title: str, content: str, date: str, category: str) -> None:
        """
        Add a new transcript to the database.
        
        Args:
            committee: Name of the committee
            title: Title of the transcript
            content: Full transcript content
            date: Date of the meeting
            category: Category of the transcript
        """
        self.cursor.execute(
            "INSERT INTO transcripts (committee, title, content, date, category) VALUES (?, ?, ?, ?, ?)", 
            (committee, title, content, date, category)
        )
        self.conn.commit()

    def add_journalist(self, first_name: str, last_name: str, organization: Optional[str], bio: Optional[str], articles: Optional[str]) -> None:
        """
        Add a new journalist to the database.
        
        Args:
            first_name: Journalist's first name
            last_name: Journalist's last name
            organization: News organization (optional)
            bio: Journalist biography (optional)
            articles: List of articles as JSON string (optional)
        """
        self.cursor.execute(
            "INSERT INTO journalists (first_name, last_name, organization, bio, articles) VALUES (?, ?, ?, ?, ?)", 
            (first_name, last_name, organization, bio, articles)
        )
        self.conn.commit()

    def add_article(self, committee_id: int, youtube_id: str, journalist_id: int, content: str, transcript_id: int, date: str, category: Optional[str]) -> None: 
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
        self.cursor.execute(
            "INSERT INTO articles (committee_id, youtube_id, journalist_id, content, transcript_id, date, category) VALUES (?, ?, ?, ?, ?, ?, ?)", 
            (committee_id, youtube_id, journalist_id, content, transcript_id, date, category)
        )
        self.conn.commit()

    def add_committee(self, name: str, description: Optional[str], created_date: Optional[str]) -> None:
        """
        Add a new committee to the database.
        
        Args:
            name: Name of the committee
            description: Description of the committee (optional)
            created_date: Date when committee was established (optional)
        """
        self.cursor.execute(
            "INSERT INTO committees (name, description, created_date) VALUES (?, ?, ?)", 
            (name, description, created_date)
        )
        self.conn.commit()

    def get_transcripts(self) -> List[Tuple[Union[int, str]]]:
        """
        Retrieve all transcripts from the database.
        
        Returns:
            List of tuples containing transcript data.
            Each tuple contains: (id, committee, title, content, date, category)
        """
        self.cursor.execute("SELECT * FROM transcripts")
        return self.cursor.fetchall()
    
    def close(self) -> None:
        """
        Close the database connection.
        
        Call this method when you're done using the database to free up resources.
        """
        self.conn.close()
    
    def reconnect(self) -> None:
        """
        Reopen the database connection after it has been closed.
        
        This method creates a new connection to the same database file.
        Useful when you need to close and reopen the connection.
        """
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()