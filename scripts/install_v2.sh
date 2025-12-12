#!/bin/bash
#
# Universal Server Backup System v2 - One-Command Installer
# Fully automated, idempotent installation for any Linux server
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/vitalykirkpatrick/universal-server-backup/main/scripts/install_v2.sh | sudo bash
#
# Or:
#   sudo bash install_v2.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Version
VERSION="2.0.0"

# Configuration
INSTALL_DIR="/opt/universal-backup"
CONFIG_DIR="/etc/universal-backup"
LOG_DIR="/var/log/universal-backup"
TEMP_DIR="/tmp/universal-backup"
REPO_URL="https://github.com/vitalykirkpatrick/universal-server-backup.git"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo ""
    echo -e "${BLUE}======================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================================================${NC}"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Detect OS and version
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
        OS_NAME=$PRETTY_NAME
    else
        log_error "Cannot detect OS (missing /etc/os-release)"
        exit 1
    fi
    
    log_info "Detected OS: $OS_NAME"
}

# Generate unique server ID
generate_server_id() {
    local hostname=$(hostname)
    local machine_id=""
    
    # Try multiple sources for a unique ID
    if [ -f /sys/class/dmi/id/product_uuid ]; then
        machine_id=$(cat /sys/class/dmi/id/product_uuid 2>/dev/null | tr '[:upper:]' '[:lower:]')
    elif [ -f /etc/machine-id ]; then
        machine_id=$(cat /etc/machine-id)
    else
        # Fallback to MAC address
        machine_id=$(ip link show | grep -m 1 'link/ether' | awk '{print $2}' | tr -d ':')
    fi
    
    # Combine hostname and machine ID for uniqueness
    SERVER_ID="${hostname}-${machine_id:0:8}"
    log_info "Generated Server ID: $SERVER_ID"
}

# Install dependencies based on OS
install_dependencies() {
    log_step "Installing System Dependencies"
    
    case "$OS" in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq \
                python3 \
                python3-pip \
                python3-venv \
                pigz \
                pv \
                util-linux \
                curl \
                git \
                bc \
                jq \
                rsync \
                parted \
                lvm2 2>&1 | grep -v "already"
            ;;
        centos|rhel|fedora|rocky|almalinux)
            yum install -y -q \
                python3 \
                python3-pip \
                pigz \
                pv \
                util-linux \
                curl \
                git \
                bc \
                jq \
                rsync \
                parted \
                lvm2
            ;;
        arch|manjaro)
            pacman -Sy --noconfirm --needed \
                python \
                python-pip \
                pigz \
                pv \
                util-linux \
                curl \
                git \
                bc \
                jq \
                rsync \
                parted \
                lvm2
            ;;
        *)
            log_warn "Unknown OS: $OS, attempting Ubuntu/Debian package installation"
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip pigz pv curl git bc jq rsync parted lvm2
            ;;
    esac
    
    log_info "✅ System dependencies installed"
}

# Install Python dependencies
install_python_deps() {
    log_step "Installing Python Dependencies"
    
    # Create virtual environment (optional but recommended)
    if [ ! -d "$INSTALL_DIR/venv" ]; then
        python3 -m venv "$INSTALL_DIR/venv"
        log_info "Created Python virtual environment"
    fi
    
    # Activate venv and install packages
    source "$INSTALL_DIR/venv/bin/activate"
    
    pip3 install --quiet --upgrade pip
    pip3 install --quiet boto3 google-auth google-api-python-client google-auth-oauthlib google-auth-httplib2
    
    deactivate
    
    log_info "✅ Python dependencies installed"
}

# Create directory structure
create_directories() {
    log_step "Creating Directory Structure"
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$TEMP_DIR"
    
    # Set permissions
    chmod 755 "$INSTALL_DIR"
    chmod 755 "$CONFIG_DIR"
    chmod 755 "$LOG_DIR"
    chmod 1777 "$TEMP_DIR"  # Sticky bit for temp directory
    
    log_info "✅ Directories created"
}

