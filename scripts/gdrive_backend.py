#!/usr/bin/env python3
"""
Google Drive Backend for Universal Server Backup
Handles uploads and downloads to/from Google Drive API
"""

import os
import sys
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

class GDriveBackend:
    def __init__(self, config):
        """Initialize Google Drive backend"""
        self.config = config
        self.folder_name = config.get('gdrive', {}).get('folder_name', 'ServerBackups')
        self.shared_drive_id = config.get('gdrive', {}).get('shared_drive_id')
        
        # Initialize Google Drive API
        self.service = self._initialize_service()
        self.folder_id = self._get_or_create_folder()
    
    def _initialize_service(self):
        """Initialize Google Drive API service"""
        try:
            # Get credentials from environment
            refresh_token = os.environ.get('GOOGLE_DRIVE_REFRESH_TOKEN')
            access_token = os.environ.get('GOOGLE_DRIVE_ACCESS_TOKEN')
            client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
            client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
            
            if not all([refresh_token, client_id, client_secret]):
                print("ERROR: Google Drive credentials not found in environment")
                print("Required: GOOGLE_DRIVE_REFRESH_TOKEN, GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET")
                sys.exit(1)
            
            # Create credentials object
            creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=client_id,
                client_secret=client_secret,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            
            # Build service
            service = build('drive', 'v3', credentials=creds)
            return service
            
        except Exception as e:
            print(f"Failed to initialize Google Drive API: {e}")
            sys.exit(1)
    
    def _get_or_create_folder(self):
        """Get or create backup folder in Google Drive"""
        try:
            # Search for folder
            query = f"name='{self.folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                folder_id = files[0]['id']
                print(f"Using existing Google Drive folder: {self.folder_name} ({folder_id})")
                return folder_id
            else:
                # Create folder
                file_metadata = {
                    'name': self.folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                folder = self.service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                
                folder_id = folder.get('id')
                print(f"Created Google Drive folder: {self.folder_name} ({folder_id})")
                return folder_id
                
        except HttpError as e:
            print(f"Error accessing Google Drive: {e}")
            sys.exit(1)
    
    def upload(self, local_path, remote_name=None):
        """Upload file to Google Drive"""
        if not remote_name:
            remote_name = Path(local_path).name
        
        try:
            print(f"   Uploading to Google Drive: {remote_name}")
            
            # Check if file already exists
            query = f"name='{remote_name}' and '{self.folder_id}' in parents and trashed=false"
            results = self.service.files().list(q=query, fields='files(id)').execute()
            existing_files = results.get('files', [])
            
            # Prepare file metadata
            file_metadata = {
                'name': remote_name,
                'parents': [self.folder_id]
            }
            
            # Create media upload
            media = MediaFileUpload(
                str(local_path),
                resumable=True,
                chunksize=10*1024*1024  # 10MB chunks
            )
            
            if existing_files:
                # Update existing file
                file_id = existing_files[0]['id']
                request = self.service.files().update(
                    fileId=file_id,
                    media_body=media
                )
            else:
                # Create new file
                request = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                )
            
            # Upload with progress
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    sys.stdout.write(f"\r   Uploaded: {progress}%")
                    sys.stdout.flush()
            
            sys.stdout.write("\n")
            print(f"   ✅ Upload complete: {remote_name}")
            return True
            
        except HttpError as e:
            print(f"   ❌ Google Drive upload failed: {e}")
            return False
        except Exception as e:
            print(f"   ❌ Upload error: {e}")
            return False
    
    def download(self, remote_name, local_path):
        """Download file from Google Drive"""
        try:
            print(f"   Downloading from Google Drive: {remote_name}")
            
            # Find file
            query = f"name='{remote_name}' and '{self.folder_id}' in parents and trashed=false"
            results = self.service.files().list(q=query, fields='files(id, size)').execute()
            files = results.get('files', [])
            
            if not files:
                print(f"   ❌ File not found: {remote_name}")
                return False
            
            file_id = files[0]['id']
            file_size = int(files[0].get('size', 0))
            
            # Download file
            request = self.service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request, chunksize=10*1024*1024)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        sys.stdout.write(f"\r   Downloaded: {progress}%")
                        sys.stdout.flush()
            
            sys.stdout.write("\n")
            print(f"   ✅ Download complete: {local_path}")
            return True
            
        except HttpError as e:
            print(f"   ❌ Google Drive download failed: {e}")
            return False
        except Exception as e:
            print(f"   ❌ Download error: {e}")
            return False
    
    def list_backups(self):
        """List available backups in Google Drive"""
        try:
            query = f"'{self.folder_id}' in parents and trashed=false and name contains '.img.gz'"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, size, modifiedTime)',
                orderBy='modifiedTime desc'
            ).execute()
            
            files = results.get('files', [])
            
            backups = []
            for file in files:
                backups.append({
                    'name': file['name'],
                    'size': int(file.get('size', 0)),
                    'modified': file['modifiedTime'],
                    'id': file['id']
                })
            
            return backups
            
        except HttpError as e:
            print(f"Error listing Google Drive backups: {e}")
            return []
    
    def delete_backup(self, remote_name):
        """Delete backup from Google Drive"""
        try:
            # Find file
            query = f"name='{remote_name}' and '{self.folder_id}' in parents and trashed=false"
            results = self.service.files().list(q=query, fields='files(id)').execute()
            files = results.get('files', [])
            
            if not files:
                print(f"   ⚠️  File not found: {remote_name}")
                return False
            
            file_id = files[0]['id']
            
            # Delete file
            self.service.files().delete(fileId=file_id).execute()
            
            # Also delete manifest if exists
            manifest_name = f"{remote_name}.manifest.json"
            query = f"name='{manifest_name}' and '{self.folder_id}' in parents and trashed=false"
            results = self.service.files().list(q=query, fields='files(id)').execute()
            manifest_files = results.get('files', [])
            
            if manifest_files:
                self.service.files().delete(fileId=manifest_files[0]['id']).execute()
            
            print(f"   ✅ Deleted from Google Drive: {remote_name}")
            return True
            
        except HttpError as e:
            print(f"   ❌ Google Drive delete failed: {e}")
            return False
    
    def get_manifest(self, remote_name):
        """Get backup manifest from Google Drive"""
        manifest_name = f"{remote_name}.manifest.json"
        
        try:
            # Find manifest file
            query = f"name='{manifest_name}' and '{self.folder_id}' in parents and trashed=false"
            results = self.service.files().list(q=query, fields='files(id)').execute()
            files = results.get('files', [])
            
            if not files:
                return None
            
            file_id = files[0]['id']
            
            # Download manifest content
            request = self.service.files().get_media(fileId=file_id)
            content = request.execute()
            
            manifest = json.loads(content.decode('utf-8'))
            return manifest
            
        except Exception:
            return None
