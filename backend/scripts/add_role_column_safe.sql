-- Safe migration to add role column to signature_request_signers

-- Step 1: Add column as nullable
ALTER TABLE signature_request_signers 
ADD COLUMN IF NOT EXISTS role VARCHAR(20);

-- Step 2: Update existing records with default value
UPDATE signature_request_signers 
SET role = 'signer' 
WHERE role IS NULL;

-- Step 3: Add NOT NULL constraint
ALTER TABLE signature_request_signers 
ALTER COLUMN role SET NOT NULL;

-- Step 4: Add default for future inserts
ALTER TABLE signature_request_signers 
ALTER COLUMN role SET DEFAULT 'signer';