# Universal Server Backup System - Summary

## Project Overview

**Repository**: https://github.com/vitalykirkpatrick/universal-server-backup

A complete, production-ready disaster recovery solution that creates full system disk images and stores them securely in cloud storage (AWS S3 and Google Drive). Designed for easy deployment across multiple Linux servers with automated backups and command-line restoration.

## Key Features

### Backup Capabilities
- **Full System Image**: Complete disk-level backup (bootable)
- **Dual Cloud Storage**: AWS S3 and Google Drive API support
- **Efficient Compression**: Multi-threaded compression with pigz
- **Automated Scheduling**: Cron-based automatic backups
- **Progress Tracking**: Real-time progress and detailed logging
- **Checksum Verification**: SHA-256 integrity verification

### Restoration Capabilities
- **Command-Line Restoration**: Simple CLI-based recovery
- **Multi-Source Support**: Restore from S3 or Google Drive
- **Integrity Verification**: Pre-restore checksum validation
- **Live USB Compatible**: Works from rescue environments
- **Selective Restore**: Choose specific backup version

### System Components Backed Up
- Complete disk image (all partitions)
- System packages (apt, pip, npm)
- Nginx configurations and SSL certificates
- Cron jobs and scheduled tasks
- Environment variables and secrets
- Database configurations
- Application files and data

## Repository Structure

```
universal-server-backup/
├── README.md                    # Main documentation
├── LICENSE                      # MIT License
├── SUMMARY.md                   # This file
├── scripts/
│   ├── install.sh              # One-command installer
│   ├── backup.py               # Main backup script
│   ├── restore.py              # Main restoration script
│   ├── s3_backend.py           # AWS S3 integration
│   ├── gdrive_backend.py       # Google Drive integration
│   └── utils.py                # Utility functions
├── config/
│   ├── backup.conf.example     # Configuration template
│   └── credentials.env.example # Credentials template
└── docs/
    ├── INSTALLATION.md         # Installation guide
    └── DEPLOYMENT.md           # Deployment guide
```

## Quick Start

### Installation (3 steps)

```bash
# 1. Clone repository
git clone https://github.com/vitalykirkpatrick/universal-server-backup.git
cd universal-server-backup

# 2. Run installer
sudo bash scripts/install.sh

# 3. Configure credentials
sudo nano /etc/universal-backup/credentials.env
```

### First Backup

```bash
# Test configuration
sudo universal-backup --backend all --dry-run

# Run backup
sudo universal-backup --backend s3
```

### Restoration (Disaster Recovery)

```bash
# Boot from Live USB
# Install dependencies
sudo apt update && sudo apt install -y git python3 python3-pip

# Clone repository
git clone https://github.com/vitalykirkpatrick/universal-server-backup.git
cd universal-server-backup

# Install packages
sudo pip3 install boto3 google-auth google-api-python-client

# Configure credentials
sudo nano config/credentials.env
source config/credentials.env

# List backups
sudo python3 scripts/restore.py --list --backend s3

# Restore
sudo python3 scripts/restore.py --backend s3 --backup latest
```

## Production Deployment

### Deployed On
- **Server**: audiobooksmith (172.245.67.47)
- **Installation Path**: `/opt/universal-server-backup/`
- **Configuration**: `/etc/universal-backup/`
- **Logs**: `/var/log/universal-backup/`

### Configured Backends
- ✅ AWS S3 (bucket: audiobooksmith-backups)
- ✅ Google Drive (folder: ServerBackups)

### Automated Backups
- **Schedule**: Weekly on Sunday at 2 AM
- **Method**: Cron job
- **Command**: `universal-backup --backend all`

### Commands Available
```bash
# Backup commands
universal-backup --backend all
universal-backup --backend s3
universal-backup --backend gdrive
universal-backup --backend all --name "pre-upgrade"

# Restore commands
universal-restore --list --backend s3
universal-restore --backend s3 --backup latest
universal-restore --backend s3 --backup "specific-backup.img.gz"
```

## Technical Details

### Dependencies
- **System**: python3, pip3, pigz, pv, util-linux, curl, git
- **Python**: boto3, google-auth, google-api-python-client

### Backup Process
1. Create disk image with `dd`
2. Compress with `pigz` (parallel gzip)
3. Calculate SHA-256 checksum
4. Create manifest JSON
5. Upload to cloud storage
6. Verify upload
7. Clean up temporary files

### Restore Process
1. Download backup from cloud
2. Download manifest
3. Verify checksum
4. Decompress image
5. Write to disk with `dd`
6. Sync filesystem
7. Reboot

### Storage Efficiency
- Compression ratio: ~40% (varies by data)
- Example: 50GB disk → ~20GB backup
- Incremental backups: Not yet implemented (planned)

## Configuration Files

### Main Configuration
Location: `/etc/universal-backup/backup.conf`

```ini
[general]
backup_name = audiobooksmith
compression_level = 6

[backends]
enabled = s3,gdrive
default = s3

[s3]
bucket_name = audiobooksmith-backups
region = us-east-1
storage_class = STANDARD_IA

[retention]
keep_daily = 7
keep_weekly = 4
keep_monthly = 6
```

### Credentials
Location: `/etc/universal-backup/credentials.env`
Permissions: `600` (owner read/write only)

