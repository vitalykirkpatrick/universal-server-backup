# Deployment Guide

This guide explains how to deploy the Universal Server Backup system to your production servers.

## Quick Deployment

### One-Line Installation

```bash
curl -sSL https://raw.githubusercontent.com/vitalykirkpatrick/universal-server-backup/master/scripts/install.sh | sudo bash
```

Or clone and install:

```bash
git clone https://github.com/vitalykirkpatrick/universal-server-backup.git
cd universal-server-backup
sudo bash scripts/install.sh
```

## Post-Installation Configuration

### 1. Configure Backup Settings

Edit `/etc/universal-backup/backup.conf`:

```bash
sudo nano /etc/universal-backup/backup.conf
```

Key settings:
- `backup_name`: Your server identifier
- `backends.enabled`: Choose `s3`, `gdrive`, or both
- `s3.bucket_name`: Your S3 bucket name
- `gdrive.folder_name`: Your Google Drive folder
- `schedule.cron_schedule`: Backup frequency

### 2. Add Credentials

Edit `/etc/universal-backup/credentials.env`:

```bash
sudo nano /etc/universal-backup/credentials.env
```

Add your AWS and/or Google Drive credentials (see INSTALLATION.md for details).

### 3. Test Configuration

```bash
# Dry run (no actual backup)
sudo universal-backup --backend all --dry-run

# Check credentials
source /etc/universal-backup/credentials.env
echo $AWS_ACCESS_KEY_ID
echo $GOOGLE_OAUTH_CLIENT_ID
```

## Multiple Server Deployment

### Using Ansible

Create `deploy-backup.yml`:

```yaml
---
- name: Deploy Universal Server Backup
  hosts: all
  become: yes
  
  vars:
    backup_repo: "https://github.com/vitalykirkpatrick/universal-server-backup.git"
    aws_access_key: "{{ lookup('env', 'AWS_ACCESS_KEY_ID') }}"
    aws_secret_key: "{{ lookup('env', 'AWS_SECRET_ACCESS_KEY') }}"
    
  tasks:
    - name: Clone repository
      git:
        repo: "{{ backup_repo }}"
        dest: /opt/universal-server-backup
        
    - name: Run installer
      shell: bash /opt/universal-server-backup/scripts/install.sh
      
    - name: Configure credentials
      template:
        src: credentials.env.j2
        dest: /etc/universal-backup/credentials.env
        mode: '0600'
        
    - name: Configure settings
      template:
        src: backup.conf.j2
        dest: /etc/universal-backup/backup.conf
```

Run deployment:

```bash
ansible-playbook -i inventory.ini deploy-backup.yml
```

### Using SSH Loop

```bash
#!/bin/bash
# deploy-to-servers.sh

SERVERS=(
    "server1.example.com"
    "server2.example.com"
    "server3.example.com"
)

for server in "${SERVERS[@]}"; do
    echo "Deploying to $server..."
    
    ssh root@$server << 'EOF'
        cd /opt
        git clone https://github.com/vitalykirkpatrick/universal-server-backup.git
        cd universal-server-backup
        bash scripts/install.sh
EOF
    
    # Copy credentials
    scp credentials.env root@$server:/etc/universal-backup/credentials.env
    
    echo "✅ Deployed to $server"
done
```

## Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    pigz \
    pv \
    util-linux \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip3 install boto3 google-auth google-api-python-client

# Clone repository
RUN git clone https://github.com/vitalykirkpatrick/universal-server-backup.git /opt/universal-backup

