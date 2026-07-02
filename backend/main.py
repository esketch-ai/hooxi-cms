from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid
import os

# Import SQLAlchemy models
try:
    from sqlalchemy.orm import Session
    from .models import Client, Contract, ServiceRequest, ChatLog, engine, SessionLocal
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("⚠️  Database not available - using in-memory storage")

# Initialize FastAPI app
app = FastAPI(
    title="Hooxi CMS API",
    description="Carbon Fleet Management System API",
    version="1.0.0"
)

# CORS middleware for frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files middleware - serve React app from /dist (not /static)
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="/dist"), name="static")

# Database session dependency
def get_db():
    if not DATABASE_AVAILABLE:
        yield None
        return
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models for API requests
class ClientCreate(BaseModel):
    client_type: str
    company_name: Optional[str] = None
    biz_reg_no: Optional[str] = None
    ceo_name: Optional[str] = None
    main_contact_email: Optional[str] = None

class ContractCreate(BaseModel):
    client_id: str
    contract_no: str
    start_date: str
    end_date: str
    amount: float

# Health check endpoint
@app.get("/")
async def root(request: Request):
    """Serve React app for frontend"""
    static_path = "/dist/index.html"  # Fixed path from dist folder
    if os.path.exists(static_path):
        from fastapi.responses import FileResponse
        return FileResponse(static_path)
    
    # Fallback to API response if no static files found
    return {"Hello": "World", "API": "Hooxi CMS v1.0"}

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "database_available": DATABASE_AVAILABLE
    }

# Client Management APIs with Database Support
@app.get("/api/clients")
async def get_clients(client_type: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Get all clients, optionally filtered by type"""
    if not DATABASE_AVAILABLE:
        return []
    
    query = Client
    if client_type:
        query = query.filter(Client.client_type == client_type)
    
    return [client.dict() for client in db.query(query).all()]

@app.get("/api/clients/{client_id}")
async def get_client(client_id: str, db: Session = Depends(get_db)):
    """Get a specific client by ID"""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client.dict()

@app.post("/api/clients", status_code=201)
async def create_client(client_data: ClientCreate, db: Session = Depends(get_db)):
    """Create a new client"""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    new_client = Client(
        client_id=str(uuid.uuid4()),
        client_type=client_data.client_type,
        company_name=client_data.company_name,
        biz_reg_no=client_data.biz_reg_no,
        ceo_name=client_data.ceo_name,
        main_contact_email=client_data.main_contact_email,
        contract_status="ACTIVE"
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    return new_client.dict()

@app.put("/api/clients/{client_id}")
async def update_client(client_id: str, client_data: ClientCreate, db: Session = Depends(get_db)):
    """Update an existing client"""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    update_data = client_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(client, key, value)
    
    db.commit()
    db.refresh(client)
    return client.dict()

@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: str, db: Session = Depends(get_db)):
    """Delete a client"""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    db.delete(client)
    db.commit()
    return {"message": "Client deleted successfully"}

# Contract Management APIs  
@app.get("/api/contracts")
async def get_contracts(client_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Get all contracts, optionally filtered by client"""
    if not DATABASE_AVAILABLE:
        return []
    
    query = Contract
    if client_id:
        query = query.filter(Contract.client_id == client_id)
    
    return [contract.dict() for contract in db.query(query).all()]

@app.post("/api/contracts", status_code=201)
async def create_contract(contract_data: ContractCreate, db: Session = Depends(get_db)):
    """Create a new contract"""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    new_contract = Contract(
        contract_id=str(uuid.uuid4()),
        client_id=contract_data.client_id,
        contract_no=contract_data.contract_no,
        start_date=datetime.fromisoformat(contract_data.start_date),
        end_date=datetime.fromisoformat(contract_data.end_date),
        amount=contract_data.amount,
        status="ACTIVE"
    )
    db.add(new_contract)
    db.commit()
    db.refresh(new_contract)
    return new_contract.dict()

# Service Request APIs (FMS Integration)
@app.get("/api/service-requests")
async def get_service_requests(status: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Get service requests, optionally filtered by status"""
    if not DATABASE_AVAILABLE:
        return []
    
    query = ServiceRequest
    if status:
        query = query.filter(ServiceRequest.status == status)
    
    return [sr.dict() for sr in db.query(query).all()]

@app.post("/api/service-requests", status_code=201)
async def create_service_request(request_data: dict, db: Session = Depends(get_db)):
    """Create a new service request"""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    new_request = ServiceRequest(
        request_id=str(uuid.uuid4()),
        **request_data,
        status="PENDING"
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
    return new_request.dict()

# Chat Log APIs (AI Chatbot)
@app.get("/api/chat-logs/{client_id}")
async def get_chat_logs(client_id: str, limit: int = Query(50), db: Session = Depends(get_db)):
    """Get chat logs for a specific client"""
    if not DATABASE_AVAILABLE:
        return []
    
    logs = db.query(ChatLog).filter(ChatLog.client_id == client_id).order_by(ChatLog.created_at.desc()).limit(limit)
    return [log.dict() for log in logs]

@app.post("/api/chat-logs/{client_id}")
async def add_chat_log(client_id: str, message_data: dict, db: Session = Depends(get_db)):
    """Add a new chat log"""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    new_log = ChatLog(
        log_id=str(uuid.uuid4()),
        **message_data,
        client_id=client_id,
        created_at=datetime.utcnow()
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return new_log.dict()

# Dashboard Statistics APIs
@app.get("/api/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics"""
    if not DATABASE_AVAILABLE:
        return {
            "total_clients": 0,
            "transport_clients": 0,
            "facility_clients": 0,
            "active_contracts": 0,
            "pending_requests": 0
        }
    
    total_clients = db.query(Client).count()
    transport_clients = db.query(Client).filter(Client.client_type == "TRANSPORT").count()
    facility_clients = db.query(Client).filter(Client.client_type == "FACILITY").count()
    active_contracts = db.query(Contract).filter(Contract.status == "ACTIVE").count()
    pending_requests = db.query(ServiceRequest).filter(ServiceRequest.status == "PENDING").count()
    
    return {
        "total_clients": total_clients,
        "transport_clients": transport_clients,
        "facility_clients": facility_clients,
        "active_contracts": active_contracts,
        "pending_requests": pending_requests
    }

# FMS Integration Endpoint
@app.post("/api/fms/webhook")
async def fms_webhook(data: dict):
    """Handle FMS integration webhook"""
    return {
        "status": "received",
        "message": "FMS data processed successfully"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