# Clone or update repository
install_scripts() {
    log_step "Installing Backup Scripts"
    
    if [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Updating existing installation..."
        cd "$INSTALL_DIR"
        git pull --quiet
    else
        log_info "Cloning repository..."
        # If running from a local copy
        if [ -f "$(dirname "$0")/backup.py" ]; then
            SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            REPO_DIR="$(dirname "$SCRIPT_DIR")"
            cp -r "$REPO_DIR"/* "$INSTALL_DIR/"
        else
            # Clone from GitHub
            git clone --quiet "$REPO_URL" "$INSTALL_DIR"
        fi
    fi
    
    # Make scripts executable
    chmod +x "$INSTALL_DIR"/scripts/*.py 2>/dev/null || true
    chmod +x "$INSTALL_DIR"/scripts/*.sh 2>/dev/null || true
    
    log_info "✅ Scripts installed to $INSTALL_DIR"
}

# Configure server-specific settings
configure_system() {
    log_step "Configuring Server-Specific Settings"
    
    # Generate server ID
    generate_server_id
    
    # Create configuration file (idempotent)
    if [ ! -f "$CONFIG_DIR/backup.conf" ]; then
        cat > "$CONFIG_DIR/backup.conf" << EOF
[general]
backup_name = $SERVER_ID
compression_level = 6
encryption_enabled = false
notification_email = 
server_id = $SERVER_ID
hostname = $(hostname)

[backends]
enabled = s3,gdrive
default = s3

[s3]
bucket_name = universal-backups
region = us-east-1
storage_class = STANDARD_IA
folder = backups/$SERVER_ID

[gdrive]
folder_name = ServerBackups/$SERVER_ID
shared_drive_id = 

[gcs]
bucket_name = universal-backups-gcs
storage_class = NEARLINE
folder = backups/$SERVER_ID

[retention]
keep_daily = 7
keep_weekly = 4
keep_monthly = 6
keep_yearly = 2

[schedule]
auto_backup = true
full_backup_schedule = 0 2 1 * *
incremental_backup_schedule = 0 3 * * *
differential_backup_schedule = 0 2 * * 0
EOF
        log_info "✅ Configuration file created: $CONFIG_DIR/backup.conf"
    else
        log_warn "Configuration file already exists, skipping"
    fi
}

# Configure credentials (interactive or from environment)
configure_credentials() {
    log_step "Configuring Credentials"
    
    if [ ! -f "$CONFIG_DIR/credentials.env" ]; then
        # Check if credentials are in environment
        if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
            log_info "Using credentials from environment variables"
            cat > "$CONFIG_DIR/credentials.env" << EOF
# AWS S3 Credentials
export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# Google Drive API Credentials
export GOOGLE_OAUTH_CLIENT_ID="${GOOGLE_OAUTH_CLIENT_ID:-}"
export GOOGLE_OAUTH_CLIENT_SECRET="${GOOGLE_OAUTH_CLIENT_SECRET:-}"
export GOOGLE_DRIVE_REFRESH_TOKEN="${GOOGLE_DRIVE_REFRESH_TOKEN:-}"
export GOOGLE_DRIVE_ACCESS_TOKEN="${GOOGLE_DRIVE_ACCESS_TOKEN:-}"

# Google Cloud Storage
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-}"

# Optional: Email Notifications
export SMTP_SERVER="${SMTP_SERVER:-}"
export SMTP_PORT="${SMTP_PORT:-587}"
export SMTP_USER="${SMTP_USER:-}"
export SMTP_PASS="${SMTP_PASS:-}"
export SMTP_FROM="${SMTP_FROM:-backup@$(hostname)}"
EOF
        else
            # Create template
            cat > "$CONFIG_DIR/credentials.env" << 'EOF'
# AWS S3 Credentials
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_DEFAULT_REGION="us-east-1"

# Google Drive API Credentials
export GOOGLE_OAUTH_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_OAUTH_CLIENT_SECRET="your-client-secret"
export GOOGLE_DRIVE_REFRESH_TOKEN="your-refresh-token"
export GOOGLE_DRIVE_ACCESS_TOKEN="your-access-token"

# Google Cloud Storage
export GOOGLE_APPLICATION_CREDENTIALS="/etc/universal-backup/gcs-service-account.json"

# Optional: Email Notifications
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="your-email@gmail.com"
export SMTP_PASS="your-app-password"
export SMTP_FROM="backup@yourserver.com"
EOF
            log_warn "Credentials template created. Please edit: $CONFIG_DIR/credentials.env"
        fi
        
        chmod 600 "$CONFIG_DIR/credentials.env"
        log_info "✅ Credentials file created with secure permissions (600)"
    else
        log_warn "Credentials file already exists, skipping"
    fi
}

# Create wrapper scripts
create_wrappers() {
    log_step "Creating Command-Line Tools"
    
    # Backup wrapper
    cat > /usr/local/bin/universal-backup << 'EOF'
#!/bin/bash
# Load credentials
if [ -f /etc/universal-backup/credentials.env ]; then
    source /etc/universal-backup/credentials.env
fi

# Activate virtual environment
if [ -f /opt/universal-backup/venv/bin/activate ]; then
    source /opt/universal-backup/venv/bin/activate
fi

# Run backup
python3 /opt/universal-backup/scripts/backup.py "$@"
EOF
    
    chmod +x /usr/local/bin/universal-backup
    
    # Restore wrapper
    cat > /usr/local/bin/universal-restore << 'EOF'
#!/bin/bash
# Load credentials
if [ -f /etc/universal-backup/credentials.env ]; then
    source /etc/universal-backup/credentials.env
fi

# Activate virtual environment
if [ -f /opt/universal-backup/venv/bin/activate ]; then
    source /opt/universal-backup/venv/bin/activate
fi

# Run restore
python3 /opt/universal-backup/scripts/restore.py "$@"
EOF
    
    chmod +x /usr/local/bin/universal-restore
    
    log_info "✅ Command-line tools created"
    log_info "   - universal-backup"
    log_info "   - universal-restore"
}

# Setup systemd services and timers
setup_systemd() {
    log_step "Configuring Automated Backups (Systemd)"
    
    # Create service file
    cat > /etc/systemd/system/universal-backup.service << 'EOF'
[Unit]
Description=Universal Server Backup
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/universal-backup/credentials.env
ExecStart=/usr/local/bin/universal-backup --backend all
StandardOutput=journal
StandardError=journal
SyslogIdentifier=universal-backup
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
    
    # Create timer for monthly full backups
    cat > /etc/systemd/system/universal-backup-full.timer << 'EOF'
[Unit]
Description=Universal Server Backup - Monthly Full Backup
Requires=universal-backup.service

[Timer]
OnCalendar=monthly
Persistent=true
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
EOF
    
    # Create timer for daily incremental backups
    cat > /etc/systemd/system/universal-backup-incremental.timer << 'EOF'
[Unit]
Description=Universal Server Backup - Daily Incremental Backup
Requires=universal-backup.service

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=30m

[Install]
WantedBy=timers.target
EOF
    
    # Reload systemd
    systemctl daemon-reload
    
    log_info "✅ Systemd services and timers created"
    log_info "   Enable with: systemctl enable --now universal-backup-full.timer"
    log_info "   Enable with: systemctl enable --now universal-backup-incremental.timer"
}

# Display final instructions
show_completion_message() {
    log_step "Installation Complete!"
    
    echo ""
    echo -e "${GREEN}✅ Universal Backup System v$VERSION installed successfully!${NC}"
    echo ""
    echo "Server ID: ${BLUE}$SERVER_ID${NC}"
    echo "Installation Directory: ${BLUE}$INSTALL_DIR${NC}"
    echo "Configuration: ${BLUE}$CONFIG_DIR/backup.conf${NC}"
    echo "Credentials: ${BLUE}$CONFIG_DIR/credentials.env${NC}"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo ""
    echo "1. Configure your cloud credentials:"
    echo "   ${BLUE}sudo nano $CONFIG_DIR/credentials.env${NC}"
    echo ""
    echo "2. Test your configuration:"
    echo "   ${BLUE}sudo universal-backup --backend all --dry-run${NC}"
    echo ""
    echo "3. Run your first backup:"
    echo "   ${BLUE}sudo universal-backup --backend s3 --type full${NC}"
    echo ""
    echo "4. Enable automated backups:"
    echo "   ${BLUE}sudo systemctl enable --now universal-backup-full.timer${NC}"
    echo "   ${BLUE}sudo systemctl enable --now universal-backup-incremental.timer${NC}"
    echo ""
    echo "5. List backups:"
    echo "   ${BLUE}sudo universal-restore --list --backend s3${NC}"
    echo ""
    echo "For help:"
    echo "   ${BLUE}universal-backup --help${NC}"
    echo "   ${BLUE}universal-restore --help${NC}"
    echo ""
    log_step "Installation Log: $LOG_DIR/install.log"
}

# ============================================================================
# MAIN INSTALLATION FLOW
# ============================================================================

main() {
    log_step "Universal Server Backup System v$VERSION - Installer"
    
    # Redirect all output to log file
    exec > >(tee -a "$LOG_DIR/install.log")
    exec 2>&1
    
    check_root
    detect_os
    create_directories
    install_dependencies
    install_scripts
    install_python_deps
    configure_system
    configure_credentials
    create_wrappers
    setup_systemd
    show_completion_message
}

# Run main function
main "$@"
