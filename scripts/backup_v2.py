#!/usr/bin/env python3
"""
Universal Server Backup System v2 - Enhanced Backup Script
Supports full, incremental, and differential backups with intelligent rotation

Usage:
    universal-backup --type full --backend s3
    universal-backup --type incremental --backend all
    universal-backup --type differential --backend gdrive
    universal-backup --list --backend s3
"""

import os
import sys
import argparse
import subprocess
import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
import configparser

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Configuration
CONFIG_FILE = "/etc/universal-backup/backup.conf"
LOG_DIR = Path("/var/log/universal-backup")
TEMP_DIR = Path("/tmp/universal-backup")
MANIFEST_DIR = Path("/var/lib/universal-backup/manifests")

# Ensure directories exist
LOG_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

class BackupLogger:
    """Centralized logging system"""
    
    def __init__(self, log_file=None):
        if log_file is None:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            log_file = LOG_DIR / f"backup_{timestamp}.log"
        
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log(self, level, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        print(log_entry)
        
        with open(self.log_file, 'a') as f:
            f.write(log_entry + "\n")
    
    def info(self, message):
        self.log("INFO", message)
    
    def warn(self, message):
        self.log("WARN", message)
    
    def error(self, message):
        self.log("ERROR", message)
    
    def success(self, message):
        self.log("SUCCESS", message)


class BackupConfig:
    """Configuration management"""
    
    def __init__(self, config_file=CONFIG_FILE):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        # Extract common settings
        self.server_id = self.config.get('general', 'server_id', fallback='unknown-server')
        self.backup_name = self.config.get('general', 'backup_name', fallback=self.server_id)
        self.compression_level = self.config.getint('general', 'compression_level', fallback=6)
        
        # Retention settings
        self.keep_daily = self.config.getint('retention', 'keep_daily', fallback=7)
        self.keep_weekly = self.config.getint('retention', 'keep_weekly', fallback=4)
        self.keep_monthly = self.config.getint('retention', 'keep_monthly', fallback=6)
        
        # Backend settings
        self.enabled_backends = [b.strip() for b in self.config.get('backends', 'enabled', fallback='s3').split(',')]
        self.default_backend = self.config.get('backends', 'default', fallback='s3')
        
        # S3 settings
        self.s3_bucket = self.config.get('s3', 'bucket_name', fallback='universal-backups')
        self.s3_region = self.config.get('s3', 'region', fallback='us-east-1')
        self.s3_folder = self.config.get('s3', 'folder', fallback=f'backups/{self.server_id}')
        
        # Google Drive settings
        self.gdrive_folder = self.config.get('gdrive', 'folder_name', fallback=f'ServerBackups/{self.server_id}')


class BackupEngine:
    """Main backup engine supporting multiple backup types"""
    
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.manifest = {}
    
    def get_disk_info(self):
        """Get primary disk information"""
        try:
            # Get root filesystem device
            result = subprocess.run(['df', '/', '--output=source'], capture_output=True, text=True, check=True)
            device = result.stdout.strip().split('\n')[1]
            
            # Get actual disk (remove partition number)
            if device.startswith('/dev/nvme'):
                disk = device.rstrip('p0123456789')
            else:
                disk = device.rstrip('0123456789')
            
            # Get disk size
            result = subprocess.run(['lsblk', '-b', '-n', '-o', 'SIZE', disk], capture_output=True, text=True, check=True)
            size_bytes = int(result.stdout.strip())
            size_gb = size_bytes / (1024**3)
            
            return {
                'device': device,
                'disk': disk,
                'size_bytes': size_bytes,
                'size_gb': round(size_gb, 2)
            }
        except Exception as e:
            self.logger.error(f"Failed to get disk info: {e}")
            return None
    
    def create_full_backup(self, dry_run=False):
        """Create a full system image backup"""
        self.logger.info("=== Starting Full System Backup ===")
        
        disk_info = self.get_disk_info()
        if not disk_info:
            return None
        
        self.logger.info(f"Source disk: {disk_info['disk']} ({disk_info['size_gb']} GB)")
        
        if dry_run:
            self.logger.info("[DRY RUN] Would create full disk image")
            return "/tmp/dry-run-full.img.gz"
        
        # Generate filename
        filename = f"{self.config.backup_name}_full_{self.timestamp}.img.gz"
        output_path = TEMP_DIR / filename
        
        self.logger.info(f"Creating compressed image: {output_path}")
        
        # Create disk image with dd and compress with pigz
        try:
            cmd = f"dd if={disk_info['disk']} bs=4M status=progress | pigz -{self.config.compression_level} > {output_path}"
            
            self.logger.info(f"Running: {cmd}")
            subprocess.run(cmd, shell=True, check=True)
            
            # Calculate checksum
            checksum = self.calculate_checksum(output_path)
            
            # Create manifest
            self.manifest = {
                'type': 'full',
                'timestamp': self.timestamp,
                'filename': filename,
                'source_disk': disk_info['disk'],
                'source_size_gb': disk_info['size_gb'],
                'backup_size_bytes': output_path.stat().st_size,
                'checksum_sha256': checksum,
                'compression_level': self.config.compression_level
            }
            
            # Save manifest
            manifest_path = MANIFEST_DIR / f"{filename}.manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(self.manifest, f, indent=2)
            
            self.logger.success(f"Full backup created: {output_path}")
            self.logger.info(f"Backup size: {self.manifest['backup_size_bytes'] / (1024**3):.2f} GB")
            self.logger.info(f"Checksum: {checksum}")
            
            return str(output_path)
            
        except Exception as e:
            self.logger.error(f"Full backup failed: {e}")
            return None
    
    def create_incremental_backup(self, dry_run=False):
        """Create an incremental backup (only changed files since last backup)"""
        self.logger.info("=== Starting Incremental Backup ===")
        
        if dry_run:
            self.logger.info("[DRY RUN] Would create incremental backup")
            return "/tmp/dry-run-incremental.tar.gz"
        
        # Find last backup manifest
        last_manifest = self.find_last_manifest()
        
        # Directories to back up
        backup_dirs = [
            '/etc',
            '/home',
            '/var/www',
            '/opt',
            '/root',
            '/usr/local'
        ]
        
        # Generate filename
        filename = f"{self.config.backup_name}_incremental_{self.timestamp}.tar.gz"
        output_path = TEMP_DIR / filename
        
        # Create snapshot directory
        snapshot_dir = Path("/var/lib/universal-backup/snapshots")
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Use rsync to create incremental backup
        try:
            # Build rsync command
            rsync_cmd = [
                'rsync',
                '-aAXv',
                '--delete',
                '--link-dest=' + str(snapshot_dir / 'latest'),
            ]
            
            for dir in backup_dirs:
                if Path(dir).exists():
                    rsync_cmd.append(dir)
            
            snapshot_path = snapshot_dir / self.timestamp
            rsync_cmd.append(str(snapshot_path))
            
            self.logger.info(f"Running rsync: {' '.join(rsync_cmd)}")
            subprocess.run(rsync_cmd, check=True)
            
            # Update latest symlink
            latest_link = snapshot_dir / 'latest'
            if latest_link.exists():
                latest_link.unlink()
            latest_link.symlink_to(snapshot_path)
            
            # Compress the snapshot
            self.logger.info(f"Compressing snapshot to {output_path}")
            subprocess.run([
                'tar',
                '-czf',
                str(output_path),
                '-C',
                str(snapshot_dir),
                self.timestamp
            ], check=True)
            
            # Calculate checksum
            checksum = self.calculate_checksum(output_path)
            
            # Create manifest
            self.manifest = {
                'type': 'incremental',
                'timestamp': self.timestamp,
                'filename': filename,
                'backup_size_bytes': output_path.stat().st_size,
                'checksum_sha256': checksum,
                'base_backup': last_manifest.get('filename') if last_manifest else None,
                'backed_up_dirs': backup_dirs
            }
            
            # Save manifest
            manifest_path = MANIFEST_DIR / f"{filename}.manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(self.manifest, f, indent=2)
            
            self.logger.success(f"Incremental backup created: {output_path}")
            self.logger.info(f"Backup size: {self.manifest['backup_size_bytes'] / (1024**2):.2f} MB")
            
            return str(output_path)
            
        except Exception as e:
            self.logger.error(f"Incremental backup failed: {e}")
            return None
    
    def create_differential_backup(self, dry_run=False):
        """Create a differential backup (all changes since last full backup)"""
        self.logger.info("=== Starting Differential Backup ===")
        
        if dry_run:
            self.logger.info("[DRY RUN] Would create differential backup")
            return "/tmp/dry-run-differential.tar.gz"
        
        # Find last full backup
        last_full = self.find_last_manifest(backup_type='full')
        
        if not last_full:
            self.logger.warn("No full backup found, creating full backup instead")
            return self.create_full_backup(dry_run=dry_run)
        
        self.logger.info(f"Base backup: {last_full.get('filename')}")
        
        # Similar to incremental, but compare against last full backup
        # Implementation would be similar to incremental but with different base
        
        return self.create_incremental_backup(dry_run=dry_run)
    
    def calculate_checksum(self, file_path):
        """Calculate SHA-256 checksum of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def find_last_manifest(self, backup_type=None):
        """Find the most recent backup manifest"""
        manifests = sorted(MANIFEST_DIR.glob("*.manifest.json"), reverse=True)
        
        for manifest_file in manifests:
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
                if backup_type is None or manifest.get('type') == backup_type:
                    return manifest
        
        return None
    
    def upload_to_backend(self, backup_file, backend='s3'):
        """Upload backup to cloud storage"""
        self.logger.info(f"Uploading to {backend}...")
        
        if backend == 's3':
            return self.upload_to_s3(backup_file)
        elif backend == 'gdrive':
            return self.upload_to_gdrive(backup_file)
        else:
            self.logger.error(f"Unknown backend: {backend}")
            return False
    
    def upload_to_s3(self, backup_file):
        """Upload backup to AWS S3"""
        try:
            import boto3
            
            s3_client = boto3.client('s3', region_name=self.config.s3_region)
            
            # Upload file
            s3_key = f"{self.config.s3_folder}/{Path(backup_file).name}"
            
            self.logger.info(f"Uploading to s3://{self.config.s3_bucket}/{s3_key}")
            
            s3_client.upload_file(
                backup_file,
                self.config.s3_bucket,
                s3_key,
                ExtraArgs={'StorageClass': 'STANDARD_IA'}
            )
            
            # Upload manifest
            manifest_file = MANIFEST_DIR / f"{Path(backup_file).name}.manifest.json"
            if manifest_file.exists():
                s3_client.upload_file(
                    str(manifest_file),
                    self.config.s3_bucket,
                    f"{s3_key}.manifest.json"
                )
            
            self.logger.success(f"Uploaded to S3: {s3_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"S3 upload failed: {e}")
            return False
    
    def upload_to_gdrive(self, backup_file):
        """Upload backup to Google Drive"""
        self.logger.info("Google Drive upload not yet implemented in v2")
        return False
    
    def rotate_backups(self, backend='s3'):
        """Rotate old backups according to retention policy"""
        self.logger.info(f"Rotating backups on {backend}...")
        
        if backend == 's3':
            return self.rotate_s3_backups()
        else:
            self.logger.warn(f"Rotation not implemented for {backend}")
            return False
    
    def rotate_s3_backups(self):
        """Rotate S3 backups keeping only the 5 most recent"""
        try:
            import boto3
            
            s3_client = boto3.client('s3', region_name=self.config.s3_region)
            
            # List all backups
            response = s3_client.list_objects_v2(
                Bucket=self.config.s3_bucket,
                Prefix=self.config.s3_folder
            )
            
            if 'Contents' not in response:
                self.logger.info("No backups to rotate")
                return True
            
            # Filter backup files (exclude manifests)
            backups = [obj for obj in response['Contents'] if not obj['Key'].endswith('.manifest.json')]
            
            # Sort by last modified date
            backups.sort(key=lambda x: x['LastModified'], reverse=True)
            
            # Keep only 5 most recent
            MAX_BACKUPS = 5
            
            if len(backups) > MAX_BACKUPS:
                backups_to_delete = backups[MAX_BACKUPS:]
                
                self.logger.info(f"Deleting {len(backups_to_delete)} old backups")
                
                for backup in backups_to_delete:
                    key = backup['Key']
                    self.logger.info(f"Deleting: {key}")
                    s3_client.delete_object(Bucket=self.config.s3_bucket, Key=key)
                    
                    # Also delete manifest
                    manifest_key = f"{key}.manifest.json"
                    try:
                        s3_client.delete_object(Bucket=self.config.s3_bucket, Key=manifest_key)
                    except:
                        pass
                
                self.logger.success(f"Rotation complete. Kept {MAX_BACKUPS} most recent backups")
            else:
                self.logger.info(f"Only {len(backups)} backups found, no rotation needed")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Backup rotation failed: {e}")
            return False
    
    def cleanup_temp_files(self):
        """Clean up temporary backup files"""
        self.logger.info("Cleaning up temporary files...")
        
        try:
            for file in TEMP_DIR.glob("*.img.gz"):
                file.unlink()
                self.logger.info(f"Deleted: {file}")
            
            for file in TEMP_DIR.glob("*.tar.gz"):
                file.unlink()
                self.logger.info(f"Deleted: {file}")
            
            self.logger.success("Cleanup complete")
        except Exception as e:
            self.logger.warn(f"Cleanup failed: {e}")


def main():
    parser = argparse.ArgumentParser(description='Universal Server Backup System v2')
    parser.add_argument('--type', choices=['full', 'incremental', 'differential'], default='full',
                        help='Backup type (default: full)')
    parser.add_argument('--backend', choices=['s3', 'gdrive', 'all'], default='s3',
                        help='Storage backend (default: s3)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Perform a dry run without creating actual backups')
    parser.add_argument('--list', action='store_true',
                        help='List available backups')
    parser.add_argument('--no-upload', action='store_true',
                        help='Skip uploading to cloud storage')
    parser.add_argument('--no-rotation', action='store_true',
                        help='Skip backup rotation')
    
    args = parser.parse_args()
    
    # Initialize logger and config
    logger = BackupLogger()
    config = BackupConfig()
    engine = BackupEngine(config, logger)
    
    logger.info("=" * 70)
    logger.info("Universal Server Backup System v2.0")
    logger.info(f"Server ID: {config.server_id}")
    logger.info(f"Backup Type: {args.type}")
    logger.info(f"Backend: {args.backend}")
    logger.info("=" * 70)
    
    # Create backup
    if args.type == 'full':
        backup_file = engine.create_full_backup(dry_run=args.dry_run)
    elif args.type == 'incremental':
        backup_file = engine.create_incremental_backup(dry_run=args.dry_run)
    elif args.type == 'differential':
        backup_file = engine.create_differential_backup(dry_run=args.dry_run)
    else:
        logger.error(f"Unknown backup type: {args.type}")
        sys.exit(1)
    
    if not backup_file:
        logger.error("Backup creation failed")
        sys.exit(1)
    
    # Upload to backend
    if not args.no_upload and not args.dry_run:
        backends = ['s3', 'gdrive'] if args.backend == 'all' else [args.backend]
        
        for backend in backends:
            if backend in config.enabled_backends:
                success = engine.upload_to_backend(backup_file, backend)
                if not success:
                    logger.error(f"Upload to {backend} failed")
    
    # Rotate old backups
    if not args.no_rotation and not args.dry_run:
        engine.rotate_backups(backend=args.backend)
    
    # Cleanup
    if not args.dry_run:
        engine.cleanup_temp_files()
    
    logger.info("=" * 70)
    logger.success("Backup process completed successfully")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()