Contains:
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- GOOGLE_OAUTH_CLIENT_ID
- GOOGLE_OAUTH_CLIENT_SECRET
- GOOGLE_DRIVE_REFRESH_TOKEN
- GOOGLE_DRIVE_ACCESS_TOKEN

## Monitoring & Logs

### Log Files
- Daily logs: `/var/log/universal-backup/backup_YYYY-MM-DD.log`
- Cron logs: `/var/log/universal-backup/cron.log`

### Monitoring Commands
```bash
# View today's log
sudo tail -f /var/log/universal-backup/backup_$(date +%Y-%m-%d).log

# Check cron job
sudo crontab -l | grep universal-backup

# Check systemd service
sudo systemctl status universal-backup.service
sudo systemctl status universal-backup.timer
```

## Security

### Credentials Security
- Stored in `/etc/universal-backup/credentials.env`
- File permissions: `600` (root only)
- Never committed to git
- Separate from application code

### Backup Security
- Optional AES-256 encryption
- HTTPS/TLS for all transfers
- Checksum verification
- Secure deletion of temporary files

### Access Control
- Root/sudo required for backup/restore
- Cloud storage access via API keys
- No plaintext passwords in logs

## Cost Estimates

### AWS S3 Storage
- Standard-IA: $0.0125/GB/month
- Example: 20GB backup = $0.25/month
- Transfer: $0.09/GB (outbound)

### Google Drive
- 15GB free
- 100GB: $1.99/month
- 200GB: $2.99/month

### Recommendations
- Use S3 Standard-IA for cost efficiency
- Use Google Drive for small servers (< 15GB)
- Use both for redundancy

## Disaster Recovery Scenarios

### Scenario 1: Complete Server Loss
1. Boot from Ubuntu Live USB
2. Install git and Python
3. Clone repository
4. Configure credentials
5. Run restore script
6. Reboot into restored system
**Time**: 2-4 hours (depending on disk size)

### Scenario 2: Accidental File Deletion
- System image backups don't support file-level recovery
- Must restore entire system or use file-based backup
- **Recommendation**: Use separate file backup for important data

### Scenario 3: Server Migration
1. Create backup on old server
2. Provision new server
3. Boot new server from Live USB
4. Restore backup to new server
5. Update network configuration
6. Reboot
**Time**: 3-5 hours

## Limitations

### Current Limitations
- ❌ No incremental backups (full only)
- ❌ No file-level recovery
- ❌ Requires offline backup (unmounted partitions)
- ❌ No real-time replication
- ❌ Single-threaded upload (per backend)

### Planned Features
- [ ] Incremental backup support
- [ ] Parallel multi-part uploads
- [ ] Web-based management interface
- [ ] Real-time monitoring dashboard
- [ ] Automated restore testing
- [ ] Multi-region replication
- [ ] Database-specific optimizations

## Comparison with Alternatives

### vs. Clonezilla
- ✅ Automated cloud upload
- ✅ API integration
- ✅ Scheduled backups
- ❌ No GUI

### vs. Rsync/Restic
- ✅ Full disk image (bootable)
- ✅ Bare metal recovery
- ❌ No incremental backups
- ❌ Larger backup size

### vs. Cloud Provider Snapshots
- ✅ Works with any cloud/on-prem
- ✅ No vendor lock-in
- ✅ Multiple storage options
- ❌ Manual setup required

## Best Practices

### Backup Strategy
1. **3-2-1 Rule**: 3 copies, 2 different media, 1 offsite
2. **Test Restores**: Quarterly restore tests
3. **Monitor Logs**: Review backup logs weekly
4. **Verify Checksums**: Always verify after download
5. **Document Changes**: Keep deployment notes

### Security
1. **Rotate Credentials**: Change API keys annually
2. **Encrypt Backups**: Enable encryption for sensitive data
3. **Secure Credentials**: Use 600 permissions
4. **Audit Access**: Review who can restore
5. **Use IAM Roles**: Prefer roles over keys (AWS)

### Cost Optimization
1. **Use IA Storage**: Standard-IA for S3
2. **Set Retention**: Auto-delete old backups
3. **Compress Efficiently**: Balance speed vs size
4. **Monitor Usage**: Set billing alerts
5. **Clean Temp Files**: Remove after upload

## Maintenance

### Regular Tasks
- **Weekly**: Review backup logs
- **Monthly**: Verify backup integrity
- **Quarterly**: Test restoration
- **Annually**: Rotate credentials

### Updates
```bash
# Update repository
cd /opt/universal-server-backup
git pull

# Update Python packages
sudo pip3 install --upgrade boto3 google-auth google-api-python-client

# Restart services
sudo systemctl restart universal-backup.timer
```

## Support & Contributing

### Getting Help
- **Documentation**: https://github.com/vitalykirkpatrick/universal-server-backup/docs
- **Issues**: https://github.com/vitalykirkpatrick/universal-server-backup/issues
- **Discussions**: https://github.com/vitalykirkpatrick/universal-server-backup/discussions

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

### Reporting Issues
Include:
- OS and version
- Python version
- Error messages
- Log files
- Steps to reproduce

## License

MIT License - See LICENSE file for details.

## Credits

Developed for universal server disaster recovery.

**Technologies Used**:
- Python 3
- boto3 (AWS SDK)
- Google Drive API
- pigz (parallel gzip)
- dd (disk imaging)

---

**Last Updated**: December 12, 2024
**Version**: 1.0.0
**Status**: Production Ready ✅
