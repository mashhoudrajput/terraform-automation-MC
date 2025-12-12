"""
Database configuration and models using SQLAlchemy.
"""
import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Text, Enum, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import enum

from src.config.settings import settings

logger = logging.getLogger(__name__)

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
    parent_uuid = Column(String(36), nullable=True, index=True)  # For sub-hospitals
    terraform_outputs = Column(Text, nullable=True)  # JSON string
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    
    # Add parent_uuid column if it doesn't exist (migration)
    try:
        inspector = inspect(engine)
        if 'clients' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('clients')]
            
            if 'parent_uuid' not in columns:
                with engine.connect() as conn:
                    conn.execute(text('ALTER TABLE clients ADD COLUMN parent_uuid VARCHAR(36)'))
                    conn.commit()
                logger.info("Added parent_uuid column to clients table")
    except Exception as e:
        logger.warning(f"Could not check/add parent_uuid column: {e}")


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

