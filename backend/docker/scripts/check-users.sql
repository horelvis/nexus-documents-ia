-- Script to check users and entity search issues

-- 1. Check all users in the database
SELECT 'All users:' as query;
SELECT id, email, full_name, tenant_id, created_at 
FROM users 
ORDER BY created_at DESC
LIMIT 10;

-- 2. Check users with names containing 'jo'
SELECT '
Users with names containing "jo":' as query;
SELECT id, email, full_name, tenant_id 
FROM users 
WHERE LOWER(COALESCE(full_name, '')) LIKE '%jo%' 
   OR LOWER(email) LIKE '%jo%';

-- 3. Check users grouped by tenant
SELECT '
Users per tenant:' as query;
SELECT tenant_id, COUNT(*) as user_count 
FROM users 
GROUP BY tenant_id;

-- 4. Check users with NULL full_name
SELECT '
Users with NULL full_name:' as query;
SELECT COUNT(*) as null_name_count 
FROM users 
WHERE full_name IS NULL;

-- 5. Sample data for testing (commented out - uncomment to insert test user)
-- INSERT INTO users (id, email, full_name, tenant_id, created_at, updated_at)
-- VALUES (
--     gen_random_uuid(),
--     'john.doe@example.com',
--     'John Doe',
--     (SELECT tenant_id FROM users LIMIT 1), -- Use existing tenant
--     NOW(),
--     NOW()
-- );