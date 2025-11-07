#!/usr/bin/env python3
"""
Manual test script that actually writes to your real database.
⚠️  WARNING: This will write real data to your production database!
"""

import sys
import os

sys.path.append("/code")

from app.data.transcript_manager import TranscriptManager
from app.data.database import Database
from app.data.data_classes import AIAgent, Committee


def manual_database_test():
    """
    Test that actually writes to your real fr-mirror.db database.
    ⚠️  WARNING: This modifies your production database!
    """

    print("⚠️  WARNING: This test will write to your REAL database!")
    print("📁 Database: fr-mirror.db")

    response = input("Are you sure you want to continue? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Test cancelled")
        return

    print("\n🚀 Starting REAL database test...")

    # Use your actual production database
    print("📊 Connecting to production database...")
    database = Database("fr-mirror")  # This connects to fr-mirror.db

    # Create TranscriptManager
    print("🎬 Creating TranscriptManager...")
    transcript_manager = TranscriptManager(
        committee="Test Committee", database=database
    )

    # Real test data that will be written to your database
    test_video_id = "MANUAL_TEST_123"
    test_transcript = """
    [MANUAL TEST DATA - SAFE TO DELETE]
    This is test transcript data created by the manual database test.
    Speaker 1: This is a test of the transcript manager.
    Speaker 2: The data should appear in your fr-mirror.db database.
    Speaker 1: You can safely delete this record after testing.
    [END TEST DATA]
    """
    test_committee = Committee.CITY_COUNCIL.value
    test_category = AIAgent.GROK

    print(f"📝 Test data:")
    print(f"   Video ID: {test_video_id}")
    print(f"   Committee: {test_committee}")
    print(f"   Category: {test_category}")
    print(f"   Transcript length: {len(test_transcript)} characters")

    try:
        # Test _cache_transcript - this will write to your real database
        print("\n🔄 Writing to REAL database...")
        transcript_manager._cache_transcript(
            video_id=test_video_id, transcript=test_transcript, committee=test_committee
        )

        print("✅ Data written to fr-mirror.db successfully!")

        # Verify the data was written
        print("\n🔍 Verifying data in real database...")
        cursor = database.cursor
        cursor.execute(
            "SELECT id, committee, title, content, category FROM transcripts WHERE title = ?",
            (test_video_id,),
        )
        result = cursor.fetchone()

        if result:
            transcript_id, committee, title, content, category = result
            print("✅ Data found in production database!")
            print(f"   Database ID: {transcript_id}")
            print(f"   Committee: {committee}")
            print(f"   Title: {title}")
            print(f"   Category: {category}")
            print(f"   Content preview: {content[:100]}...")

            # Ask if user wants to clean up
            cleanup = input("\n🧹 Delete this test data? (yes/no): ")
            if cleanup.lower() == "yes":
                cursor.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
                database.conn.commit()
                print("✅ Test data deleted from database")
            else:
                print("ℹ️  Test data left in database (you can delete it manually)")

        else:
            print("❌ Data not found in database!")

    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        import traceback

        traceback.print_exc()

    finally:
        # Close database connection
        if database.is_connected:
            database.close()
            print("\n🔒 Database connection closed")


if __name__ == "__main__":
    manual_database_test()
