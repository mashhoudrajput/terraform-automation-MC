"""
Database configuration and models using SQLAlchemy.
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import enum

from src.config.settings import settings

# Create database engine
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}  # Needed for SQLite
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


class ClientStatusEnum(enum.Enum):
    """Enum for client deployment status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Client(Base):
    """Client database model."""
    __tablename__ = "clients"
    
    uuid = Column(String(36), primary_key=True, index=True)
    client_name = Column(String(100), nullable=False)
    job_id = Column(String(50), unique=True, index=True, nullable=False)
    status = Column(Enum(ClientStatusEnum), default=ClientStatusEnum.PENDING, nullable=False)
    environment = Column(String(20), nullable=False)
    region = Column(String(50), nullable=False)
    terraform_outputs = Column(Text, nullable=True)  # JSON string
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

