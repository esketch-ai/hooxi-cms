-- Hooxi CMS Database Initialization
-- Based on planning document: IA-based CRM System

-- Enable UUID extension for PostgreSQL 15+
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Clients table (tb_client)
CREATE TABLE IF NOT EXISTS clients (
    client_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_type VARCHAR(20) NOT NULL,
    company_name VARCHAR(100),
    biz_reg_no VARCHAR(20),
    ceo_name VARCHAR(50),
    main_contact_name VARCHAR(50),
    main_contact_phone VARCHAR(20),
    main_contact_email VARCHAR(100),
    contract_status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_clients_type ON clients(client_type);
CREATE INDEX idx_clients_company ON clients(company_name);
CREATE INDEX idx_clients_contact_email ON clients(main_contact_email);
CREATE INDEX idx_clients_status ON clients(contract_status);

-- Contract details table
CREATE TABLE IF NOT EXISTS contracts (
    contract_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(client_id) ON DELETE CASCADE,
    contract_no VARCHAR(50),
    start_date DATE,
    end_date DATE,
    amount DECIMAL(15, 2),
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Service requests table (FMS integration)
CREATE TABLE IF NOT EXISTS service_requests (
    request_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(client_id) ON DELETE CASCADE,
    request_type VARCHAR(50),
    description TEXT,
    status VARCHAR(20) DEFAULT 'PENDING',
    priority VARCHAR(20) DEFAULT 'NORMAL',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chat logs for AI chatbot
CREATE TABLE IF NOT EXISTS chat_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(client_id) ON DELETE SET NULL,
    message TEXT NOT NULL,
    response TEXT,
    is_user BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create audit triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_clients_timestamp BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_contracts_timestamp BEFORE UPDATE ON contracts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data for testing
INSERT INTO clients (client_type, company_name, ceo_name, main_contact_email) VALUES
('TRANSPORT', 'Sample Transport Co.', 'CEO Name', 'ceo@example.com'),
('FACILITY', 'Sample Facility Inc.', 'Manager Name', 'manager@example.com');

