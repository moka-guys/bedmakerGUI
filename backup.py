import os
import shutil
from datetime import datetime
import sqlite3

def backup_database():
    """Create a backup of the SQLite database"""
    backup_dir = 'backups'
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'app_db_backup_{timestamp}.db')
    
    # Connect to the database
    conn = sqlite3.connect('app.db')
    
    # Create a backup
    backup = sqlite3.connect(backup_path)
    conn.backup(backup)
    
    # Close connections
    backup.close()
    conn.close()
    
    # Compress backup
    shutil.make_archive(backup_path, 'gzip', backup_dir, f'app_db_backup_{timestamp}.db')
    os.remove(backup_path)
    
    # Keep only last 5 backups
    backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.gz')])
    if len(backups) > 5:
        for old_backup in backups[:-5]:
            os.remove(os.path.join(backup_dir, old_backup))

if __name__ == '__main__':
    backup_database()