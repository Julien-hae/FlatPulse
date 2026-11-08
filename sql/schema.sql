-- FlatPulse — schéma PostgreSQL 16 (#62). Modèle décrit dans docs/architecture.md §4.
--
-- Les montants (price_chf, charges_chf, min_price, max_price) sont en CENTIMES :
-- CHF 1'850.– → 185000 (§4.1). Un prix sur demande est NULL, jamais 0.

CREATE TABLE sources (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    slug            VARCHAR(50) UNIQUE NOT NULL,
    base_url        TEXT NOT NULL,
    scraper_class   VARCHAR(100) NOT NULL,
    poll_interval_s INT NOT NULL DEFAULT 120,
    rate_limit_rpm  INT NOT NULL DEFAULT 10,
    is_active       BOOLEAN DEFAULT TRUE,
    config          JSONB DEFAULT '{}',
    last_scraped_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE listings (
    id              SERIAL PRIMARY KEY,
    source_id       INT NOT NULL REFERENCES sources(id),
    external_id     VARCHAR(255) NOT NULL,
    external_url    TEXT NOT NULL,
    fingerprint     VARCHAR(64) NOT NULL,

    title           TEXT NOT NULL,
    description     TEXT,
    property_type   VARCHAR(20),       -- apartment, house, parking, commercial, storage
    price_chf       INT,               -- EN CENTIMES, loyer mensuel charges comprises
    charges_chf     INT,               -- EN CENTIMES, part des charges dans price_chf
    nb_rooms        DECIMAL(3,1),
    surface_m2      DECIMAL(7,2),      -- 45.5 m² reste 45.5, comme Listing.surface_m2
    floor           INT,               -- 0 = rez, négatif = sous-sol
    address         TEXT,
    city            VARCHAR(100),
    canton          VARCHAR(2),        -- code à deux lettres : GE, VD…
    postal_code     VARCHAR(10),
    listing_type    VARCHAR(10) DEFAULT 'rent',

    enriched        JSONB DEFAULT '{}',
    images          TEXT[] DEFAULT '{}',

    first_seen_at   TIMESTAMPTZ DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE,

    UNIQUE(source_id, external_id)
);

CREATE INDEX idx_listings_fingerprint ON listings(fingerprint);
CREATE INDEX idx_listings_search ON listings(is_active, city, nb_rooms, price_chf);
CREATE INDEX idx_listings_enriched ON listings USING GIN(enriched);

CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) UNIQUE,
    telegram_id BIGINT UNIQUE,
    lang        VARCHAR(2) DEFAULT 'fr',
    plan        VARCHAR(20) DEFAULT 'free',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE search_profiles (
    id                 SERIAL PRIMARY KEY,
    user_id            INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name               VARCHAR(100),
    listing_type       VARCHAR(10) DEFAULT 'rent',
    cities             TEXT[],
    cantons            VARCHAR(2)[],
    min_rooms          DECIMAL(3,1),
    max_rooms          DECIMAL(3,1),
    min_price          INT,            -- EN CENTIMES
    max_price          INT,            -- EN CENTIMES
    min_surface        INT,
    required_amenities TEXT[],
    pets_required      BOOLEAN DEFAULT FALSE,
    custom_criteria    TEXT,
    is_active          BOOLEAN DEFAULT TRUE,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    listing_id  INT NOT NULL REFERENCES listings(id),
    profile_id  INT NOT NULL REFERENCES search_profiles(id) ON DELETE CASCADE,
    channel     VARCHAR(20) NOT NULL,
    match_score DECIMAL(5,2) NOT NULL,
    sent_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, listing_id, channel)
);

-- NPA → canton (#133). Une ligne par (NPA, localité), avec le canton qui porte le
-- plus d'adresses de la localité : 1290 est Versoix (GE) et Chavannes-des-Bois (VD).
-- Données : répertoire officiel des localités, « Source : Office fédéral de
-- topographie swisstopo ». Les colonnes sont celles de sql/postal_codes.csv, qui se
-- charge tel quel : \copy postal_codes FROM 'sql/postal_codes.csv' CSV HEADER
CREATE TABLE postal_codes (
    postal_code  VARCHAR(4)  NOT NULL,
    locality     TEXT        NOT NULL,
    canton       VARCHAR(2)  NOT NULL,
    PRIMARY KEY (postal_code, locality)
);
