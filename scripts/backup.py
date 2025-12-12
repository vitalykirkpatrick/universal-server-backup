#!/usr/bin/env python3
"""
Universal Server Backup System - Main Backup Script
Creates full system images and uploads to Google Drive and/or AWS S3

Usage:
    python3 backup.py --backend all
    python3 backup.py --backend s3
    python3 backup.py --backend gdrive
    python3 backup.py --backend all --name "pre-upgrade"
"""

import os
import sys
import argparse
import subprocess
import json
import hashlib
from datetime import datetime
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from s3_backend import S3Backend
    from gdrive_backend import GDriveBackend
    from gcs_backend import GCSBackend
    from utils import (
        load_config, get_disk_info, estimate_backup_size,
        send_notification, log_message, format_size
    )
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure all required scripts are in the scripts/ directory")
    sys.exit(1)

class SystemBackup:
    def __init__(self, config_path="/etc/universal-backup/backup.conf"):
        """Initialize backup system"""
        self.config = load_config(config_path)
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.backup_name = self.config.get('general', {}).get('backup_name', 'server')
        self.temp_dir = Path("/tmp/universal-backup")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize backends
        self.backends = {}
        if 's3' in self.config.get('backends', {}).get('enabled', '').split(','):
            self.backends['s3'] = S3Backend(self.config)
        if 'gdrive' in self.config.get('backends', {}).get('enabled', '').split(','):
            self.backends['gdrive'] = GDriveBackend(self.config)
        if 'gcs' in self.config.get('backends', {}).get('enabled', '').split(','):
            self.backends['gcs'] = GCSBackend(self.config)
        
        self.image_path = None
        self.manifest = {}
        
    def get_backup_filename(self, custom_name=None):
        """Generate backup filename"""
        if custom_name:
            return f"{self.backup_name}_{custom_name}_{self.timestamp}.img.gz"
        return f"{self.backup_name}_full_{self.timestamp}.img.gz"
    
    def create_system_image(self, dry_run=False):
        """Create full system disk image"""
        log_message("INFO", "Starting system image creation...")
        
        # Get primary disk
        disk_info = get_disk_info()
        source_disk = disk_info['primary_disk']
        disk_size = disk_info['size_gb']
        
        log_message("INFO", f"Source disk: {source_disk} ({disk_size} GB)")
        
        if dry_run:
            log_message("INFO", "[DRY RUN] Would create image of {source_disk}")
            return "/tmp/dry-run-image.img.gz"
        
        # Check available space
        estimated_size = estimate_backup_size(source_disk)
        log_message("INFO", f"Estimated backup size: {format_size(estimated_size)}")
        
        # Create image filename
        image_filename = self.get_backup_filename()
        self.image_path = self.temp_dir / image_filename
        
        log_message("INFO", f"Creating compressed image: {self.image_path}")
        
        # Create disk image with dd and compress with pigz
        try:
            # Check if pigz is available
            subprocess.run(['which', 'pigz'], check=True, capture_output=True)
            compressor = 'pigz'
        except:
            log_message("WARN", "pigz not found, using gzip (slower)")
            compressor = 'gzip'
        
        # Build command
        compression_level = self.config.get('general', {}).get('compression_level', 6)
        
        # Use dd with progress monitoring via pv
        cmd = f"dd if={source_disk} bs=4M status=progress | {compressor} -{compression_level} > {self.image_path}"
        
        log_message("INFO", f"Running: {cmd}")
        log_message("INFO", "This may take several hours depending on disk size...")
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                check=True,
                stderr=subprocess.PIPE,
                text=True
            )
            log_message("INFO", "System image created successfully")
        except subprocess.CalledProcessError as e:
            log_message("ERROR", f"Failed to create system image: {e.stderr}")
            raise
        
        # Calculate checksum
        log_message("INFO", "Calculating checksum...")
        checksum = self.calculate_checksum(self.image_path)
        
        # Create manifest
        self.manifest = {
            'backup_name': self.backup_name,
            'timestamp': self.timestamp,
            'filename': image_filename,
            'source_disk': source_disk,
            'disk_size_gb': disk_size,
            'image_size_bytes': self.image_path.stat().st_size,
            'compression': compressor,
            'compression_level': compression_level,
            'checksum_sha256': checksum,
            'hostname': os.uname().nodename,
            'kernel': os.uname().release,
            'created_at': datetime.now().isoformat()
        }
        
        # Save manifest
        manifest_path = self.temp_dir / f"{image_filename}.manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(self.manifest, f, indent=2)
        
        log_message("INFO", f"Manifest saved: {manifest_path}")
        
        return self.image_path
    
    def calculate_checksum(self, filepath):
        """Calculate SHA256 checksum of file"""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def upload_to_backends(self, backends=['all'], dry_run=False):
        """Upload backup to specified backends"""
        if not self.image_path or not self.image_path.exists():
            log_message("ERROR", "No backup image found to upload")
            return False
        
        # Determine which backends to use
        if 'all' in backends:
            backends = list(self.backends.keys())
        
        results = {}
        
        for backend_name in backends:
            if backend_name not in self.backends:
                log_message("WARN", f"Backend '{backend_name}' not configured, skipping")
                continue
            
            log_message("INFO", f"Uploading to {backend_name.upper()}...")
            
            if dry_run:
                log_message("INFO", f"[DRY RUN] Would upload to {backend_name}")
                results[backend_name] = True
                continue
            
            try:
                backend = self.backends[backend_name]
                
                # Upload image
                success = backend.upload(
                    self.image_path,
                    self.manifest['filename']
                )
                
                if success:
                    # Upload manifest
                    manifest_path = self.temp_dir / f"{self.manifest['filename']}.manifest.json"
                    backend.upload(
                        manifest_path,
                        f"{self.manifest['filename']}.manifest.json"
                    )
                    log_message("INFO", f"✅ Upload to {backend_name} successful")
                    results[backend_name] = True
                else:
                    log_message("ERROR", f"❌ Upload to {backend_name} failed")
                    results[backend_name] = False
                    
            except Exception as e:
                log_message("ERROR", f"Exception during {backend_name} upload: {e}")
                results[backend_name] = False
        
        return all(results.values())
    
    def cleanup(self, keep_local=False):
        """Clean up temporary files"""
        if keep_local:
            log_message("INFO", f"Keeping local backup at: {self.image_path}")
            return
        
        log_message("INFO", "Cleaning up temporary files...")
        
        if self.image_path and self.image_path.exists():
            self.image_path.unlink()
            log_message("INFO", f"Removed: {self.image_path}")
        
        # Clean up manifest
        manifest_path = self.temp_dir / f"{self.manifest.get('filename', '')}.manifest.json"
        if manifest_path.exists():
            manifest_path.unlink()
            log_message("INFO", f"Removed: {manifest_path}")
    
    def run_backup(self, backends=['all'], custom_name=None, dry_run=False, keep_local=False):
        """Run complete backup process"""
        log_message("INFO", "="*70)
        log_message("INFO", "UNIVERSAL SERVER BACKUP - STARTING")
        log_message("INFO", "="*70)
        log_message("INFO", f"Backup Name: {self.backup_name}")
        log_message("INFO", f"Timestamp: {self.timestamp}")
        log_message("INFO", f"Backends: {', '.join(backends)}")
        log_message("INFO", "="*70)
        
        try:
            # Create system image
            image_path = self.create_system_image(dry_run=dry_run)
            
            if not dry_run:
                log_message("INFO", f"Image created: {image_path}")
                log_message("INFO", f"Size: {format_size(image_path.stat().st_size)}")
            
            # Upload to backends
            upload_success = self.upload_to_backends(backends, dry_run=dry_run)
            
            # Cleanup
            if not dry_run:
                self.cleanup(keep_local=keep_local)
            
            # Send notification
            if upload_success:
                log_message("INFO", "="*70)
                log_message("INFO", "✅ BACKUP COMPLETED SUCCESSFULLY")
                log_message("INFO", "="*70)
                send_notification(
                    self.config,
                    "Backup Successful",
                    f"Server backup completed: {self.backup_name}_{self.timestamp}"
                )
                return True
            else:
                log_message("ERROR", "="*70)
                log_message("ERROR", "❌ BACKUP FAILED")
                log_message("ERROR", "="*70)
                send_notification(
                    self.config,
                    "Backup Failed",
                    f"Server backup failed: {self.backup_name}_{self.timestamp}"
                )
                return False
                
        except Exception as e:
            log_message("ERROR", f"Backup failed with exception: {e}")
            send_notification(
                self.config,
                "Backup Error",
                f"Server backup error: {str(e)}"
            )
            return False

