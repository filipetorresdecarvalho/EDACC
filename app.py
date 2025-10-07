#!/usr/bin/env python3
import os
import sys
import json
import time
import threading
import glob
import re
import logging
from datetime import datetime
import pickle

try:
    import pandas as pd
except ImportError:
    print("pandas is required. Install with: pip install pandas")
    sys.exit(1)

try:
    import pyttsx3
except ImportError:
    print("pyttsx3 is required. Install with: pip install pyttsx3")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

# Configuration
CONFIG_PATH = "config.json"
MINING_CONFIG_PATH = "mining.json"

def load_config(path, defaults=None):
    """Load config file or return defaults"""
    if defaults is None:
        defaults = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        # If config doesn't exist, create it with defaults
        if path == CONFIG_PATH:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(defaults, f, indent=2)
                logging.info(f"Created new config file: {path}")
            except Exception as ex:
                logging.error(f"Failed to create config: {ex}")
        return defaults
    except Exception as ex:
        logging.error(f"Failed to load {path}: {ex}")
        return defaults

class SimpleTextToSpeech:
    """Ultra-reliable TTS that creates a new engine for each request"""
    
    def __init__(self):
        self._queue = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._stop = threading.Event()
        self._thread.start()
        logging.info("TTS system initialized")
    
    def speak(self, text):
        """Queue text for speaking"""
        with self._lock:
            self._queue.append(text)
            logging.info(f"TTS queued: {text}")
    
    def _worker(self):
        """Process speech queue"""
        while not self._stop.is_set():
            text = None
            with self._lock:
                if self._queue:
                    text = self._queue.pop(0)
            
            if text:
                logging.info(f"TTS speaking: {text}")
                try:
                    # Create fresh engine each time (more reliable)
                    engine = pyttsx3.init()
                    engine.setProperty("rate", 150)  # Slightly slower
                    engine.setProperty("volume", 1.0)
                    engine.say(text)
                    engine.runAndWait()
                    del engine  # Clean up
                except Exception as ex:
                    logging.error(f"TTS error: {ex}")
            else:
                time.sleep(0.1)
    
    def stop(self):
        """Stop the TTS worker"""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

class MiningData:
    """Stores and manages mining data"""
    
    def __init__(self):
        self.df = pd.DataFrame(columns=["timestamp", "material", "proportion"])
        self.last_save = time.time()
    
    def add_material(self, timestamp, material, proportion):
        """Add a material entry"""
        new_row = pd.DataFrame([{
            "timestamp": timestamp,
            "material": material,
            "proportion": proportion
        }])
        self.df = pd.concat([self.df, new_row], ignore_index=True)
    
    def save(self, path="mining_data.csv"):
        """Save data to CSV"""
        try:
            self.df.to_csv(path, index=False)
            logging.info(f"Saved mining data: {len(self.df)} records")
        except Exception as ex:
            logging.error(f"Failed to save mining data: {ex}")

