# Installation Guide

This guide will walk you through installing the Universal Server Backup system on your Linux server.

## Prerequisites

### System Requirements
- Linux server (Ubuntu 20.04+, Debian 10+, CentOS 8+, or similar)
- Root or sudo access
- Minimum 10GB free disk space for temporary files
- Internet connection

### Cloud Storage Requirements

You'll need at least one of the following:

**Option 1: AWS S3**
- AWS account
- IAM user with S3 permissions
- Access Key ID and Secret Access Key

**Option 2: Google Drive**
- Google account
- Google Cloud project with Drive API enabled
- OAuth 2.0 credentials

## Installation Steps

### Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/universal-server-backup.git
cd universal-server-backup
```

### Step 2: Run Installer

```bash
sudo bash scripts/install.sh
```

The installer will:
- Install system dependencies (python3, pigz, pv, etc.)
- Install Python packages (boto3, google-api-python-client)
- Create configuration directories
- Copy scripts to `/opt/universal-backup/`
- Create wrapper commands (`universal-backup`, `universal-restore`)
- Set up cron job for automated backups
- Create systemd service and timer

### Step 3: Configure Settings

Edit the main configuration file:

```bash
sudo nano /etc/universal-backup/backup.conf
```

Key settings to configure:

```ini
[general]
backup_name = my-server          # Change to your server name
notification_email = you@example.com

[backends]
enabled = s3,gdrive              # Choose which backends to enable

[s3]
bucket_name = my-server-backups  # Your S3 bucket name
region = us-east-1               # Your AWS region

[gdrive]
folder_name = ServerBackups      # Google Drive folder name
```

### Step 4: Add Credentials

Edit the credentials file:

```bash
sudo nano /etc/universal-backup/credentials.env
```

#### For AWS S3:

```bash
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_DEFAULT_REGION="us-east-1"
```

**How to get AWS credentials:**
1. Log in to AWS Console
2. Go to IAM → Users → Your User
3. Security Credentials tab
4. Create Access Key
5. Copy Access Key ID and Secret Access Key

**Required IAM Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject",
        "s3:CreateBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-server-backups",
        "arn:aws:s3:::my-server-backups/*"
      ]
    }
  ]
}
```

#### For Google Drive:

```bash
export GOOGLE_OAUTH_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_OAUTH_CLIENT_SECRET="your-client-secret"
export GOOGLE_DRIVE_REFRESH_TOKEN="your-refresh-token"
export GOOGLE_DRIVE_ACCESS_TOKEN="your-access-token"
```

**How to get Google Drive credentials:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google Drive API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download credentials JSON
6. Use OAuth Playground or run authorization script to get tokens

**Quick OAuth Setup:**

```bash
# Install Google Auth library
pip3 install google-auth-oauthlib

# Create auth script
cat > /tmp/google_auth.py << 'EOF'
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.file']

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

print(f"Refresh Token: {creds.refresh_token}")
print(f"Access Token: {creds.token}")
EOF

# Run it (will open browser)
python3 /tmp/google_auth.py
```

### Step 5: Test Configuration

Test your setup without actually creating a backup:

```bash
sudo universal-backup --backend all --dry-run
```

This will verify:
- All dependencies are installed
- Configuration is valid
- Credentials are working
- Cloud storage is accessible

### Step 6: Run First Backup

Create your first backup:

```bash
# Backup to all configured backends
sudo universal-backup --backend all

# Or backup to specific backend
sudo universal-backup --backend s3
sudo universal-backup --backend gdrive
```

**Note:** The first backup will take several hours depending on your disk size and internet speed.

## Verify Installation

### Check Backup Status

```bash
# List backups in S3
sudo universal-restore --list --backend s3

# List backups in Google Drive
sudo universal-restore --list --backend gdrive
```

### Check Logs

```bash
# View today's log
sudo tail -f /var/log/universal-backup/backup_$(date +%Y-%m-%d).log

# View cron log
sudo tail -f /var/log/universal-backup/cron.log
```

### Check Cron Job

```bash
# View cron jobs
sudo crontab -l

# Should see something like:
# 0 2 * * 0 /usr/local/bin/universal-backup --backend all >> /var/log/universal-backup/cron.log 2>&1
```

### Check Systemd Service

```bash
# Check service status
sudo systemctl status universal-backup.service

# Check timer status
sudo systemctl status universal-backup.timer

# Enable timer (alternative to cron)
sudo systemctl enable --now universal-backup.timer
```

## Troubleshooting

### "No module named 'boto3'"

```bash
sudo pip3 install boto3
```

### "AWS credentials not found"

Make sure credentials are set in `/etc/universal-backup/credentials.env` and the file is readable:

```bash
sudo chmod 600 /etc/universal-backup/credentials.env
sudo cat /etc/universal-backup/credentials.env
```

### "Google Drive authentication failed"

Regenerate your OAuth tokens:

```bash
# Delete old tokens
sudo rm -f ~/.credentials/drive-python-quickstart.json

# Run auth script again
python3 /tmp/google_auth.py
```

### "No space left on device"

The backup process needs temporary space. Free up space or change temp directory:

```bash
# Check disk space
df -h

# Clean up old backups
sudo rm -rf /tmp/universal-backup/*
sudo rm -rf /tmp/universal-restore/*
```

### "Permission denied"

Make sure you're running as root:

```bash
sudo universal-backup --backend all
```

## Uninstallation

To remove the backup system:

```bash
# Remove cron job
sudo crontab -l | grep -v universal-backup | crontab -

# Disable systemd timer
sudo systemctl disable --now universal-backup.timer

# Remove files
sudo rm -rf /opt/universal-backup
sudo rm -rf /etc/universal-backup
sudo rm -rf /var/log/universal-backup
sudo rm /usr/local/bin/universal-backup
sudo rm /usr/local/bin/universal-restore
sudo rm /etc/systemd/system/universal-backup.service
sudo rm /etc/systemd/system/universal-backup.timer
```

## Next Steps

- Read [BACKUP_GUIDE.md](BACKUP_GUIDE.md) for backup procedures
- Read [RESTORE_GUIDE.md](RESTORE_GUIDE.md) for restoration procedures
- Set up email notifications
- Test restoration on a test server

## Support

For issues or questions:
- GitHub Issues: https://github.com/yourusername/universal-server-backup/issues
- Documentation: https://github.com/yourusername/universal-server-backup/docs
