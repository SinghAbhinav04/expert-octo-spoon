"""
Database connection and session management - MongoDB via Motor
"""
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from app.config import settings


class Database:
    """MongoDB async connection manager using Motor"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
    
    async def connect(self):
        """Create MongoDB connection"""
        self.client = AsyncIOMotorClient(settings.MONGODB_URI)
        self.db = self.client[settings.MONGODB_DB_NAME]
        
        # Test connection
        await self.client.admin.command("ping")
        print("✅ MongoDB connection established")
    
    async def disconnect(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            print("✅ MongoDB connection closed")
    
    async def ping(self) -> bool:
        """Health check - ping MongoDB"""
        try:
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False


# Global database instance
db = Database()


async def get_db():
    """FastAPI dependency for database access"""
    return db