class EliteAssistant:
    """Main application class"""
    
    def __init__(self):
        # Default configuration with CORRECT path for Filipe
        default_config = {
            "journal_dir": r"C:\Users\Filipe\Saved Games\Frontier Developments\Elite Dangerous",
            "poll_interval": 0.1,
            "mining_config": MINING_CONFIG_PATH
        }
        
        # Load configuration
        self.config = load_config(CONFIG_PATH, default_config)
        self.mining_thresholds = load_config(self.config.get("mining_config", MINING_CONFIG_PATH), {
            "Platinum": 30
        })
        
        self.journal_dir = self.config.get("journal_dir")
        self.poll_interval = float(self.config.get("poll_interval", 0.1))
        
        # Initialize components
        self.tts = SimpleTextToSpeech()
        self.mining_data = MiningData()
        self.current_file = None
        self.last_position = 0
        self.last_line = None
        self.stop_flag = threading.Event()
        
        # Print startup information
        logging.info(f"Journal directory: {self.journal_dir}")
        logging.info(f"Mining thresholds: {self.mining_thresholds}")
    
    def find_latest_journal(self):
        """Find the most recent journal file"""
        try:
            if not os.path.exists(self.journal_dir):
                logging.error(f"Journal directory does not exist: {self.journal_dir}")
                return None
                
            files = [f for f in os.listdir(self.journal_dir) 
                    if f.startswith("Journal.") and f.endswith(".log")]
            if not files:
                logging.warning(f"No journal files found in {self.journal_dir}")
                return None
                
            files.sort(key=lambda f: os.path.getmtime(os.path.join(self.journal_dir, f)), 
                      reverse=True)
            latest_file = os.path.join(self.journal_dir, files[0])
            return latest_file
        except Exception as ex:
            logging.error(f"Error finding journal files: {ex}")
            return None
    
    def read_new_lines(self):
        """Read new lines from the current journal file"""
        latest = self.find_latest_journal()
        if not latest:
            return []
            
        # Check if journal file has changed
        if latest != self.current_file:
            logging.info(f"Switching to journal: {latest}")
            self.current_file = latest
            # Start at end of file for new journals
            try:
                self.last_position = os.path.getsize(latest)
            except:
                self.last_position = 0
        
        try:
            with open(self.current_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self.last_position)
                lines = f.readlines()
                self.last_position = f.tell()
                
                # Filter duplicates and empty lines
                result = []
                for line in lines:
                    line = line.strip()
                    if not line or line == self.last_line:
                        continue
                    self.last_line = line
                    result.append(line)
                
                return result
        except Exception as ex:
            logging.error(f"Error reading journal: {ex}")
            return []
    
    def handle_mining(self, line):
        """Process mining events"""
        if '"event":"ProspectedAsteroid"' not in line:
            return False
        
        try:
            # Try to parse as JSON
            data = json.loads(line)
            if data.get("event") != "ProspectedAsteroid":
                return False
                
            # Get materials array
            materials = data.get("Materials", [])
            timestamp = data.get("timestamp", datetime.now().isoformat())
            
            if not materials:
                return False
            
            # Print nice header for this asteroid
            print("\n" + "-" * 40)
            print(f"New prospected Asteroid")
            print(f"{timestamp}")
            print("-" * 40)
            
            # Process materials
            for mat in materials:
                name = mat.get("Name", "")
                proportion = mat.get("Proportion", 0)
                if not name:
                    continue
                
                # Convert to percentage
                #percent = int(float(proportion) * 100) if isinstance(proportion, float) else int(proportion)
                percent = int(float(proportion) ) if isinstance(proportion, float) else int(proportion)
                
                # Log to terminal
                logging.info(f"[MINING] {name}: {percent}%")
                
                # Check threshold for TTS
                threshold = self.mining_thresholds.get(name)
                if threshold is not None and percent >= threshold:
                    message = f"{name} found at {percent} percent"
                    logging.info(f"[ALERT] {message}")
                    self.tts.speak(message)
                
                # Store in dataset
                self.mining_data.add_material(timestamp, name, percent)
            
            return True
        except json.JSONDecodeError:
            # Try regex as fallback
            materials_match = re.search(r'"Materials"\s*:\s*(\[.*?\])', line)
            timestamp_match = re.search(r'"timestamp"\s*:\s*"([^"]+)"', line)
            
            if not materials_match:
                return False
                
            try:
                materials = json.loads(materials_match.group(1))
                timestamp = timestamp_match.group(1) if timestamp_match else datetime.now().isoformat()
                
                # Print header
                print("\n" + "-" * 40)
                print(f"New prospected Asteroid (regex parsed)")
                print(f"{timestamp}")
                print("-" * 40)
                
                # Process materials with regex
                for mat in materials:
                    name = mat.get("Name", "")
                    proportion = mat.get("Proportion", 0)
                    if not name:
                        continue
                    
                    # Convert to percentage
                    #percent = int(float(proportion) * 100) if isinstance(proportion, float) else int(proportion)
                    percent = int(float(proportion)) if isinstance(proportion, float) else int(proportion)
                    
                    # Log to terminal
                    logging.info(f"[MINING] {name}: {percent}%")
                    
                    # Check threshold for TTS
                    threshold = self.mining_thresholds.get(name)
                    if threshold is not None and percent >= threshold:
                        message = f"{name} found at {percent} percent"
                        logging.info(f"[ALERT] {message}")
                        self.tts.speak(message)
                    
                    # Store in dataset
                    self.mining_data.add_material(timestamp, name, percent)
                
                return True
            except Exception as ex:
                logging.error(f"Failed to parse mining data with regex: {ex}")
                return False
        except Exception as ex:
            logging.error(f"Error in mining handler: {ex}")
            return False
    
    def handle_message(self, line):
        """Process message events"""
        if '"event":"ReceiveText"' not in line:
            return False
        
        try:
            data = json.loads(line)
            if data.get("event") != "ReceiveText":
                return False
                
            sender = data.get("From", "Unknown")
            message = data.get("Message", "")
            channel = data.get("Channel", "").lower()
            
            if channel == "squadron":
                msg = f"message from squadron member {sender} saying: {message}"
                logging.info(msg)
                self.tts.speak(msg)
                return True
            
            elif channel == "npc":
                msg_lower = message.lower()
                pirate_words = ["cargo", "surrender", "let me see", "hand over", "pirate"]
                
                if any(word in msg_lower for word in pirate_words):
                    msg = f"NPC PIRATE MESSAGE: {message}"
                else:
                    msg = f"NPC message: {message}"
                    
                logging.info(msg)
                self.tts.speak(msg)
                return True
                
            elif channel == "player":
                msg = f"player message from {sender} saying: {message}"
                logging.info(msg)
                self.tts.speak(msg)
                return True
                
        except json.JSONDecodeError:
            # Try regex fallback for messages
            from_match = re.search(r'"From"\s*:\s*"([^"]+)"', line)
            message_match = re.search(r'"Message"\s*:\s*"([^"]+)"', line)
            channel_match = re.search(r'"Channel"\s*:\s*"([^"]+)"', line)
            
            if from_match and message_match and channel_match:
                sender = from_match.group(1)
                message = message_match.group(1)
                channel = channel_match.group(1).lower()
                
                if channel == "squadron":
                    msg = f"message from squadron member {sender} saying: {message}"
                    logging.info(msg)
                    self.tts.speak(msg)
                    return True
                
                # Handle other channels similarly...
        except Exception as ex:
            logging.error(f"Error in message handler: {ex}")
            
        return False
    
    def run(self):
        """Main application loop"""
        logging.info("Elite Dangerous Assistant starting...")
        self.tts.speak("Elite Dangerous Assistant ready")
        
        try:
            while not self.stop_flag.is_set():
                lines = self.read_new_lines()
                
                if not lines:
                    time.sleep(self.poll_interval)
                    continue
                
                for line in lines:
                    try:
                        # Try each handler
                        handled = (
                            self.handle_mining(line) or
                            self.handle_message(line)
                        )
                        
                        # Add additional debugging if needed
                        if not handled and '"event"' in line:
                            try:
                                data = json.loads(line)
                                event = data.get("event")
                                if event not in ("Music", "Status", "NavRoute"):  # Skip noisy events
                                    logging.debug(f"Unhandled event: {event}")
                            except:
                                pass
                    except Exception as ex:
                        logging.error(f"Error processing line: {ex}")
                
                # Periodic save
                now = time.time()
                if now - self.mining_data.last_save > 600:  # 10 minutes
                    self.mining_data.save()
                    self.mining_data.last_save = now
                    
        except KeyboardInterrupt:
            logging.info("Interrupted by user")
        finally:
            self.stop_flag.set()
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown"""
        logging.info("Shutting down...")
        self.mining_data.save()
        self.tts.stop()
        logging.info("Goodbye!")

# Start the application
if __name__ == "__main__":
    app = EliteAssistant()
    app.run()