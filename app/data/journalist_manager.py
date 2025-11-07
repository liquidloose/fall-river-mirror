import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from .database import Database

logger = logging.getLogger(__name__)


class JournalistManager:
    """
    Manages journalist entities in the database.
    Handles CRUD operations for journalists as proper entities, not enums.
    """

    def __init__(self, database: Database):
        self.database = database

    def create_journalist(
        self,
        full_name: str,
        first_name: str,
        last_name: str,
        bio: Optional[str] = None,
        description: Optional[str] = None,
        articles: Optional[str] = None,
    ) -> bool:
        """
        Create a new journalist in the database.

        Args:
            full_name: Full name of the journalist
            first_name: First name
            last_name: Last name
            bio: Biographical information
            description: Professional description
            articles: Articles (could be JSON string)

        Returns:
            bool: True if successful, False if failed
        """
        try:
            query = """
                INSERT INTO journalists 
                (full_name, first_name, last_name, bio, articles, description, created_date) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            self.database.cursor.execute(
                query,
                (
                    full_name,
                    first_name,
                    last_name,
                    bio,
                    articles,
                    description,
                    datetime.now().isoformat(),
                ),
            )
            self.database.conn.commit()
            logger.info(f"Successfully created journalist: {full_name}")
            return True
        except Exception as e:
            logger.error(f"Error creating journalist {full_name}: {str(e)}")
            self.database.conn.rollback()
            return False

    def get_journalist(self, full_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a journalist by full name.

        Args:
            full_name: Full name of the journalist

        Returns:
            Dict with journalist data or None if not found
        """
        try:
            query = """
                SELECT id, full_name, first_name, last_name, bio, articles, description, created_date 
                FROM journalists 
                WHERE full_name = ?
            """
            self.database.cursor.execute(query, (full_name,))
            result = self.database.cursor.fetchone()

            if result:
                return {
                    "id": result[0],
                    "full_name": result[1],
                    "first_name": result[2],
                    "last_name": result[3],
                    "bio": result[4],
                    "articles": result[5],
                    "description": result[6],
                    "created_date": result[7],
                }
            return None
        except Exception as e:
            logger.error(f"Error retrieving journalist {full_name}: {str(e)}")
            return None

    def journalist_exists(self, full_name: str) -> bool:
        """
        Check if a journalist exists in the database.

        Args:
            full_name: Full name of the journalist

        Returns:
            bool: True if journalist exists, False otherwise
        """
        return self.get_journalist(full_name) is not None

    def update_journalist(
        self,
        full_name: str,
        bio: Optional[str] = None,
        description: Optional[str] = None,
        articles: Optional[str] = None,
    ) -> bool:
        """
        Update journalist information.

        Args:
            full_name: Full name of the journalist to update
            bio: New biographical information
            description: New professional description
            articles: New articles data

        Returns:
            bool: True if successful, False if failed
        """
        try:
            # Build dynamic update query based on provided parameters
            updates = []
            params = []

            if bio is not None:
                updates.append("bio = ?")
                params.append(bio)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if articles is not None:
                updates.append("articles = ?")
                params.append(articles)

            if not updates:
                logger.warning(f"No updates provided for journalist {full_name}")
                return False

            params.append(full_name)  # For WHERE clause
            query = f"UPDATE journalists SET {', '.join(updates)} WHERE full_name = ?"

            self.database.cursor.execute(query, params)
            self.database.conn.commit()

            if self.database.cursor.rowcount > 0:
                logger.info(f"Successfully updated journalist: {full_name}")
                return True
            else:
                logger.warning(f"No journalist found with name: {full_name}")
                return False

        except Exception as e:
            logger.error(f"Error updating journalist {full_name}: {str(e)}")
            self.database.conn.rollback()
            return False

    def upsert_journalist(
        self,
        full_name: str,
        first_name: str,
        last_name: str,
        bio: Optional[str] = None,
        description: Optional[str] = None,
        articles: Optional[str] = None,
    ) -> bool:
        """
        Insert or update a journalist (upsert operation).

        Args:
            full_name: Full name of the journalist
            first_name: First name
            last_name: Last name
            bio: Biographical information
            description: Professional description
            articles: Articles data

        Returns:
            bool: True if successful, False if failed
        """
        if self.journalist_exists(full_name):
            return self.update_journalist(full_name, bio, description, articles)
        else:
            return self.create_journalist(
                full_name, first_name, last_name, bio, description, articles
            )

    def get_all_journalists(self) -> List[Dict[str, Any]]:
        """
        Retrieve all journalists from the database.

        Returns:
            List of dictionaries containing journalist data
        """
        try:
            query = """
                SELECT id, full_name, first_name, last_name, bio, articles, description, created_date 
                FROM journalists 
                ORDER BY full_name
            """
            self.database.cursor.execute(query)
            results = self.database.cursor.fetchall()

            journalists = []
            for result in results:
                journalists.append({
                    "id": result[0],
                    "full_name": result[1],
                    "first_name": result[2],
                    "last_name": result[3],
                    "bio": result[4],
                    "articles": result[5],
                    "description": result[6],
                    "created_date": result[7],
                })

            return journalists
        except Exception as e:
            logger.error(f"Error retrieving all journalists: {str(e)}")
            return []

    def delete_journalist(self, full_name: str) -> bool:
        """
        Delete a journalist from the database.

        Args:
            full_name: Full name of the journalist to delete

        Returns:
            bool: True if successful, False if failed
        """
        try:
            query = "DELETE FROM journalists WHERE full_name = ?"
            self.database.cursor.execute(query, (full_name,))
            self.database.conn.commit()

            if self.database.cursor.rowcount > 0:
                logger.info(f"Successfully deleted journalist: {full_name}")
                return True
            else:
                logger.warning(f"No journalist found with name: {full_name}")
                return False

        except Exception as e:
            logger.error(f"Error deleting journalist {full_name}: {str(e)}")
            self.database.conn.rollback()
            return False
