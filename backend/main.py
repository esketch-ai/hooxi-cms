from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime

# Initialize FastAPI app
app = FastAPI(
    title="Hooxi CMS API",
    description="Carbon Fleet Management System API",
    version="1.0.0"
)

# CORS middleware for frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database simulation (replace with actual PostgreSQL later)
class ClientModel(BaseModel):
    client_id: str = None  # UUID
    client_type: str
    company_name: Optional[str] = None
    biz_reg_no: Optional[str] = None
    ceo_name: Optional[str] = None
    main_contact_name: Optional[str] = None
    main_contact_phone: Optional[str] = None
    main_contact_email: Optional[str] = None
    contract_status: str = "ACTIVE"

# In-memory storage (replace with database)
clients_db = [
    ClientModel(
        client_id=str(uuid.uuid4()),
        client_type="TRANSPORT",
        company_name="대한로지스 (주)",
        biz_reg_no="123-45-67890",
        ceo_name="CEO Name",
        main_contact_email="ceo@example.com"
    ),
    ClientModel(
        client_id=str(uuid.uuid4()),
        client_type="FACILITY", 
        company_name="스마트에코타워",
        biz_reg_no="987-65-43210",
        ceo_name="Manager Name"
    ),
]

contracts_db = []
service_requests_db = []
chat_logs_db = []

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
async def root():
    return {"Hello": "World", "API": "Hooxi CMS v1.0"}

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# Client Management APIs
@app.get("/api/clients")
async def get_clients(client_type: Optional[str] = None):
    """Get all clients, optionally filtered by type"""
    if client_type:
        return [client.dict() for client in clients_db if client.client_type == client_type]
    return [client.dict() for client in clients_db]

@app.get("/api/clients/{client_id}")
async def get_client(client_id: str):
    """Get a specific client by ID"""
    client = next((c for c in clients_db if c.client_id == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client.dict()

@app.post("/api/clients", status_code=201)
async def create_client(client_data: ClientCreate):
    """Create a new client"""
    new_client = ClientModel(
        client_id=str(uuid.uuid4()),
        client_type=client_data.client_type,
        company_name=client_data.company_name,
        biz_reg_no=client_data.biz_reg_no,
        ceo_name=client_data.ceo_name,
        main_contact_email=client_data.main_contact_email,
        contract_status="ACTIVE"
    )
    clients_db.append(new_client)
    return new_client.dict()

@app.put("/api/clients/{client_id}")
async def update_client(client_id: str, client_data: ClientCreate):
    """Update an existing client"""
    client = next((c for c in clients_db if c.client_id == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    update_data = client_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(client, key, value)
    
    return client.dict()

@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: str):
    """Delete a client"""
    global clients_db
    initial_length = len(clients_db)
    clients_db = [c for c in clients_db if c.client_id != client_id]
    
    if len(clients_db) == initial_length:
        raise HTTPException(status_code=404, detail="Client not found")
        
    return {"message": "Client deleted successfully"}

# Contract Management APIs  
@app.get("/api/contracts")
async def get_contracts(client_id: Optional[str] = None):
    """Get all contracts, optionally filtered by client"""
    if client_id:
        return [c.dict() for c in contracts_db if c.client_id == client_id]
    return [c.dict() for c in contracts_db]

@app.post("/api/contracts", status_code=201)
async def create_contract(contract_data: ContractCreate):
    """Create a new contract"""
    new_contract = {
        "contract_id": str(uuid.uuid4()),
        **contract_data.dict()
    }
    contracts_db.append(new_contract)
    return new_contract

# Service Request APIs (FMS Integration)
@app.get("/api/service-requests")
async def get_service_requests(status: Optional[str] = None):
    """Get service requests, optionally filtered by status"""
    if status:
        return [sr.dict() for sr in service_requests_db if sr.status == status]
    return [sr.dict() for sr in service_requests_db]

@app.post("/api/service-requests", status_code=201)
async def create_service_request(request_data: dict):
    """Create a new service request"""
    new_request = {
        "request_id": str(uuid.uuid4()),
        **request_data,
        "status": "PENDING"
    }
    service_requests_db.append(new_request)
    return new_request

# Chat Log APIs (AI Chatbot)
@app.get("/api/chat-logs/{client_id}")
async def get_chat_logs(client_id: str, limit: int = 50):
    """Get chat logs for a specific client"""
    logs = [log.dict() for log in chat_logs_db if log.client_id == client_id][-limit:]
    return logs

@app.post("/api/chat-logs/{client_id}")
async def add_chat_log(client_id: str, message_data: dict):
    """Add a new chat log"""
    new_log = {
        "log_id": str(uuid.uuid4()),
        **message_data,
        "client_id": client_id,
        "created_at": datetime.now().isoformat()
    }
    chat_logs_db.append(new_log)
    return new_log

# Dashboard Statistics APIs
@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Get dashboard statistics"""
    total_clients = len(clients_db)
    transport_clients = len([c for c in clients_db if c.client_type == "TRANSPORT"])
    facility_clients = len([c for c in clients_db if c.client_type == "FACILITY"])
    
    return {
        "total_clients": total_clients,
        "transport_clients": transport_clients,
        "facility_clients": facility_clients,
        "active_contracts": len(contracts_db),
        "pending_requests": len([sr for sr in service_requests_db if sr.status == "PENDING"])
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
