-- Calendar events table
CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    event_uid VARCHAR(255) UNIQUE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    location VARCHAR(500),
    organizer_email VARCHAR(255),
    meeting_link VARCHAR(500),
    discord_event_id VARCHAR(50),
    discord_message_id VARCHAR(50),
    source_email VARCHAR(255),
    raw_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- RSVPs table
CREATE TABLE IF NOT EXISTS calendar_rsvps (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES calendar_events(id) ON DELETE CASCADE,
    discord_user_id VARCHAR(50) NOT NULL,
    discord_username VARCHAR(100),
    response VARCHAR(20) NOT NULL,
    email_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(event_id, discord_user_id)
);

-- Shipping labels table
CREATE TABLE IF NOT EXISTS shipping_labels (
    id SERIAL PRIMARY KEY,
    tracking_number VARCHAR(100) UNIQUE NOT NULL,
    carrier VARCHAR(50) NOT NULL,
    service VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    provider_label_id VARCHAR(100),
    provider_shipment_id VARCHAR(100),
    rate_amount DECIMAL(10, 2) NOT NULL,
    label_pdf_base64 TEXT,
    label_url VARCHAR(500),
    from_address JSONB NOT NULL,
    to_address JSONB NOT NULL,
    parcel JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    discord_user_id VARCHAR(50),
    discord_message_id VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    voided_at TIMESTAMP WITH TIME ZONE
);

-- Drive file index (for AI context)
CREATE TABLE IF NOT EXISTS drive_files (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100),
    folder_id VARCHAR(100),
    folder_name VARCHAR(255),
    web_view_link VARCHAR(500),
    modified_time TIMESTAMP WITH TIME ZONE,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Package presets table
CREATE TABLE IF NOT EXISTS package_presets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    length DECIMAL(6, 2) NOT NULL,
    width DECIMAL(6, 2) NOT NULL,
    height DECIMAL(6, 2) NOT NULL,
    weight DECIMAL(6, 2) NOT NULL,
    discord_user_id VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events(start_time);
CREATE INDEX IF NOT EXISTS idx_shipping_labels_user ON shipping_labels(discord_user_id);
CREATE INDEX IF NOT EXISTS idx_shipping_labels_status ON shipping_labels(status);
CREATE INDEX IF NOT EXISTS idx_drive_files_folder ON drive_files(folder_id);
CREATE INDEX IF NOT EXISTS idx_package_presets_user ON package_presets(discord_user_id);
