#!/bin/bash
#
# Universal Server Backup - Installation Script
# Installs and configures the backup system on any Linux server
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "Universal Server Backup - Installation"
echo "======================================================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VER=$VERSION_ID
else
    echo -e "${RED}Error: Cannot detect OS${NC}"
    exit 1
fi

echo -e "${GREEN}Detected OS: $OS $VER${NC}"
echo ""

# Install dependencies
echo "Installing dependencies..."

if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
    apt-get update
    apt-get install -y \
        python3 \
        python3-pip \
        pigz \
        pv \
        util-linux \
        curl \
        git
elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ] || [ "$OS" = "fedora" ]; then
    yum install -y \
        python3 \
        python3-pip \
        pigz \
        pv \
        util-linux \
        curl \
        git
else
    echo -e "${YELLOW}Warning: Unknown OS, attempting to install with apt-get${NC}"
    apt-get update
    apt-get install -y python3 python3-pip pigz pv curl git
fi

echo -e "${GREEN}✅ System dependencies installed${NC}"
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."

pip3 install --upgrade pip
pip3 install boto3 google-auth google-api-python-client google-auth-oauthlib google-auth-httplib2

echo -e "${GREEN}✅ Python dependencies installed${NC}"
echo ""

# Create directories
echo "Creating directories..."

mkdir -p /etc/universal-backup
mkdir -p /var/log/universal-backup
mkdir -p /opt/universal-backup

echo -e "${GREEN}✅ Directories created${NC}"
echo ""

# Copy scripts
echo "Installing scripts..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

cp -r "$SCRIPT_DIR"/*.py /opt/universal-backup/
chmod +x /opt/universal-backup/*.py

echo -e "${GREEN}✅ Scripts installed to /opt/universal-backup/${NC}"
echo ""

# Create configuration file
echo "Creating configuration file..."

if [ ! -f /etc/universal-backup/backup.conf ]; then
    cat > /etc/universal-backup/backup.conf << 'EOF'
[general]
backup_name = my-server
compression_level = 6
encryption_enabled = false
notification_email = 

[backends]
enabled = s3,gdrive
default = s3

[s3]
bucket_name = my-server-backups
region = us-east-1
storage_class = STANDARD_IA

[gdrive]
folder_name = ServerBackups
shared_drive_id = 

[retention]
keep_daily = 7
keep_weekly = 4
keep_monthly = 6
keep_yearly = 2

[schedule]
auto_backup = true
cron_schedule = 0 2 * * 0
EOF

    echo -e "${GREEN}✅ Configuration file created: /etc/universal-backup/backup.conf${NC}"
    echo -e "${YELLOW}⚠️  Please edit this file to configure your settings${NC}"
else
    echo -e "${YELLOW}Configuration file already exists, skipping${NC}"
fi

echo ""

# Create credentials template
echo "Creating credentials template..."

if [ ! -f /etc/universal-backup/credentials.env ]; then
    cat > /etc/universal-backup/credentials.env << 'EOF'
# AWS S3 Credentials
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_DEFAULT_REGION="us-east-1"

# Google Drive API Credentials
export GOOGLE_OAUTH_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_OAUTH_CLIENT_SECRET="your-client-secret"
export GOOGLE_DRIVE_REFRESH_TOKEN="your-refresh-token"
export GOOGLE_DRIVE_ACCESS_TOKEN="your-access-token"

# Optional: Email Notifications
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="your-email@gmail.com"
export SMTP_PASS="your-app-password"
export SMTP_FROM="backup@yourserver.com"
EOF

    chmod 600 /etc/universal-backup/credentials.env
    echo -e "${GREEN}✅ Credentials template created: /etc/universal-backup/credentials.env${NC}"
    echo -e "${YELLOW}⚠️  Please edit this file to add your credentials${NC}"
else
    echo -e "${YELLOW}Credentials file already exists, skipping${NC}"
fi

echo ""

# Create wrapper script
echo "Creating backup wrapper script..."

cat > /usr/local/bin/universal-backup << 'EOF'
#!/bin/bash
# Load credentials
if [ -f /etc/universal-backup/credentials.env ]; then
    source /etc/universal-backup/credentials.env
fi

# Run backup
python3 /opt/universal-backup/backup.py "$@"
EOF

chmod +x /usr/local/bin/universal-backup

cat > /usr/local/bin/universal-restore << 'EOF'
#!/bin/bash
# Load credentials
if [ -f /etc/universal-backup/credentials.env ]; then
    source /etc/universal-backup/credentials.env
fi

# Run restore
python3 /opt/universal-backup/restore.py "$@"
EOF

chmod +x /usr/local/bin/universal-restore

echo -e "${GREEN}✅ Wrapper scripts created${NC}"
echo ""

# Setup cron job
echo "Setting up automated backups..."

CRON_SCHEDULE=$(grep "cron_schedule" /etc/universal-backup/backup.conf | cut -d'=' -f2 | xargs)

if [ -z "$CRON_SCHEDULE" ]; then
    CRON_SCHEDULE="0 2 * * 0"  # Default: Weekly on Sunday at 2 AM
fi

# Check if cron job already exists
if ! crontab -l 2>/dev/null | grep -q "universal-backup"; then
    (crontab -l 2>/dev/null; echo "$CRON_SCHEDULE /usr/local/bin/universal-backup --backend all >> /var/log/universal-backup/cron.log 2>&1") | crontab -
    echo -e "${GREEN}✅ Cron job installed: $CRON_SCHEDULE${NC}"
else
    echo -e "${YELLOW}Cron job already exists, skipping${NC}"
fi

echo ""

# Create systemd service (optional)
echo "Creating systemd service..."

cat > /etc/systemd/system/universal-backup.service << 'EOF'
[Unit]
Description=Universal Server Backup
After=network.target

[Service]
Type=oneshot
EnvironmentFile=/etc/universal-backup/credentials.env
ExecStart=/usr/local/bin/universal-backup --backend all
StandardOutput=journal
StandardError=journal
SyslogIdentifier=universal-backup

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo -e "${GREEN}✅ Systemd service created${NC}"
echo "   Start manually with: systemctl start universal-backup"
echo ""

# Create systemd timer (alternative to cron)
cat > /etc/systemd/system/universal-backup.timer << 'EOF'
[Unit]
Description=Universal Server Backup Timer
Requires=universal-backup.service

[Timer]
OnCalendar=Sun *-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

echo -e "${GREEN}✅ Systemd timer created${NC}"
echo "   Enable with: systemctl enable --now universal-backup.timer"
echo ""

# Final instructions
echo "======================================================================"
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo "======================================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Configure your settings:"
echo "   sudo nano /etc/universal-backup/backup.conf"
echo ""
echo "2. Add your credentials:"
echo "   sudo nano /etc/universal-backup/credentials.env"
echo ""
echo "3. Test your configuration:"
echo "   sudo universal-backup --backend all --dry-run"
echo ""
echo "4. Run your first backup:"
echo "   sudo universal-backup --backend all"
echo ""
echo "5. List backups:"
echo "   sudo universal-restore --list --backend s3"
echo ""
echo "Automated backups are scheduled for: $CRON_SCHEDULE"
echo "Logs are stored in: /var/log/universal-backup/"
echo ""
echo "For help:"
echo "   universal-backup --help"
echo "   universal-restore --help"
echo ""
echo "======================================================================"
