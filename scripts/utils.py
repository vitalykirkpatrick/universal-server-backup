#!/usr/bin/env python3
"""
Utility functions for Universal Server Backup
"""

import os
import sys
import subprocess
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
import configparser

def load_config(config_path):
    """Load configuration from INI file"""
    if not os.path.exists(config_path):
        # Try alternative paths
        alt_paths = [
            '/etc/universal-backup/backup.conf',
            os.path.join(os.path.dirname(__file__), '../config/backup.conf'),
            os.path.join(os.path.dirname(__file__), '../config/backup.conf.example')
        ]
        
        for alt_path in alt_paths:
            if os.path.exists(alt_path):
                config_path = alt_path
                break
        else:
            print(f"ERROR: Configuration file not found")
            print(f"Searched: {config_path}")
            print(f"Also tried: {', '.join(alt_paths)}")
            sys.exit(1)
    
    config = configparser.ConfigParser()
    config.read(config_path)
    
    # Convert to nested dict
    config_dict = {}
    for section in config.sections():
        config_dict[section] = dict(config[section])
    
    return config_dict

def get_disk_info():
    """Get information about primary disk"""
    try:
        # Find root partition
        result = subprocess.run(
            ['df', '-h', '/'],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            raise Exception("Cannot parse df output")
        
        # Parse output
        parts = lines[1].split()
        filesystem = parts[0]
        
        # Get actual disk device (not partition)
        if filesystem.startswith('/dev/'):
            # Remove partition number (e.g., /dev/sda1 -> /dev/sda)
            import re
            disk = re.sub(r'\d+$', '', filesystem)
            
            # Get disk size
            result = subprocess.run(
                ['lsblk', '-b', '-n', '-o', 'SIZE', disk],
                capture_output=True,
                text=True,
                check=True
            )
            
            size_bytes = int(result.stdout.strip().split()[0])
            size_gb = size_bytes / (1024**3)
            
            return {
                'primary_disk': disk,
                'size_bytes': size_bytes,
                'size_gb': round(size_gb, 2)
            }
        else:
            raise Exception(f"Cannot determine disk for filesystem: {filesystem}")
            
    except Exception as e:
        print(f"Error getting disk info: {e}")
        # Fallback
        return {
            'primary_disk': '/dev/sda',
            'size_bytes': 0,
            'size_gb': 0
        }

def estimate_backup_size(disk_path):
    """Estimate compressed backup size"""
    try:
        # Get used space on all partitions of this disk
        result = subprocess.run(
            ['lsblk', '-b', '-n', '-o', 'SIZE,FSUSE%', disk_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        total_used = 0
        for line in result.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 2 and parts[1] != '':
                size = int(parts[0])
                use_percent = int(parts[1].rstrip('%'))
                total_used += (size * use_percent / 100)
        
        # Estimate compression ratio (typically 30-50% for system data)
        estimated_compressed = total_used * 0.4
        
        return int(estimated_compressed)
        
    except Exception as e:
        print(f"Warning: Could not estimate backup size: {e}")
        return 0

def format_size(bytes_size):
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def log_message(level, message):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)
    
    # Also write to log file
    log_dir = Path("/var/log/universal-backup")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"backup_{datetime.now().strftime('%Y-%m-%d')}.log"
    
    try:
        with open(log_file, 'a') as f:
            f.write(log_line + '\n')
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}")

def send_notification(config, subject, message):
    """Send email notification"""
    email = config.get('general', {}).get('notification_email')
    
    if not email:
        return
    
    try:
        # Get SMTP settings from environment or config
        smtp_server = os.environ.get('SMTP_SERVER', 'localhost')
        smtp_port = int(os.environ.get('SMTP_PORT', 25))
        smtp_user = os.environ.get('SMTP_USER')
        smtp_pass = os.environ.get('SMTP_PASS')
        from_email = os.environ.get('SMTP_FROM', 'backup@localhost')
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = email
        msg['Subject'] = f"[Universal Backup] {subject}"
        
        body = f"""
Universal Server Backup Notification

{message}

Hostname: {os.uname().nodename}
Timestamp: {datetime.now().isoformat()}

---
This is an automated message from Universal Server Backup System
"""
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        if smtp_user and smtp_pass:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_pass)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
        
        server.send_message(msg)
        server.quit()
        
        log_message("INFO", f"Notification sent to {email}")
        
    except Exception as e:
        log_message("WARN", f"Failed to send notification: {e}")

def check_dependencies():
    """Check if required dependencies are installed"""
    required = ['dd', 'gzip', 'python3', 'lsblk', 'df']
    optional = ['pigz', 'pv']
    
    missing = []
    missing_optional = []
    
    for cmd in required:
        if not shutil.which(cmd):
            missing.append(cmd)
    
    for cmd in optional:
        if not shutil.which(cmd):
            missing_optional.append(cmd)
    
    if missing:
        print(f"ERROR: Missing required dependencies: {', '.join(missing)}")
        print("Install with: sudo apt install " + ' '.join(missing))
        return False
    
    if missing_optional:
        print(f"Warning: Missing optional dependencies: {', '.join(missing_optional)}")
        print("Install with: sudo apt install " + ' '.join(missing_optional))
    
    return True

def verify_checksum(filepath, expected_checksum):
    """Verify file checksum"""
    import hashlib
    
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    
    actual_checksum = sha256_hash.hexdigest()
    
    if actual_checksum == expected_checksum:
        log_message("INFO", "✅ Checksum verification passed")
        return True
    else:
        log_message("ERROR", "❌ Checksum verification failed!")
        log_message("ERROR", f"Expected: {expected_checksum}")
        log_message("ERROR", f"Actual: {actual_checksum}")
        return False

import shutil
