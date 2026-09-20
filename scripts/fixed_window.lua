-- scripts/fixed_window.lua
-- Portable fixed-window rate limiter counter.
-- KEYS[1] = rate limit key
-- ARGV[1] = window TTL in seconds
-- Returns the new counter value after increment.
local c = redis.call('INCR', KEYS[1])
if c == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return c
