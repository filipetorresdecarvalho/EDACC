# Elite Dangerous Asteroid Content Companion (EDACC)

EDACC is a tool for Elite Dangerous miners that monitors your game journal files and announces valuable asteroid findings using text-to-speech. It helps you focus on piloting your ship while not missing any high-value asteroids.

## Features

- **Real-time monitoring** of Elite Dangerous journal files
- **Voice announcements** for valuable asteroids (Platinum, Gold, Painite over 50%)
- **Statistics tracking** of mining sessions
- **Performance optimized** using Win32 API for efficient file access
- **Configurable** through JSON config file

## Installation

1. Make sure you have Python 3.8+ installed on your system
2. Clone this repository:
```bash
git clone https://github.com/filipetorresdecarvalho/EDACC.git
cd EDACC
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

## Usage

1. Start Elite Dangerous
2. Launch the asteroid tracker:
```bash
python elite_asteroid_tracker.py
```

3. Start mining! The application will monitor your journal files and announce when you find valuable asteroids.

## Configuration

The application uses a `config.json` file that will be created on first run. You can modify it to change:

- Target materials and minimum percentages
- Journal file directory
- Polling frequency
- Text-to-speech settings

Example configuration:
```json
{
    "journal_dir": "C:\\Users\\YourName\\Saved Games\\Frontier Developments\\Elite Dangerous",
    "file_pattern": "Journal.*.log",
    "polling_frequency": 0.1,
    "target_materials": {
        "Platinum": 50.0,
        "Gold": 50.0,
        "Painite": 50.0
    },
    "voice_rate": 200,
    "voice_volume": 1.0
}
```

## Statistics

The application tracks statistics about asteroid prospecting in a CSV file. You can analyze this data later to optimize your mining strategy.

## Troubleshooting

If you encounter issues, check the debug log file (debug-YYYYMMDD_HHMMSS.log) created in the application directory.

## License

MIT License

## Acknowledgements

- Frontier Developments for creating Elite Dangerous
- The Elite Dangerous mining community