# Copy scripts
COPY scripts/*.py /opt/universal-backup/

# Create directories
RUN mkdir -p /etc/universal-backup /var/log/universal-backup

# Copy configuration
COPY config/backup.conf /etc/universal-backup/backup.conf
COPY config/credentials.env /etc/universal-backup/credentials.env

# Set entrypoint
ENTRYPOINT ["/opt/universal-backup/backup.py"]
CMD ["--backend", "all"]
```

Build and run:

```bash
docker build -t universal-backup .
docker run -v /dev:/dev --privileged universal-backup
```

## Cloud-Specific Deployments

### AWS EC2

User data script for auto-deployment:

```bash
#!/bin/bash
cd /opt
git clone https://github.com/vitalykirkpatrick/universal-server-backup.git
cd universal-server-backup
bash scripts/install.sh

# Configure for S3
cat > /etc/universal-backup/credentials.env << 'EOF'
export AWS_ACCESS_KEY_ID="$(ec2-metadata --instance-id)"
export AWS_SECRET_ACCESS_KEY="$(ec2-metadata --security-credentials)"
EOF

# Use instance role instead of keys
```

### Google Cloud Platform

```bash
#!/bin/bash
cd /opt
git clone https://github.com/vitalykirkpatrick/universal-server-backup.git
cd universal-server-backup
bash scripts/install.sh

# Use service account
gcloud auth application-default login
```

### Azure

```bash
#!/bin/bash
cd /opt
git clone https://github.com/vitalykirkpatrick/universal-server-backup.git
cd universal-server-backup
bash scripts/install.sh

# Configure for Azure Blob Storage (requires modification)
```

## Verification

### Test Backup

```bash
# Create test backup
sudo universal-backup --backend s3 --name "deployment-test"

# Verify upload
sudo universal-restore --list --backend s3
```

### Monitor Logs

```bash
# Real-time log monitoring
sudo tail -f /var/log/universal-backup/backup_$(date +%Y-%m-%d).log

# Check cron execution
sudo tail -f /var/log/universal-backup/cron.log
```

### Check Cron Job

```bash
sudo crontab -l | grep universal-backup
```

### Check Systemd Service

```bash
sudo systemctl status universal-backup.service
sudo systemctl status universal-backup.timer
```

## Troubleshooting

### Permission Issues

```bash
sudo chmod 600 /etc/universal-backup/credentials.env
sudo chown root:root /etc/universal-backup/*
```

### Python Dependencies

```bash
sudo pip3 install --upgrade boto3 google-auth google-api-python-client
```

### Disk Space

```bash
# Check available space
df -h /tmp

# Clean up old temporary files
sudo rm -rf /tmp/universal-backup/*
sudo rm -rf /tmp/universal-restore/*
```

## Updating

### Update All Servers

```bash
#!/bin/bash
# update-backup-system.sh

SERVERS=(
    "server1.example.com"
    "server2.example.com"
)

for server in "${SERVERS[@]}"; do
    echo "Updating $server..."
    
    ssh root@$server << 'EOF'
        cd /opt/universal-server-backup
        git pull
        # Restart if needed
        systemctl restart universal-backup.timer
EOF
    
    echo "✅ Updated $server"
done
```

## Monitoring

### Centralized Logging

Send logs to centralized server:

```bash
# On each server
sudo apt-get install rsyslog

# Configure rsyslog
cat >> /etc/rsyslog.d/50-universal-backup.conf << 'EOF'
$ModLoad imfile
$InputFileName /var/log/universal-backup/backup_*.log
$InputFileTag universal-backup:
$InputFileStateFile stat-universal-backup
$InputFileSeverity info
$InputFileFacility local7
$InputRunFileMonitor

*.* @@log-server.example.com:514
EOF

sudo systemctl restart rsyslog
```

### Email Alerts

Configure SMTP in credentials.env:

```bash
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="alerts@example.com"
export SMTP_PASS="app-password"
export SMTP_FROM="backup@yourserver.com"
```

### Monitoring Dashboard

Use Grafana + Prometheus to monitor:
- Backup success/failure rates
- Backup sizes
- Backup duration
- Storage usage

## Best Practices

1. **Test Restores Regularly**: Schedule quarterly restore tests
2. **Monitor Storage Costs**: Set up billing alerts
3. **Rotate Credentials**: Change API keys annually
4. **Document Custom Changes**: Keep deployment notes
5. **Version Control Configs**: Store configs in private repo
6. **Automate Updates**: Use CI/CD for updates
7. **Monitor Logs**: Set up log aggregation
8. **Test Disaster Recovery**: Practice full server rebuilds

## Security Considerations

1. **Credentials**: Never commit credentials to git
2. **File Permissions**: Keep credentials.env at 600
3. **Network Security**: Use VPN for restore operations
4. **Encryption**: Enable backup encryption for sensitive data
5. **Access Control**: Limit who can restore backups
6. **Audit Logs**: Review backup/restore logs regularly

## Support

For deployment issues:
- GitHub Issues: https://github.com/vitalykirkpatrick/universal-server-backup/issues
- Documentation: https://github.com/vitalykirkpatrick/universal-server-backup/docs
