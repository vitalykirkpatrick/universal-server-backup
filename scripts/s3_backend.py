#!/usr/bin/env python3
"""
AWS S3 Backend for Universal Server Backup
Handles uploads and downloads to/from Amazon S3
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path

class S3Backend:
    def __init__(self, config):
        """Initialize S3 backend"""
        self.config = config
        self.bucket_name = config.get('s3', {}).get('bucket_name')
        self.region = config.get('s3', {}).get('region', 'us-east-1')
        self.storage_class = config.get('s3', {}).get('storage_class', 'STANDARD_IA')
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                region_name=self.region
            )
            
            # Ensure bucket exists
            self._ensure_bucket_exists()
            
        except NoCredentialsError:
            print("ERROR: AWS credentials not found in environment")
            print("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            sys.exit(1)
    
    def _ensure_bucket_exists(self):
        """Ensure S3 bucket exists"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket doesn't exist, create it
                try:
                    if self.region == 'us-east-1':
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    print(f"Created S3 bucket: {self.bucket_name}")
                except ClientError as create_error:
                    print(f"Failed to create bucket: {create_error}")
                    raise
    
    def upload(self, local_path, remote_name=None, folder="backups"):
        """Upload file to S3"""
        if not remote_name:
            remote_name = Path(local_path).name
        
        s3_key = f"{folder}/{remote_name}"
        
        try:
            print(f"   Uploading to S3: s3://{self.bucket_name}/{s3_key}")
            
            # Get file size for progress
            file_size = Path(local_path).stat().st_size
            
            # Upload with progress callback
            self.s3_client.upload_file(
                str(local_path),
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    'StorageClass': self.storage_class,
                    'Metadata': {
                        'uploaded_by': 'universal-backup',
                        'hostname': os.uname().nodename
                    }
                },
                Callback=ProgressPercentage(local_path, file_size)
            )
            
            print(f"   ✅ Upload complete: s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            print(f"   ❌ S3 upload failed: {e}")
            return False
    
    def download(self, remote_name, local_path, folder="backups"):
        """Download file from S3"""
        s3_key = f"{folder}/{remote_name}"
        
        try:
            print(f"   Downloading from S3: s3://{self.bucket_name}/{s3_key}")
            
            # Get file size
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            file_size = response['ContentLength']
            
            # Download with progress
            self.s3_client.download_file(
                self.bucket_name,
                s3_key,
                str(local_path),
                Callback=ProgressPercentage(local_path, file_size, download=True)
            )
            
            print(f"   ✅ Download complete: {local_path}")
            return True
            
        except ClientError as e:
            print(f"   ❌ S3 download failed: {e}")
            return False
    
    def list_backups(self, folder="backups"):
        """List available backups in S3"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{folder}/"
            )
            
            if 'Contents' not in response:
                return []
            
            backups = []
            for obj in response['Contents']:
                key = obj['Key']
                if key.endswith('.img.gz'):
                    backups.append({
                        'name': Path(key).name,
                        'size': obj['Size'],
                        'modified': obj['LastModified'],
                        'storage_class': obj.get('StorageClass', 'STANDARD'),
                        'key': key
                    })
            
            return sorted(backups, key=lambda x: x['modified'], reverse=True)
            
        except ClientError as e:
            print(f"Error listing S3 backups: {e}")
            return []
    
    def delete_backup(self, remote_name, folder="backups"):
        """Delete backup from S3"""
        s3_key = f"{folder}/{remote_name}"
        
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            
            # Also delete manifest if exists
            manifest_key = f"{s3_key}.manifest.json"
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=manifest_key)
            
            print(f"   ✅ Deleted from S3: {remote_name}")
            return True
            
        except ClientError as e:
            print(f"   ❌ S3 delete failed: {e}")
            return False
    
    def get_manifest(self, remote_name, folder="backups"):
        """Get backup manifest from S3"""
        manifest_key = f"{folder}/{remote_name}.manifest.json"
        
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=manifest_key)
            import json
            manifest = json.loads(response['Body'].read().decode('utf-8'))
            return manifest
            
        except ClientError:
            return None

class ProgressPercentage:
    """Progress callback for S3 uploads/downloads"""
    def __init__(self, filename, size, download=False):
        self._filename = filename
        self._size = size
        self._seen_so_far = 0
        self._download = download
    
    def __call__(self, bytes_amount):
        self._seen_so_far += bytes_amount
        percentage = (self._seen_so_far / self._size) * 100
        action = "Downloaded" if self._download else "Uploaded"
        sys.stdout.write(
            f"\r   {action}: {self._seen_so_far}/{self._size} bytes ({percentage:.1f}%)"
        )
        sys.stdout.flush()
        if self._seen_so_far >= self._size:
            sys.stdout.write("\n")
