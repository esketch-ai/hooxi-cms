from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import uuid
from datetime import datetime

# Database URL from environment or default
DATABASE_URL = "postgresql://hooxi:hooxi_secret123@localhost:5432/hooxi_cms"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class Client(Base):
    __tablename__ = "clients"
    
    client_id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_type = Column(String(20), nullable=False)
    company_name = Column(String(100))
    biz_reg_no = Column(String(20))
    ceo_name = Column(String(50))
    main_contact_name = Column(String(50))
    main_contact_phone = Column(String(20))
    main_contact_email = Column(String(100), index=True)
    contract_status = Column(String(20), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Contract(Base):
    __tablename__ = "contracts"
    
    contract_id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.client_id"), nullable=False)
    contract_no = Column(String(50))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    amount = Column(Float)
    status = Column(String(20), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ServiceRequest(Base):
    __tablename__ = "service_requests"
    
    request_id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.client_id"), nullable=False)
    request_type = Column(String(50))
    description = Column(Text)
    status = Column(String(20), default="PENDING")
    priority = Column(String(20), default="NORMAL")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatLog(Base):
    __tablename__ = "chat_logs"
    
    log_id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.client_id"), nullable=True)
    message = Column(Text, nullable=False)
    response = Column(Text)
    is_user = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)
