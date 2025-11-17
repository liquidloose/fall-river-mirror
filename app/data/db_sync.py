import logging
from enum import Enum
from .data_classes import ArticleType, Tone
from .database import Database
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseSync:
    """
    Synchronizes Python Enum class values with their corresponding database tables.

    This class ensures that all enum values defined in code are present in the database
    by comparing enum values against database records and inserting any missing entries.
    This is useful for maintaining consistency between application code and database state,
    especially after adding new enum values.

    Architecture:
    -------------
    The sync process follows these steps:
    1. Map each Enum class to its corresponding database table
    2. Query the database to get existing values
    3. Compare existing values with enum values
    4. Insert any missing values into the database

    Database Table Structure:
    -------------------------
    Each synced table must have at minimum:
    - name (TEXT): The enum value string
    - created_date (TEXT): ISO format timestamp of when the record was inserted

    Usage Example:
    --------------
    >>> db = Database("path/to/db.db")
    >>> sync = DatabaseSync(db)
    >>> sync.sync_all_enums()  # Syncs all configured enums

    Attributes:
    -----------
    database : Database
        The database instance to sync with
    enum_table_mapping : dict
        Maps Enum classes to their corresponding database table names
    """

    def __init__(self, database: Database):
        """
        Initialize DatabaseSync with a database connection.

        Args:
            database (Database): An active Database instance with an open connection
        """
        self.database = database

        # Maps each Enum class to its corresponding database table name
        # Add new mappings here when creating new enum types
        self.enum_table_mapping = {
            Tone: "tones",  # Article tone options (e.g., formal, casual)
            ArticleType: "categories",  # Article ArticleType types (e.g., news, opinion)
        }

    def sync_all_enums(self):
        """
        Synchronize all configured enum classes with their database tables.

        Iterates through the enum_table_mapping dictionary and syncs each enum
        class with its corresponding table. Errors in syncing one enum do not
        prevent other enums from being synced.

        This method should be called during application startup to ensure
        database consistency with the current codebase.

        Raises:
            Logs errors but does not raise exceptions to prevent application
            startup failure due to sync issues.
        """
        logger.info("Starting database enum synchronization...")

        # Iterate through all configured enum-to-table mappings
        for enum_class, table_name in self.enum_table_mapping.items():
            try:
                logger.info(f"Synchronization query made for {enum_class.__name__}")
                self._sync_enum_to_table(enum_class, table_name)
            except Exception as e:
                # Log the error but continue syncing other enums
                logger.error(f"Failed to sync {enum_class.__name__}: {str(e)}")

    def _sync_enum_to_table(self, enum_class: Enum, table_name: str):
        """
        Sync a specific enum class to its database table.

        This is the core sync logic that:
        1. Retrieves all existing values from the database table
        2. Extracts all values from the enum class
        3. Calculates the difference (missing values)
        4. Inserts any missing values into the database

        Args:
            enum_class (Enum): The enum class to sync (e.g., Committee, Tone)
            table_name (str): The database table name (e.g., "committees", "tones")

        Example:
            If Committee enum has ["City Council", "Planning Board"] but the
            database only has ["City Council"], this will insert "Planning Board"
        """
        # Step 1: Get existing values from database (returns a set of strings)
        existing_values = self._get_existing_values(table_name)

        # Step 2: Get all enum values (extracts .value from each enum member)
        # For Committee enum, this creates a set like {"City Council", "Planning Board", ...}
        enum_values = {item.value for item in enum_class}

        # Step 3: Find values that exist in the enum but not in the database
        # Uses set difference operation to find missing values
        missing_values = enum_values - existing_values

        # Step 4: Insert missing values if any are found
        if missing_values:
            success = self._insert_missing_values(table_name, missing_values)
            if success:
                logger.info(
                    f"Inserted {len(missing_values)} missing value(s) into {table_name}: {missing_values}"
                )
        else:
            logger.info(
                f"No missing values found for {table_name} - database is in sync"
            )

    def _get_existing_values(self, table_name: str) -> set:
        """
        Retrieve all existing values from the 'name' column of a database table.

        Queries the specified table and extracts all values from the 'name' column,
        returning them as a set for efficient comparison with enum values.

        Args:
            table_name (str): The name of the database table to query

        Returns:
            set: A set of strings representing all 'name' values in the table.
                 Returns empty set if an error occurs.

        Example:
            If the committees table has rows with name values:
            ["City Council", "Planning Board"]
            This returns: {"City Council", "Planning Board"}
        """
        try:
            # Query to select all name values from the table
            query = f"SELECT name FROM {table_name}"
            self.database.cursor.execute(query)
            results = self.database.cursor.fetchall()

            # Extract the first column (name) from each row and create a set
            # Each row is a tuple like ("City Council",), so row[0] gets the string
            return {row[0] for row in results}
        except Exception as e:
            logger.error(f"Error getting existing values from {table_name}: {str(e)}")
            # Return empty set on error so sync can continue (will treat all values as missing)
            return set()

    def _insert_missing_values(self, table_name: str, values: set) -> bool:
        """
        Insert missing enum values into a database table with timestamps.

        Inserts each value as a new row with the current timestamp. Uses parameterized
        queries to prevent SQL injection. All inserts are performed in a single
        transaction that is either fully committed or fully rolled back on error.

        Args:
            table_name (str): The database table to insert into
            values (set): Set of string values to insert

        Returns:
            bool: True if all values were successfully inserted and committed,
                  False if an error occurred (transaction is rolled back)

        Example:
            values = {"City Council", "Planning Board"}
            Inserts two rows into the committees table:
            - ("City Council", "2025-11-07T12:34:56.789")
            - ("Planning Board", "2025-11-07T12:34:56.790")

        Notes:
            - Uses parameterized queries (?) to prevent SQL injection
            - All inserts happen in one transaction for atomicity
            - If any insert fails, all inserts are rolled back
        """
        try:

            # Insert each missing value with a timestamp
            for value in values:
                # Use parameterized query to prevent SQL injection
                query = f"INSERT INTO {table_name} (name, created_date) VALUES (?, ?)"
                logger.info(f"Inserting value: {value} into {table_name}")

                # Execute with parameters (value, timestamp)
                # ISO format: "2025-11-07T17:30:45.123456"
                self.database.cursor.execute(query, (value, datetime.now().isoformat()))

            # Commit all inserts as a single transaction
            self.database.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting values into {table_name}: {str(e)}")
            # Rollback transaction on error to maintain data consistency
            self.database.conn.rollback()
            return False
