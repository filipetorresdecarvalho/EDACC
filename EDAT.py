"""
Elite Dangerous Asteroid Content Companion (EDACC)
A tool to monitor Elite Dangerous journal files and announce valuable asteroid findings using text-to-speech.
"""

import os
import json
import time
import re
import logging
import pandas as pd
from datetime import datetime
import pyttsx3
import win32file
import win32con
from pathlib import Path
import traceback
import threading

# Setup logging
def setup_logger():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"debug-{timestamp}.log"
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

logger = setup_logger()

# Default configuration
DEFAULT_CONFIG = {
    "journal_dir": os.path.expanduser("~\\Saved Games\\Frontier Developments\\Elite Dangerous"),
    "file_pattern": "Journal.*.log",
    "polling_frequency": 0.1,  # seconds (10 times per second)
    "target_materials": {
        "Platinum": 50.0,
        "Gold": 50.0,
        "Painite": 50.0
    },
    "voice_rate": 200,  # WPM for text-to-speech
    "voice_volume": 1.0  # 0.0 to 1.0
}

CONFIG_FILE = "config.json"
STATS_FILE = "mining_statistics.csv"

class EliteAsteroidTracker:
    def __init__(self):
        """Initialize the asteroid tracker with configuration and TTS engine."""
        try:
            self.load_config()
            
            # Initialize TTS engine
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', self.config['voice_rate'])
            self.engine.setProperty('volume', self.config['voice_volume'])
            
            # Initialize stats tracking
            self.stats = self.load_stats()
            
            # File tracking variables
            self.current_journal_path = None
            self.last_position = 0
            self.last_line = ""
            
            logger.info("EliteAsteroidTracker initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing tracker: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def load_config(self):
        """Load configuration from file or create with defaults if not exists."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    self.config = json.load(f)
                logger.info("Configuration loaded from file")
            else:
                self.config = DEFAULT_CONFIG
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(self.config, indent=4, sort_keys=True, f)
                logger.info("Default configuration created")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            logger.error(traceback.format_exc())
            self.config = DEFAULT_CONFIG
    
    def load_stats(self):
        """Load existing statistics or create new DataFrame."""
        try:
            if os.path.exists(STATS_FILE):
                stats = pd.read_csv(STATS_FILE)
                logger.info(f"Statistics loaded: {len(stats)} records")
                return stats
            else:
                stats = pd.DataFrame(columns=[
                    'timestamp', 'material', 'proportion', 'motherlode',
                    'content_type', 'remaining'
                ])
                logger.info("New statistics dataframe created")
                return stats
        except Exception as e:
            logger.error(f"Error loading statistics: {e}")
            logger.error(traceback.format_exc())
            return pd.DataFrame(columns=[
                'timestamp', 'material', 'proportion', 'motherlode',
                'content_type', 'remaining'
            ])
    
    def save_stats(self):
        """Save the statistics to CSV file."""
        try:
            self.stats.to_csv(STATS_FILE, index=False)
            logger.debug(f"Statistics saved: {len(self.stats)} records")
        except Exception as e:
            logger.error(f"Error saving statistics: {e}")
            logger.error(traceback.format_exc())
    
    def find_latest_journal(self):
        """Find the latest journal file in the configured directory."""
        try:
            pattern = re.compile(self.config['file_pattern'].replace('.', '\.').replace('*', '.*'))
            journal_files = []
            
            # Use pathlib for more reliable file listing
            p = Path(self.config['journal_dir'])
            for file in p.glob("Journal*.log"):
                if pattern.match(file.name):
                    journal_files.append((file, file.stat().st_mtime))
            
            if not journal_files:
                logger.warning("No journal files found")
                return None
                
            # Sort by modification time (newest first)
            journal_files.sort(key=lambda x: x[1], reverse=True)
            latest_file = str(journal_files[0][0])
            
            if self.current_journal_path != latest_file:
                logger.info(f"New journal file found: {latest_file}")
                self.current_journal_path = latest_file
                self.last_position = 0  # Reset position for new file
                self.last_line = ""
            
            return self.current_journal_path
            
        except Exception as e:
            logger.error(f"Error finding latest journal: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def read_new_journal_entries(self):
        """Read and parse new entries from the journal file."""
        if not self.current_journal_path or not os.path.exists(self.current_journal_path):
            logger.debug("No valid journal path available")
            return []
        
        try:
            # Use Win32 API for efficient file access
            handle = win32file.CreateFile(
                self.current_journal_path,
                win32con.GENERIC_READ,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                None,
                win32con.OPEN_EXISTING,
                0,
                None
            )
            
            # Get file size and check if new content exists
            file_size = win32file.GetFileSize(handle)
            if file_size <= self.last_position:
                win32file.CloseHandle(handle)
                return []
                
            # Seek to last read position
            win32file.SetFilePointer(handle, self.last_position, win32con.FILE_BEGIN)
            
            # Read new content
            error, data = win32file.ReadFile(handle, file_size - self.last_position)
            win32file.CloseHandle(handle)
            
            if error:
                logger.error(f"Error reading file: {error}")
                return []
                
            # Update last read position
            self.last_position = file_size
            
            # Process the data
            content = data.decode('utf-8', errors='ignore')
            lines = content.splitlines()
            
            # Skip empty results
            if not lines:
                return []
                
            # If we have a partial last line from before, combine with first line
            if self.last_line:
                lines[0] = self.last_line + lines[0]
                self.last_line = ""
            
            # If the last line doesn't end with a newline, it might be incomplete
            if not content.endswith('\n'):
                self.last_line = lines.pop()
            
            # Parse the journal entries (JSON format)
            entries = []
            for line in lines:
                try:
                    if line.strip():
                        entry = json.loads(line)
                        entries.append(entry)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse journal entry: {line[:100]}...")
            
            return entries
            
        except Exception as e:
            logger.error(f"Error reading journal entries: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def speak_text(self, text):
        """Announce text using text-to-speech."""
        try:
            # Print to console
            print(f"ANNOUNCEMENT: {text}")
            
            # Use a separate thread for TTS to avoid blocking
            def speak_thread():
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception as e:
                    logger.error(f"Error in TTS thread: {e}")
            
            threading.Thread(target=speak_thread).start()
            logger.info(f"TTS announcement: {text}")
            
        except Exception as e:
            logger.error(f"Error in speak_text: {e}")
            logger.error(traceback.format_exc())
    
    def process_asteroid(self, entry):
        """Process a ProspectedAsteroid event and announce if valuable."""
        try:
            if entry.get('event') != 'ProspectedAsteroid':
                return
            
            # Check if remaining is 100%
            remaining = entry.get('Remaining', 0)
            if remaining < 100.0:
                return
                
            materials = entry.get('Materials', [])
            found_valuable = False
            
            # Check for valuable materials
            for material in materials:
                material_name = material.get('Name', '')
                proportion = material.get('Proportion', 0.0)
                
                # Check if this is a target material with sufficient percentage
                if material_name in self.config['target_materials'] and proportion >= self.config['target_materials'][material_name]:
                    found_valuable = True
                    
                    # Record in statistics
                    self.record_asteroid(
                        entry.get('timestamp', datetime.now().isoformat()),
                        material_name,
                        proportion,
                        'MotherlodeMaterial' in entry and entry['MotherlodeMaterial'] == material_name,
                        entry.get('Content_Localised', 'Unknown'),
                        remaining
                    )
                    
                    # Announce the finding
                    rounded_proportion = round(proportion)
                    self.speak_text(f"{material_name} asteroid found with {rounded_proportion} percent content")
                    break
                    
            return found_valuable
            
        except Exception as e:
            logger.error(f"Error processing asteroid: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def record_asteroid(self, timestamp, material, proportion, is_motherlode, content_type, remaining):
        """Record asteroid information in statistics."""
        try:
            new_row = pd.DataFrame([{
                'timestamp': timestamp,
                'material': material,
                'proportion': proportion,
                'motherlode': is_motherlode,
                'content_type': content_type,
                'remaining': remaining
            }])
            
            self.stats = pd.concat([self.stats, new_row], ignore_index=True)
            self.save_stats()
            
        except Exception as e:
            logger.error(f"Error recording asteroid: {e}")
            logger.error(traceback.format_exc())
    
    def display_stats(self):
        """Display mining statistics."""
        try:
            if len(self.stats) == 0:
                print("No asteroid statistics recorded yet.")
                return
                
            # Group by material and calculate averages
            material_stats = self.stats.groupby('material').agg({
                'proportion': ['count', 'mean', 'max'],
                'motherlode': 'sum'
            })
            
            print("\n=== Mining Statistics ===")
            print(f"Total asteroids prospected: {len(self.stats)}")
            
            for material, stats in material_stats.iterrows():
                count = stats[('proportion', 'count')]
                avg_prop = stats[('proportion', 'mean')]
                max_prop = stats[('proportion', 'max')]
                motherlodes = stats[('motherlode', 'sum')]
                
                print(f"{material}: {count} found, avg: {avg_prop:.1f}%, max: {max_prop:.1f}%, motherlodes: {motherlodes}")
                
            print("========================\n")
            
        except Exception as e:
            logger.error(f"Error displaying stats: {e}")
            logger.error(traceback.format_exc())
    
    def update_config(self, new_config):
        """Update configuration with new values."""
        # TODO: Implement config updating from UI or command line
        pass
    
    def monitor_for_valuable_asteroids(self):
        """Main monitoring loop to check for valuable asteroids."""
        print(f"Starting Elite Dangerous Asteroid Content Companion")
        print(f"Monitoring journal files in: {self.config['journal_dir']}")
        print(f"Looking for: {', '.join(f'{m} ({p}%+)' for m, p in self.config['target_materials'].items())}")
        print("Press Ctrl+C to exit\n")
        
        try:
            while True:
                # Find latest journal file
                journal_path = self.find_latest_journal()
                if not journal_path:
                    time.sleep(1)  # Wait longer if no journal found
                    continue
                
                # Read new entries
                entries = self.read_new_journal_entries()
                
                # Process each entry
                for entry in entries:
                    print(f"Processing: {entry.get('event', 'Unknown')} - {entry.get('timestamp', 'No timestamp')}")
                    
                    # Process ProspectedAsteroid events
                    if entry.get('event') == 'ProspectedAsteroid':
                        self.process_asteroid(entry)
                
                # Periodically display stats (every 100 cycles)
                # if random.randint(0, 100) == 0:
                #    self.display_stats()
                
                # Sleep for the configured polling frequency
                time.sleep(self.config['polling_frequency'])
                
        except KeyboardInterrupt:
            print("\nExiting asteroid tracker...")
            self.save_stats()
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            logger.error(traceback.format_exc())
            print(f"Error: {e}. See debug log for details.")
            self.save_stats()

# Additional functionality for future expansion
def analyze_historical_data():
    """Analyze historical data to find optimal mining locations."""
    # TODO: Implement historical data analysis
    pass

def overlay_display():
    """Create a transparent overlay display for in-game information."""
    # TODO: Implement overlay display
    pass

def main():
    """Main function to start the asteroid tracker."""
    try:
        tracker = EliteAsteroidTracker()
        tracker.monitor_for_valuable_asteroids()
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}")
        logger.critical(traceback.format_exc())
        print(f"Fatal error: {e}. See debug log for details.")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