def main():
    parser = argparse.ArgumentParser(
        description='Universal Server Backup System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backup to all configured backends
  python3 backup.py --backend all
  
  # Backup to S3 only
  python3 backup.py --backend s3
  
  # Backup to Google Drive only
  python3 backup.py --backend gdrive
  
  # Custom backup name
  python3 backup.py --backend all --name "pre-upgrade"
  
  # Dry run (test without actual backup)
  python3 backup.py --backend all --dry-run
  
  # Keep local copy after upload
  python3 backup.py --backend s3 --keep-local
        """
    )
    
    parser.add_argument(
        '--backend',
        choices=['all', 's3', 'gdrive', 'gcs'],
        default='all',
        help='Backup backend to use'
    )
    parser.add_argument(
        '--name',
        help='Custom backup name'
    )
    parser.add_argument(
        '--config',
        default='/etc/universal-backup/backup.conf',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Test run without actual backup'
    )
    parser.add_argument(
        '--keep-local',
        action='store_true',
        help='Keep local backup copy after upload'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.geteuid() != 0 and not args.dry_run:
        print("Error: This script must be run as root (use sudo)")
        sys.exit(1)
    
    # Run backup
    backup = SystemBackup(config_path=args.config)
    success = backup.run_backup(
        backends=[args.backend],
        custom_name=args.name,
        dry_run=args.dry_run,
        keep_local=args.keep_local
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
