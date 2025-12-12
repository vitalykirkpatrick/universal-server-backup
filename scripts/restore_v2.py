#!/usr/bin/env python3
"""
Universal Server Backup System v2 - Enhanced Restore Script
Automated disaster recovery with guided restoration process

Usage:
    universal-restore --list --backend s3
    universal-restore --backend s3 --backup latest
    universal-restore --backend s3 --backup my-server_full_2025-12-12.img.gz --target /dev/sda
"""

import os
import sys
import argparse
import subprocess
import json
from datetime import datetime
from pathlib import Path
import configparser

# Configuration
CONFIG_FILE = "/etc/universal-backup/backup.conf"
LOG_DIR = Path("/var/log/universal-backup")
TEMP_DIR = Path("/tmp/universal-backup-restore")

# Ensure directories exist
LOG_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

class RestoreLogger:
    """Centralized logging system for restore operations"""
    
    def __init__(self, log_file=None):
        if log_file is None:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            log_file = LOG_DIR / f"restore_{timestamp}.log"
        
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


class RestoreConfig:
    """Configuration management for restore operations"""
    
    def __init__(self, config_file=CONFIG_FILE):
        self.config = configparser.ConfigParser()
        
        if Path(config_file).exists():
            self.config.read(config_file)
            self.server_id = self.config.get('general', 'server_id', fallback='unknown-server')
        else:
            # Running from live environment, use defaults
            self.server_id = 'unknown-server'
        
        # S3 settings
        self.s3_bucket = os.getenv('S3_BUCKET', self.config.get('s3', 'bucket_name', fallback='universal-backups'))
        self.s3_region = os.getenv('S3_REGION', self.config.get('s3', 'region', fallback='us-east-1'))
        self.s3_folder = os.getenv('S3_FOLDER', self.config.get('s3', 'folder', fallback=f'backups/{self.server_id}'))


