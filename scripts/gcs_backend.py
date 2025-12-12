#!/usr/bin/env python3
"""
Google Cloud Storage (GCS) Backend for Universal Server Backup
Handles uploads and downloads to/from Google Cloud Storage
"""

import os
import sys
import json
from pathlib import Path
from google.cloud import storage
from google.oauth2 import service_account

class GCSBackend:
    def __init__(self, config):
        """Initialize GCS backend"""
        self.config = config
        self.bucket_name = config.get('gcs', {}).get('bucket_name', 'server-backups')
        self.storage_class = config.get('gcs', {}).get('storage_class', 'NEARLINE')
        self.folder = config.get('gcs', {}).get('folder', 'backups')
        
        # Initialize GCS client
        try:
            # Get service account credentials from environment or file
            creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            creds_file = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            
            if creds_json:
                # Parse JSON from environment variable
                creds_dict = json.loads(creds_json)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
            elif creds_file and os.path.exists(creds_file):
                # Load from file
                credentials = service_account.Credentials.from_service_account_file(creds_file)
            else:
                print("ERROR: Google Cloud Storage credentials not found")
                print("Set GOOGLE_APPLICATION_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS")
                sys.exit(1)
            
            # Create storage client
            self.client = storage.Client(credentials=credentials, project=credentials.project_id)
            
            # Ensure bucket exists
            self._ensure_bucket_exists()
            
        except Exception as e:
            print(f"Failed to initialize Google Cloud Storage: {e}")
            sys.exit(1)
    
    def _ensure_bucket_exists(self):
        """Ensure GCS bucket exists"""
        try:
            self.bucket = self.client.bucket(self.bucket_name)
            
            if not self.bucket.exists():
                # Create bucket
                self.bucket = self.client.create_bucket(
                    self.bucket_name,
                    location='US'
                )
                print(f"Created GCS bucket: {self.bucket_name}")
            else:
                print(f"Using existing GCS bucket: {self.bucket_name}")
                
        except Exception as e:
            print(f"Error accessing GCS bucket: {e}")
            raise
    
    def upload(self, local_path, remote_name=None, folder=None):
        """Upload file to GCS"""
        if not remote_name:
            remote_name = Path(local_path).name
        
        if not folder:
            folder = self.folder
        
        blob_name = f"{folder}/{remote_name}"
        
        try:
            print(f"   Uploading to GCS: gs://{self.bucket_name}/{blob_name}")
            
            # Get file size
            file_size = Path(local_path).stat().st_size
            
            # Create blob
            blob = self.bucket.blob(blob_name)
            
            # Set storage class
            blob.storage_class = self.storage_class
            
            # Upload with progress
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            
            with open(local_path, 'rb') as f:
                total_uploaded = 0
                blob.chunk_size = chunk_size
                
                # Upload file
                blob.upload_from_file(f, rewind=True)
                
                print(f"   ✅ Upload complete: gs://{self.bucket_name}/{blob_name}")
            
            return True
            
        except Exception as e:
            print(f"   ❌ GCS upload failed: {e}")
            return False
    
    def download(self, remote_name, local_path, folder=None):
        """Download file from GCS"""
        if not folder:
            folder = self.folder
        
        blob_name = f"{folder}/{remote_name}"
        
        try:
            print(f"   Downloading from GCS: gs://{self.bucket_name}/{blob_name}")
            
            # Get blob
            blob = self.bucket.blob(blob_name)
            
            if not blob.exists():
                print(f"   ❌ File not found: {blob_name}")
                return False
            
            # Download with progress
            blob.download_to_filename(str(local_path))
            
            print(f"   ✅ Download complete: {local_path}")
            return True
            
        except Exception as e:
            print(f"   ❌ GCS download failed: {e}")
            return False
    
    def list_backups(self, folder=None):
        """List available backups in GCS"""
        if not folder:
            folder = self.folder
        
        try:
            prefix = f"{folder}/"
            blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
            
            backups = []
            for blob in blobs:
                if blob.name.endswith('.img.gz'):
                    backups.append({
                        'name': Path(blob.name).name,
                        'size': blob.size,
                        'modified': blob.updated,
                        'storage_class': blob.storage_class,
                        'blob_name': blob.name
                    })
            
            return sorted(backups, key=lambda x: x['modified'], reverse=True)
            
        except Exception as e:
            print(f"Error listing GCS backups: {e}")
            return []
    
    def delete_backup(self, remote_name, folder=None):
        """Delete backup from GCS"""
        if not folder:
            folder = self.folder
        
        blob_name = f"{folder}/{remote_name}"
        
        try:
            # Delete backup
            blob = self.bucket.blob(blob_name)
            blob.delete()
            
            # Also delete manifest if exists
            manifest_blob = self.bucket.blob(f"{blob_name}.manifest.json")
            if manifest_blob.exists():
                manifest_blob.delete()
            
            print(f"   ✅ Deleted from GCS: {remote_name}")
            return True
            
        except Exception as e:
            print(f"   ❌ GCS delete failed: {e}")
            return False
    
    def get_manifest(self, remote_name, folder=None):
        """Get backup manifest from GCS"""
        if not folder:
            folder = self.folder
        
        manifest_blob_name = f"{folder}/{remote_name}.manifest.json"
        
        try:
            blob = self.bucket.blob(manifest_blob_name)
            
            if not blob.exists():
                return None
            
            content = blob.download_as_text()
            manifest = json.loads(content)
            return manifest
            
        except Exception:
            return None
