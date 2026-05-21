# PIEC - Furnace Control & Monitoring System

Python script and front-end for listening on RS communication in furnace control system.

## Project Overview

This is a modified version of [econetanalyze](https://github.com/twkrol/econetanalyze), adapted for monitoring and controlling furnace systems through RS communication protocols.

## Features

- Real-time furnace monitoring
- Web-based control interface
- Python backend for RS communication handling
- systemd service integration for Linux deployment

## Directory Structure

See [`docs/STRUCTURE.md`](docs/STRUCTURE.md) for detailed information about the project organization.

### Quick Overview

- **`src/`** - Active Python backend scripts
- **`web/`** - Web frontend (PHP + HTML)
- **`config/`** - Configuration and service files
- **`scripts/`** - Utility scripts
- **`archive/`** - Old files, backups, and test data
- **`docs/`** - Project documentation

## Installation

1. Copy Python scripts from `src/` to your deployment directory
2. Install PHP files from `web/` to your web server
3. Install systemd service from `config/piec.service` if using Linux

## Files

### Python Backend (`src/`)
- `main.py` - Main entry point
- `test.py` - Testing utilities
- `construct.py` - Message construction
- `compare.py` - Data comparison

### Web Frontend (`web/`)
- `index.php` - Main interface
- `state.php` - State API
- `all.php` - Data API
- `style.css` - Styling

### Configuration (`config/`)
- `piec.service` - Systemd service definition

### Utilities (`scripts/`)
- `compare.sh` - Comparison helper script

## References

- Original project: https://github.com/twkrol/econetanalyze
- Archived versions in `archive/old_code/`

---

**Last Reorganized:** May 2026
