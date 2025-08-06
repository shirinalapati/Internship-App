from fastapi import Request, HTTPException
from datetime import datetime, timedelta
import uuid
import json
import os

# Simple in-memory session store (in production, use Redis or database)
sessions = {}

class SessionManager:
    def __init__(self):
        self.sessions = {}
    
    def create_session(self, user_info: dict) -> str:
        """Create a new session for the user"""
        session_id = str(uuid.uuid4())
        session_data = {
            'user_id': user_info.get('id', user_info.get('email')),
            'email': user_info.get('email'),
            'name': user_info.get('name', user_info.get('given_name', 'User')),
            'provider': user_info.get('provider', 'unknown'),
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(days=7)).isoformat()
        }
        self.sessions[session_id] = session_data
        return session_id
    
    def get_session(self, session_id: str) -> dict:
        """Get session data by session ID"""
        session_data = self.sessions.get(session_id)
        if not session_data:
            return None
        
        # Check if session is expired
        expires_at = datetime.fromisoformat(session_data['expires_at'])
        if datetime.utcnow() > expires_at:
            self.delete_session(session_id)
            return None
        
        return session_data
    
    def delete_session(self, session_id: str):
        """Delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def is_authenticated(self, request: Request) -> bool:
        """Check if the request has a valid session"""
        session_id = request.session.get('session_id')
        if not session_id:
            return False
        
        session_data = self.get_session(session_id)
        return session_data is not None
    
    def get_current_user(self, request: Request) -> dict:
        """Get current user from session"""
        session_id = request.session.get('session_id')
        if not session_id:
            return None
        
        return self.get_session(session_id)

# Global session manager instance
session_manager = SessionManager() 