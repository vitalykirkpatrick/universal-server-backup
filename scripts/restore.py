#!/usr/bin/env python3
"""
Universal Server Backup System - Restoration Script
Restores full system images from Google Drive or AWS S3

Usage:
    python3 restore.py --list --backend s3
    python3 restore.py --backend s3 --backup latest
    python3 restore.py --backend gdrive --backup "server_full_2024-12-12_02-00-00.img.gz"
    python3 restore.py --backend s3 --backup latest --target /dev/sdb
"""

import os
import sys
import argparse
import subprocess
import json
from datetime import datetime
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from s3_backend import S3Backend
    from gdrive_backend import GDriveBackend
    from gcs_backend import GCSBackend
    from utils import (
        load_config, log_message, format_size, verify_checksum
    )
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure all required scripts are in the scripts/ directory")
    sys.exit(1)

class SystemRestore:
    def __init__(self, config_path="/etc/universal-backup/backup.conf"):
        """Initialize restoration system"""
        try:
            self.config = load_config(config_path)
        except:
            # If config not found, use minimal config for restore
            self.config = {
                'backends': {'enabled': 's3,gdrive'},
                's3': {'bucket_name': 'default-backups', 'region': 'us-east-1'},
                'gdrive': {'folder_name': 'ServerBackups'}
            }
        
        self.temp_dir = Path("/tmp/universal-restore")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize backends
        self.backends = {}
        
    def _init_backend(self, backend_name):
        """Initialize specific backend"""
        if backend_name in self.backends:
            return self.backends[backend_name]
        
        try:
            if backend_name == 's3':
                self.backends['s3'] = S3Backend(self.config)
            elif backend_name == 'gdrive':
                self.backends['gdrive'] = GDriveBackend(self.config)
            elif backend_name == 'gcs':
                self.backends['gcs'] = GCSBackend(self.config)
            else:
                print(f"Unknown backend: {backend_name}")
                return None
            
            return self.backends[backend_name]
            
        except Exception as e:
            print(f"Failed to initialize {backend_name} backend: {e}")
            return None
    
    def list_backups(self, backend_name):
        """List available backups"""
        log_message("INFO", f"Listing backups from {backend_name.upper()}...")
        
        backend = self._init_backend(backend_name)
        if not backend:
            return []
        
        backups = backend.list_backups()
        
        if not backups:
            print(f"\nNo backups found in {backend_name.upper()}")
            return []
        
        print(f"\n{'='*80}")
        print(f"AVAILABLE BACKUPS - {backend_name.upper()}")
        print(f"{'='*80}")
        
        for i, backup in enumerate(backups, 1):
            print(f"\n{i}. {backup['name']}")
            print(f"   Size: {format_size(backup['size'])}")
            print(f"   Modified: {backup['modified']}")
            
            # Try to get manifest
            manifest = backend.get_manifest(backup['name'])
            if manifest:
                print(f"   Hostname: {manifest.get('hostname', 'N/A')}")
                print(f"   Disk: {manifest.get('source_disk', 'N/A')} ({manifest.get('disk_size_gb', 'N/A')} GB)")
                print(f"   Checksum: {manifest.get('checksum_sha256', 'N/A')[:16]}...")
        
        print(f"{'='*80}\n")
        
        return backups
    
    def download_backup(self, backend_name, backup_name):
        """Download backup from cloud storage"""
        log_message("INFO", f"Downloading backup from {backend_name.upper()}...")
        
        backend = self._init_backend(backend_name)
        if not backend:
            return None
        
        # If backup_name is 'latest', get the most recent
        if backup_name == 'latest':
            backups = backend.list_backups()
            if not backups:
                log_message("ERROR", "No backups found")
                return None
            backup_name = backups[0]['name']
            log_message("INFO", f"Latest backup: {backup_name}")
        
        # Download backup
        local_path = self.temp_dir / backup_name
        
        success = backend.download(backup_name, local_path)
        
        if not success:
            log_message("ERROR", "Download failed")
            return None
        
        # Download manifest
        manifest_name = f"{backup_name}.manifest.json"
        manifest_path = self.temp_dir / manifest_name
        
        try:
            backend.download(manifest_name, manifest_path)
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            return {
                'image_path': local_path,
                'manifest': manifest
            }
        except:
            log_message("WARN", "Could not download manifest")
            return {
                'image_path': local_path,
                'manifest': None
            }
    
    def verify_backup(self, image_path, manifest):
        """Verify backup integrity"""
        if not manifest:
            log_message("WARN", "No manifest available, skipping verification")
            return True
        
        expected_checksum = manifest.get('checksum_sha256')
        if not expected_checksum:
            log_message("WARN", "No checksum in manifest, skipping verification")
            return True
        
        log_message("INFO", "Verifying backup integrity...")
        return verify_checksum(image_path, expected_checksum)
    
    def restore_image(self, image_path, target_disk, verify_only=False):
        """Restore system image to disk"""
        if verify_only:
            log_message("INFO", "Verify-only mode, skipping restoration")
            return True
        
        log_message("INFO", f"Restoring image to {target_disk}...")
        
        # Confirm with user
        print("\n" + "="*80)
        print("⚠️  WARNING: THIS WILL COMPLETELY OVERWRITE THE TARGET DISK!")
        print("="*80)
        print(f"Source: {image_path}")
        print(f"Target: {target_disk}")
        print(f"Size: {format_size(image_path.stat().st_size)}")
        print("="*80)
        print("\nType 'YES' to continue, or anything else to cancel:")
        
        confirmation = input("> ").strip()
        
        if confirmation != "YES":
            log_message("INFO", "Restoration cancelled by user")
            return False
        
        log_message("INFO", "Starting restoration...")
        
        # Determine decompression tool
        try:
            subprocess.run(['which', 'pigz'], check=True, capture_output=True)
            decompressor = 'pigz'
        except:
            log_message("WARN", "pigz not found, using gzip (slower)")
            decompressor = 'gzip'
        
        # Restore with dd
        cmd = f"{decompressor} -dc {image_path} | dd of={target_disk} bs=4M status=progress"
        
        log_message("INFO", f"Running: {cmd}")
        log_message("INFO", "This may take several hours...")
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                check=True,
                stderr=subprocess.PIPE,
                text=True
            )
            
            log_message("INFO", "✅ Restoration completed successfully")
            
            # Sync to ensure all data is written
            log_message("INFO", "Syncing filesystem...")
            subprocess.run(['sync'], check=True)
            
            return True
            
        except subprocess.CalledProcessError as e:
            log_message("ERROR", f"Restoration failed: {e.stderr}")
            return False
    
    def cleanup(self):
        """Clean up temporary files"""
        log_message("INFO", "Cleaning up temporary files...")
        
        for file in self.temp_dir.glob("*"):
            try:
                file.unlink()
                log_message("INFO", f"Removed: {file}")
            except Exception as e:
                log_message("WARN", f"Could not remove {file}: {e}")
    
    def run_restore(self, backend_name, backup_name, target_disk=None, verify_only=False):
        """Run complete restoration process"""
        log_message("INFO", "="*70)
        log_message("INFO", "UNIVERSAL SERVER RESTORE - STARTING")
        log_message("INFO", "="*70)
        log_message("INFO", f"Backend: {backend_name.upper()}")
        log_message("INFO", f"Backup: {backup_name}")
        if target_disk:
            log_message("INFO", f"Target: {target_disk}")
        log_message("INFO", "="*70)
        
        try:
            # Download backup
            backup_data = self.download_backup(backend_name, backup_name)
            
            if not backup_data:
                log_message("ERROR", "Failed to download backup")
                return False
            
            image_path = backup_data['image_path']
            manifest = backup_data['manifest']
            
            # Verify backup
            if not self.verify_backup(image_path, manifest):
                log_message("ERROR", "Backup verification failed")
                return False
            
            # Determine target disk
            if not target_disk:
                if manifest and manifest.get('source_disk'):
                    target_disk = manifest['source_disk']
                    log_message("INFO", f"Using disk from manifest: {target_disk}")
                else:
                    target_disk = '/dev/sda'
                    log_message("WARN", f"No target specified, using default: {target_disk}")
            
            # Restore image
            success = self.restore_image(image_path, target_disk, verify_only=verify_only)
            
            # Cleanup
            if not verify_only:
                self.cleanup()
            
            if success:
                log_message("INFO", "="*70)
                log_message("INFO", "✅ RESTORATION COMPLETED SUCCESSFULLY")
                log_message("INFO", "="*70)
                if not verify_only:
                    print("\n🎉 System restored successfully!")
                    print("Remove the Live USB and reboot to start the restored system.")
                    print("\nReboot now? (y/n):")
                    if input("> ").strip().lower() == 'y':
                        subprocess.run(['reboot'])
                return True
            else:
                log_message("ERROR", "="*70)
                log_message("ERROR", "❌ RESTORATION FAILED")
                log_message("ERROR", "="*70)
                return False
                
        except Exception as e:
            log_message("ERROR", f"Restoration failed with exception: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(
        description='Universal Server Restore System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available backups
  python3 restore.py --list --backend s3
  python3 restore.py --list --backend gdrive
  
  # Restore latest backup
  python3 restore.py --backend s3 --backup latest
  
  # Restore specific backup
  python3 restore.py --backend s3 --backup "server_full_2024-12-12_02-00-00.img.gz"
  
  # Restore to specific disk
  python3 restore.py --backend s3 --backup latest --target /dev/sdb
  
  # Verify backup without restoring
  python3 restore.py --backend s3 --backup latest --verify-only
        """
    )
    
    parser.add_argument(
        '--backend',
        choices=['s3', 'gdrive', 'gcs'],
        required=True,
        help='Backup backend to use'
    )
    parser.add_argument(
        '--backup',
        help='Backup name or "latest"'
    )
    parser.add_argument(
        '--target',
        help='Target disk (e.g., /dev/sda)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available backups'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Verify backup integrity without restoring'
    )
    parser.add_argument(
        '--config',
        default='/etc/universal-backup/backup.conf',
        help='Path to configuration file'
    )
    
    args = parser.parse_args()
    
    # Initialize restore system
    restore = SystemRestore(config_path=args.config)
    
    # List backups
    if args.list:
        restore.list_backups(args.backend)
        sys.exit(0)
    
    # Restore backup
    if not args.backup:
        print("Error: --backup is required (use --list to see available backups)")
        sys.exit(1)
    
    # Check if running as root (unless verify-only)
    if os.geteuid() != 0 and not args.verify_only:
        print("Error: This script must be run as root (use sudo)")
        sys.exit(1)
    
    success = restore.run_restore(
        args.backend,
        args.backup,
        target_disk=args.target,
        verify_only=args.verify_only
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