class RestoreEngine:
    """Main restore engine for disaster recovery"""
    
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
    
    def list_backups_s3(self):
        """List available backups in S3"""
        try:
            import boto3
            
            s3_client = boto3.client('s3', region_name=self.config.s3_region)
            
            self.logger.info(f"Listing backups from s3://{self.config.s3_bucket}/{self.config.s3_folder}")
            
            response = s3_client.list_objects_v2(
                Bucket=self.config.s3_bucket,
                Prefix=self.config.s3_folder
            )
            
            if 'Contents' not in response:
                self.logger.warn("No backups found")
                return []
            
            # Filter backup files
            backups = []
            for obj in response['Contents']:
                key = obj['Key']
                if key.endswith('.img.gz') or key.endswith('.tar.gz'):
                    backups.append({
                        'key': key,
                        'filename': Path(key).name,
                        'size_gb': obj['Size'] / (1024**3),
                        'last_modified': obj['LastModified'].strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            # Sort by last modified
            backups.sort(key=lambda x: x['last_modified'], reverse=True)
            
            return backups
            
        except Exception as e:
            self.logger.error(f"Failed to list S3 backups: {e}")
            return []
    
    def download_from_s3(self, backup_key):
        """Download backup from S3"""
        try:
            import boto3
            
            s3_client = boto3.client('s3', region_name=self.config.s3_region)
            
            filename = Path(backup_key).name
            local_path = TEMP_DIR / filename
            
            self.logger.info(f"Downloading {backup_key} to {local_path}")
            
            # Download with progress
            s3_client.download_file(
                self.config.s3_bucket,
                backup_key,
                str(local_path)
            )
            
            # Download manifest if exists
            manifest_key = f"{backup_key}.manifest.json"
            manifest_path = TEMP_DIR / f"{filename}.manifest.json"
            
            try:
                s3_client.download_file(
                    self.config.s3_bucket,
                    manifest_key,
                    str(manifest_path)
                )
                self.logger.info(f"Downloaded manifest: {manifest_path}")
            except:
                self.logger.warn("No manifest found for this backup")
            
            self.logger.success(f"Downloaded: {local_path}")
            return str(local_path)
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return None
    
    def verify_backup(self, backup_file):
        """Verify backup integrity using checksum"""
        manifest_file = Path(f"{backup_file}.manifest.json")
        
        if not manifest_file.exists():
            self.logger.warn("No manifest file, skipping verification")
            return True
        
        try:
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
            
            expected_checksum = manifest.get('checksum_sha256')
            if not expected_checksum:
                self.logger.warn("No checksum in manifest")
                return True
            
            self.logger.info("Calculating checksum...")
            
            import hashlib
            sha256_hash = hashlib.sha256()
            with open(backup_file, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            actual_checksum = sha256_hash.hexdigest()
            
            if actual_checksum == expected_checksum:
                self.logger.success("✅ Checksum verified")
                return True
            else:
                self.logger.error("❌ Checksum mismatch!")
                self.logger.error(f"Expected: {expected_checksum}")
                self.logger.error(f"Actual: {actual_checksum}")
                return False
                
        except Exception as e:
            self.logger.error(f"Verification failed: {e}")
            return False
    
    def get_available_disks(self):
        """List available disks for restoration"""
        try:
            result = subprocess.run(
                ['lsblk', '-d', '-n', '-o', 'NAME,SIZE,TYPE'],
                capture_output=True,
                text=True,
                check=True
            )
            
            disks = []
            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 3 and parts[2] == 'disk':
                    disks.append({
                        'device': f"/dev/{parts[0]}",
                        'size': parts[1]
                    })
            
            return disks
            
        except Exception as e:
            self.logger.error(f"Failed to list disks: {e}")
            return []
    
    def restore_full_backup(self, backup_file, target_disk, dry_run=False):
        """Restore a full system image to target disk"""
        self.logger.info("=== Starting Full System Restore ===")
        self.logger.info(f"Backup file: {backup_file}")
        self.logger.info(f"Target disk: {target_disk}")
        
        if dry_run:
            self.logger.info("[DRY RUN] Would restore image to {target_disk}")
            return True
        
        # Confirm with user
        self.logger.warn("⚠️  WARNING: This will ERASE ALL DATA on {target_disk}!")
        response = input("Type 'YES' to continue: ")
        
        if response != 'YES':
            self.logger.info("Restore cancelled by user")
            return False
        
        try:
            # Decompress and write to disk
            cmd = f"pigz -dc {backup_file} | dd of={target_disk} bs=4M status=progress"
            
            self.logger.info(f"Running: {cmd}")
            subprocess.run(cmd, shell=True, check=True)
            
            # Sync filesystem
            self.logger.info("Syncing filesystem...")
            subprocess.run(['sync'], check=True)
            
            self.logger.success("✅ System image restored successfully")
            
            # Reinstall bootloader
            self.reinstall_bootloader(target_disk)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            return False
    
    def restore_incremental_backup(self, backup_file, dry_run=False):
        """Restore an incremental backup"""
        self.logger.info("=== Starting Incremental Restore ===")
        
        if dry_run:
            self.logger.info("[DRY RUN] Would restore incremental backup")
            return True
        
        try:
            # Extract to root
            cmd = f"tar -xzf {backup_file} -C /"
            
            self.logger.info(f"Running: {cmd}")
            subprocess.run(cmd, shell=True, check=True)
            
            self.logger.success("✅ Incremental backup restored successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            return False
    
    def reinstall_bootloader(self, target_disk):
        """Reinstall GRUB bootloader"""
        self.logger.info("Reinstalling bootloader...")
        
        try:
            # Mount the restored system
            mount_point = Path("/mnt/restored")
            mount_point.mkdir(parents=True, exist_ok=True)
            
            # Find root partition (usually partition 1)
            root_partition = f"{target_disk}1" if not target_disk.endswith('1') else target_disk
            
            subprocess.run(['mount', root_partition, str(mount_point)], check=True)
            
            # Bind mount necessary filesystems
            for fs in ['dev', 'proc', 'sys']:
                subprocess.run(['mount', '--bind', f'/{fs}', str(mount_point / fs)], check=True)
            
            # Install GRUB
            subprocess.run([
                'chroot', str(mount_point),
                'grub-install', target_disk
            ], check=True)
            
            # Update GRUB config
            subprocess.run([
                'chroot', str(mount_point),
                'update-grub'
            ], check=True)
            
            # Unmount
            for fs in ['sys', 'proc', 'dev']:
                subprocess.run(['umount', str(mount_point / fs)], check=False)
            
            subprocess.run(['umount', str(mount_point)], check=True)
            
            self.logger.success("✅ Bootloader reinstalled")
            
        except Exception as e:
            self.logger.warn(f"Bootloader installation failed: {e}")
            self.logger.warn("You may need to reinstall GRUB manually")
    
    def cleanup(self):
        """Clean up temporary files"""
        self.logger.info("Cleaning up temporary files...")
        
        try:
            import shutil
            shutil.rmtree(TEMP_DIR)
            self.logger.success("Cleanup complete")
        except Exception as e:
            self.logger.warn(f"Cleanup failed: {e}")


def main():
    parser = argparse.ArgumentParser(description='Universal Server Backup System v2 - Restore')
    parser.add_argument('--backend', choices=['s3', 'gdrive'], default='s3',
                        help='Storage backend (default: s3)')
    parser.add_argument('--list', action='store_true',
                        help='List available backups')
    parser.add_argument('--backup', type=str,
                        help='Backup filename or "latest" for most recent')
    parser.add_argument('--target', type=str,
                        help='Target disk for restoration (e.g., /dev/sda)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Perform a dry run without actual restoration')
    parser.add_argument('--no-verify', action='store_true',
                        help='Skip checksum verification')
    
    args = parser.parse_args()
    
    # Initialize logger and config
    logger = RestoreLogger()
    config = RestoreConfig()
    engine = RestoreEngine(config, logger)
    
    logger.info("=" * 70)
    logger.info("Universal Server Backup System v2 - Restore")
    logger.info(f"Backend: {args.backend}")
    logger.info("=" * 70)
    
    # List backups
    if args.list:
        if args.backend == 's3':
            backups = engine.list_backups_s3()
            
            if backups:
                logger.info(f"\nFound {len(backups)} backups:\n")
                print(f"{'Filename':<50} {'Size (GB)':<12} {'Last Modified'}")
                print("-" * 80)
                for backup in backups:
                    print(f"{backup['filename']:<50} {backup['size_gb']:<12.2f} {backup['last_modified']}")
            else:
                logger.warn("No backups found")
        
        return
    
    # Restore backup
    if not args.backup:
        logger.error("Please specify --backup or use --list to see available backups")
        sys.exit(1)
    
    # Get backup list
    if args.backend == 's3':
        backups = engine.list_backups_s3()
    else:
        logger.error(f"Backend {args.backend} not yet implemented")
        sys.exit(1)
    
    if not backups:
        logger.error("No backups available")
        sys.exit(1)
    
    # Select backup
    if args.backup == 'latest':
        selected_backup = backups[0]
        logger.info(f"Selected latest backup: {selected_backup['filename']}")
    else:
        # Find backup by filename
        selected_backup = next((b for b in backups if b['filename'] == args.backup), None)
        if not selected_backup:
            logger.error(f"Backup not found: {args.backup}")
            sys.exit(1)
    
    # Download backup
    backup_file = engine.download_from_s3(selected_backup['key'])
    if not backup_file:
        logger.error("Download failed")
        sys.exit(1)
    
    # Verify backup
    if not args.no_verify:
        if not engine.verify_backup(backup_file):
            logger.error("Backup verification failed")
            sys.exit(1)
    
    # Determine backup type
    is_full_backup = 'full' in selected_backup['filename'] or selected_backup['filename'].endswith('.img.gz')
    
    if is_full_backup:
        # Full backup restoration
        if not args.target:
            # List available disks
            disks = engine.get_available_disks()
            logger.info("\nAvailable disks:")
            for disk in disks:
                print(f"  {disk['device']} ({disk['size']})")
            
            logger.error("\nPlease specify --target disk for restoration")
            sys.exit(1)
        
        success = engine.restore_full_backup(backup_file, args.target, dry_run=args.dry_run)
    else:
        # Incremental/differential backup restoration
        success = engine.restore_incremental_backup(backup_file, dry_run=args.dry_run)
    
    # Cleanup
    if not args.dry_run:
        engine.cleanup()
    
    if success:
        logger.info("=" * 70)
        logger.success("Restore process completed successfully")
        logger.info("=" * 70)
        logger.info("\nNext steps:")
        logger.info("1. Reboot the system")
        logger.info("2. Verify all services are running")
        logger.info("3. Check network configuration")
    else:
        logger.error("Restore process failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
