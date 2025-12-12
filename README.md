# Universal Server Backup System

**Complete disaster recovery solution for Linux servers with full system image backups to Google Drive and AWS S3.**

## Overview

This repository provides a complete, automated backup and restoration system that creates full disk images of your server and stores them securely in cloud storage. In the event of complete server failure, you can restore your entire system from a clean installation using simple command-line tools.

## Features

### Backup Capabilities
- **Full System Image Backup**: Complete disk-level backup (bootable)
- **Dual Cloud Storage**: Google Drive API and AWS S3 support
- **Efficient Compression**: Multi-threaded compression with pigz
- **Encryption**: AES-256 encryption for sensitive data
- **Automated Scheduling**: Cron-based automatic backups
- **Retention Policies**: Automatic cleanup of old backups
- **Progress Tracking**: Real-time backup progress and logging
- **Email Notifications**: Success/failure alerts

### Restoration Capabilities
- **Command-Line Restoration**: Simple CLI-based recovery
- **Multi-Source Support**: Restore from Google Drive or S3
- **Verification**: Integrity checks before restoration
- **Selective Restore**: Choose specific backup version
- **Live USB Compatible**: Works from rescue environments

### System Components Backed Up
- ✅ Complete disk image (all partitions)
- ✅ System packages (apt, pip, npm)
- ✅ Nginx configurations and sites
- ✅ SSL certificates (Let's Encrypt)
- ✅ Cron jobs and scheduled tasks
- ✅ Environment variables and secrets
- ✅ Database configurations
- ✅ Application files and data
- ✅ User accounts and permissions

## Quick Start

### 1. Installation

```bash
# Clone repository
git clone https://github.com/yourusername/universal-server-backup.git
cd universal-server-backup

# Run installer
sudo bash scripts/install.sh
```

### 2. Configuration

```bash
# Edit configuration file
sudo nano config/backup.conf

# Add your credentials
```

### 3. First Backup

```bash
# Run manual backup
sudo python3 scripts/backup.py --backend all
```

### 4. Restoration (After Disaster)

```bash
# Boot from Live USB, install dependencies
sudo apt update && sudo apt install -y git python3 python3-pip

# Clone and restore
git clone https://github.com/yourusername/universal-server-backup.git
cd universal-server-backup
sudo python3 scripts/restore.py --list
sudo python3 scripts/restore.py --backend s3 --backup latest
```

## Repository Structure

```
universal-server-backup/
├── README.md                    # This file
├── LICENSE                      # MIT License
├── scripts/                     # Main scripts
│   ├── install.sh              # Installation script
│   ├── backup.py               # Main backup script
│   ├── restore.py              # Main restoration script
│   ├── gdrive_backend.py       # Google Drive integration
│   ├── s3_backend.py           # AWS S3 integration
│   └── utils.py                # Common utilities
├── config/                      # Configuration files
│   ├── backup.conf.example     # Example configuration
│   └── credentials.json.example # Example credentials
├── docs/                        # Documentation
│   ├── INSTALLATION.md         # Installation guide
│   ├── BACKUP_GUIDE.md         # Backup procedures
│   └── RESTORE_GUIDE.md        # Restoration procedures
└── tests/                       # Test scripts
```

## Requirements

- Linux (Ubuntu 20.04+, Debian 10+)
- Python 3.8+
- Root/sudo access
- 10GB+ free disk space

## License

MIT License - see LICENSE file for details.

---

**⚠️ Important**: Always test your backups before relying on them in production!
