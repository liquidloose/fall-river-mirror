import sqlite3

class Database:
    def __init__(self, db_name):
        """Initialize database. Creates database and tables if they don't exist."""
        self.db_path = db_name + ".db"
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._create_all_tables()   

    def _create_table(self, table_name, columns):
        self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")
        self.conn.commit()

    def _create_all_tables(self):
        """Create all required tables for the application"""
        self.create_table("transcripts", "id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT, date TEXT, category TEXT")
        self.create_table("journalists", "id INTEGER PRIMARY KEY AUTOINCREMENT, first_name TEXT, last_name TEXT, organization TEXT, bio TEXT, articles TEXT")
        self.create_table("articles", 
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "journalist_id INTEGER, "
            "content TEXT, "
            "transcript_id INTEGER, "
            "date TEXT, "
            "category TEXT, "
            "FOREIGN KEY(journalist_id) REFERENCES journalists(id), "
            "FOREIGN KEY(transcript_id) REFERENCES transcripts(id)")

    
    
    