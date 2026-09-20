-- scripts/release_lock.lua
-- Token-based compare-and-delete distributed lock release.
-- KEYS[1] = lock key
-- ARGV[1] = lock token (must match stored value to release)
-- Returns 1 if lock was released, 0 if not owned.
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
