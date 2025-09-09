import logging
from typing import Dict, Any, List
from enum import Enum
from app.data_classes import Committee, Tone, ArticleType, Journalist
from app.database import Database

logger = logging.getLogger(__name__)


class DatabaseSync:
    """
    Synchronizes enum values with database tables. Ensures all current Enum
    values exist in their corresponding database tables.
    """

    def __init__(self, database: Database):
        self.database = database
        self.enum_table_mapping = {
            Committee: "committees",
            Tone: "tones",
            ArticleType: "article_types",
            Journalist: "journalists",
        }

    def sync_all_enums(self):
        """
        Synchronize all enum classes with their database tables.
        """
        logger.info("Starting database enum synchronization...")

        for enum_class, table_name in self.enum_table_mapping.items():
            try:
                logger.info(f"Synchonization query made")
                self._sync_enum_to_table(enum_class, table_name)
            except Exception as e:
                logger.error(f"Failed to sync {enum_class.__name__}: {str(e)}")

    def _sync_enum_to_table(self, enum_class: Enum, table_name: str):
        """
        Sync a specific enum class to its database table.

        Args:
            enum_class: The enum class to sync
            table_name: The database table name
        """
        # Get existing values from database
        existing_values = self._get_existing_values(table_name)

        # Get enum values
        enum_values = {item.value for item in enum_class}

        # Find missing values
        missing_values = enum_values - existing_values

        # Insert missing values
        if missing_values:
            success = self._insert_missing_values(table_name, missing_values)
            if success:
                logger.info(
                    f"Inserted {len(missing_values)} missing value(s) called {missing_values} missing values into {table_name}"
                )
        else:
            logger.info(f"No missing values found for {table_name}")

    def _get_existing_values(self, table_name: str) -> set:
        try:
            query = f"SELECT name FROM {table_name}"
            self.database.cursor.execute(query)
            results = self.database.cursor.fetchall()
            return {row[0] for row in results}
        except Exception as e:
            logger.error(f"Error getting existing values from {table_name}: {str(e)}")
            return set()

    def _insert_missing_values(self, table_name: str, values: set) -> bool:
        """
        Insert missing values into a database table.

        Args:
            table_name: The table to insert into
            values: Set of values to insert

        Returns:
            bool: True if successful, False if failed
        """
        try:
            from datetime import datetime

            for value in values:
                query = f"INSERT INTO {table_name} (name, description, created_date) VALUES (?, ?, ?)"
                logger.info(f"Inserting value: {value} into {table_name}")
                self.database.cursor.execute(
                    query, (value, None, datetime.now().isoformat())
                )
            self.database.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting values into {table_name}: {str(e)}")
            self.database.conn.rollback()
            return False
