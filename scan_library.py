import os
import sys
import sqlite3
import argparse
from analyzer import analyze_song, save_to_db, init_db

SUPPORTED_EXTENSIONS = ('.flac', '.mp3', '.wav', '.ogg', '.m4a')

def scan_directory(directory_path, limit=1000):
    if not os.path.isdir(directory_path):
        print(f"✘ Error: Directory not found: {directory_path}", file=sys.stderr)
        return
        
    print(f"📁 Scanning directory: {directory_path} (limit: {limit} songs)")
    init_db()
    
    # Get list of audio files
    audio_files = []
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith(SUPPORTED_EXTENSIONS):
                audio_files.append(os.path.join(root, file))
                
    total_found = len(audio_files)
    print(f"🎵 Found {total_found} audio files.")
    
    # Process files
    processed_count = 0
    success_count = 0
    
    # Connect to check what's already analyzed
    conn = sqlite3.connect("music_library.db")
    cursor = conn.cursor()
    cursor.execute("SELECT filepath FROM songs")
    already_analyzed = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    print(f"📊 {len(already_analyzed)} songs already in the database.")
    
    for filepath in audio_files:
        if processed_count >= limit:
            break
            
        abs_path = os.path.abspath(filepath)
        if abs_path in already_analyzed:
            print(f"⏭ Skipping already analyzed song: {os.path.basename(filepath)}")
            continue
            
        processed_count += 1
        print(f"\n[Song {processed_count}/{limit}] Processing: {os.path.basename(filepath)}")
        
        try:
            analysis = analyze_song(abs_path)
            if analysis:
                save_to_db(abs_path, analysis)
                print(f"✔ Successfully saved to DB: {os.path.basename(filepath)}")
                success_count += 1
            else:
                print(f"✘ Failed to analyze: {os.path.basename(filepath)}")
        except Exception as e:
            print(f"✘ Error processing {filepath}: {e}", file=sys.stderr)
            
    print(f"\n✨ Scan finished! Analyzed: {processed_count}, Succeeded: {success_count}.")

def main():
    parser = argparse.ArgumentParser(description="Scan a directory of audio files and extract features to SQLite.")
    parser.add_argument("directory", help="Directory containing audio files.")
    parser.add_argument("--limit", type=int, default=1000, help="Max number of files to process.")
    args = parser.parse_args()
    
    scan_directory(args.directory, limit=args.limit)

if __name__ == "__main__":
    main()
