#!/usr/bin/env python3
import os
import sys
import duckdb
from datetime import datetime
import time

def dump_recent_chat_logs(db_path, limit=10, retries=3):
    """
    Dump the most recent chat log entries from DuckDB
    
    Args:
        db_path: Path to the chat_logs.db file
        limit: Number of entries to show (default: 10)
        retries: Number of retries if database is locked (default: 3)
    """
    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        return False
    
    for attempt in range(retries):
        try:
            # Connect in read-only mode with explicit config
            config = {'access_mode': 'READ_ONLY'}
            try:
                # Try with access_mode first (newer DuckDB versions)
                with duckdb.connect(db_path, config=config) as conn:
                    return _perform_query(conn, db_path, limit)
            except TypeError:
                # Fall back to read_only parameter (older DuckDB versions)
                with duckdb.connect(db_path, read_only=True) as conn:
                    return _perform_query(conn, db_path, limit)
                
        except duckdb.duckdb.IOException as e:
            if "Conflicting lock is held" in str(e):
                print(f"Database is locked (attempt {attempt+1}/{retries}). Retrying in 1 second...")
                time.sleep(1)
                if attempt == retries - 1:
                    print(f"Error: Database is still locked after {retries} attempts. Full error: {e}")
                    return False
            else:
                print(f"I/O Error: {e}")
                return False
        except Exception as e:
            print(f"Error querying database: {e}")
            return False

def _perform_query(conn, db_path, limit):
    """Execute the query and display results"""
    # Query for the most recent messages
    result = conn.execute(f"""
        SELECT 
            session_id, 
            conversation_id, 
            substr(message, 1, 100) || CASE WHEN length(message) > 100 THEN '...' ELSE '' END as message_preview,
            role, 
            created_at
        FROM chat_messages
        ORDER BY created_at DESC
        LIMIT {limit}
    """).fetchall()
    
    if not result:
        print("No chat messages found in the database.")
        return True
    
    # Print header
    print("\n{:-^80}".format(" Recent Chat Messages "))
    print("{:<10} | {:<10} | {:<15} | {:<40} | {:<20}".format(
        "Session", "Conv. ID", "Role", "Message Preview", "Timestamp"
    ))
    print("-" * 80)
    
    # Print messages (newest first)
    for row in result:
        session_id = row[0][:8] + "..." if len(row[0]) > 10 else row[0]
        conv_id = row[1][:8] + "..." if len(row[1]) > 10 else row[1]
        message = row[2].replace("\n", " ")
        role = row[3]
        timestamp = row[4]
        
        print("{:<10} | {:<10} | {:<15} | {:<40} | {:<20}".format(
            session_id, conv_id, role, message, timestamp
        ))
    
    print("-" * 80)
    print(f"Showing {len(result)} most recent messages from {db_path}")
    return True

if __name__ == "__main__":
    # Default path (can be overridden by command line argument)
    default_db_path = "./chat_logs.db"
    
    # Get path from command line if provided
    db_path = sys.argv[1] if len(sys.argv) > 1 else default_db_path
    
    # Get limit from command line if provided
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    dump_recent_chat_logs(db_path, limit)