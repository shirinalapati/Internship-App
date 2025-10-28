import boto3
import os
import uuid
from datetime import datetime
from typing import Optional, Tuple
from botocore.exceptions import ClientError, NoCredentialsError
import io

class S3Service:
    def __init__(self):
        """Initialize S3 client with credentials from environment variables"""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
            self.bucket_name = os.getenv('AWS_BUCKET_NAME')
            
            if not self.bucket_name:
                raise ValueError("AWS_BUCKET_NAME environment variable is required")
                
            # Test connection
            self._test_connection()
            print(f"✅ S3 service initialized successfully with bucket: {self.bucket_name}")
            
        except Exception as e:
            print(f"❌ Failed to initialize S3 service: {e}")
            raise

    def _test_connection(self):
        """Test S3 connection and bucket access"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                raise Exception(f"S3 bucket '{self.bucket_name}' does not exist")
            elif error_code == '403':
                raise Exception(f"Access denied to S3 bucket '{self.bucket_name}'. Check your AWS credentials and permissions.")
            else:
                raise Exception(f"S3 connection error: {e}")

    def generate_s3_key(self, filename: str, user_id: Optional[str] = None) -> str:
        """Generate a unique S3 key for the file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        # Clean filename to be S3-safe
        clean_filename = "".join(c for c in filename if c.isalnum() or c in '._-')
        
        if user_id:
            return f"resumes/{user_id}/{timestamp}_{unique_id}_{clean_filename}"
        else:
            return f"resumes/anonymous/{timestamp}_{unique_id}_{clean_filename}"

    def upload_file_to_s3(self, file_content: bytes, filename: str, user_id: Optional[str] = None) -> str:
        """
        Upload file content to S3 and return the S3 key
        
        Args:
            file_content: The file content as bytes
            filename: Original filename for reference
            user_id: Optional user ID for organizing files
            
        Returns:
            str: The S3 key of the uploaded file
        """
        try:
            s3_key = self.generate_s3_key(filename, user_id)
            
            # Determine content type based on file extension
            content_type = self._get_content_type(filename)
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    'original_filename': filename,
                    'upload_timestamp': datetime.now().isoformat(),
                    'user_id': user_id or 'anonymous'
                }
            )
            
            print(f"📤 Uploaded file to S3: {s3_key}")
            return s3_key
            
        except Exception as e:
            print(f"❌ Failed to upload file to S3: {e}")
            raise Exception(f"S3 upload failed: {str(e)}")

    def download_file_from_s3(self, s3_key: str) -> Tuple[bytes, str]:
        """
        Download file content from S3
        
        Args:
            s3_key: The S3 key of the file to download
            
        Returns:
            Tuple[bytes, str]: File content as bytes and original filename
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            file_content = response['Body'].read()
            
            # Get original filename from metadata
            original_filename = response.get('Metadata', {}).get('original_filename', 'resume.pdf')
            
            print(f"📥 Downloaded file from S3: {s3_key} ({len(file_content)} bytes)")
            return file_content, original_filename
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise Exception(f"File not found in S3: {s3_key}")
            else:
                raise Exception(f"S3 download error: {e}")
        except Exception as e:
            print(f"❌ Failed to download file from S3: {e}")
            raise Exception(f"S3 download failed: {str(e)}")

    def delete_file_from_s3(self, s3_key: str) -> bool:
        """
        Delete file from S3
        
        Args:
            s3_key: The S3 key of the file to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            print(f"🗑️ Deleted file from S3: {s3_key}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to delete file from S3: {e}")
            return False

    def _get_content_type(self, filename: str) -> str:
        """Determine content type based on file extension"""
        extension = filename.lower().split('.')[-1] if '.' in filename else ''
        
        content_types = {
            'pdf': 'application/pdf',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'txt': 'text/plain',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        
        return content_types.get(extension, 'application/octet-stream')

    def get_file_info(self, s3_key: str) -> dict:
        """Get metadata about a file in S3"""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return {
                'size': response['ContentLength'],
                'last_modified': response['LastModified'],
                'content_type': response['ContentType'],
                'metadata': response.get('Metadata', {})
            }
        except Exception as e:
            print(f"❌ Failed to get file info from S3: {e}")
            return {}

# Global S3 service instance
s3_service = None

def get_s3_service() -> S3Service:
    """Get or create S3 service instance"""
    global s3_service
    if s3_service is None:
        s3_service = S3Service()
    return s3_service

def upload_resume_to_s3(file_content: bytes, filename: str, user_id: Optional[str] = None) -> str:
    """Convenience function to upload resume to S3"""
    service = get_s3_service()
    return service.upload_file_to_s3(file_content, filename, user_id)

def download_resume_from_s3(s3_key: str) -> Tuple[bytes, str]:
    """Convenience function to download resume from S3"""
    service = get_s3_service()
    return service.download_file_from_s3(s3_key)

def delete_resume_from_s3(s3_key: str) -> bool:
    """Convenience function to delete resume from S3"""
    service = get_s3_service()
    return service.delete_file_from_s3(s3_key)