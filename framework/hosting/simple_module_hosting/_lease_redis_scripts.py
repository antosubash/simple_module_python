"""Atomic Redis lease and semaphore operations."""

_ACQUIRE = """
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2]) then
  return redis.call('INCR', KEYS[2])
end
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('PEXPIRE', KEYS[1], ARGV[2])
  return redis.call('INCR', KEYS[2])
end
return 0
"""

_REFRESH = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

# Shared prologue: Redis' clock in ms, expired members dropped.
_SEM_NOW = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
local function keep(ttl)
  if redis.call('PTTL', KEYS[1]) < ttl then redis.call('PEXPIRE', KEYS[1], ttl) end
end
"""

_SEM_ACQUIRE = (
    _SEM_NOW
    + """
local ttl = tonumber(ARGV[3])
if redis.call('ZSCORE', KEYS[1], ARGV[1])
   or redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[2]) then
  redis.call('ZADD', KEYS[1], now + ttl, ARGV[1])
  keep(ttl)
  return redis.call('INCR', KEYS[2])
end
return 0
"""
)

_SEM_REFRESH = (
    _SEM_NOW
    + """
local ttl = tonumber(ARGV[2])
if not redis.call('ZSCORE', KEYS[1], ARGV[1]) then return 0 end
redis.call('ZADD', KEYS[1], 'XX', now + ttl, ARGV[1])
keep(ttl)
return 1
"""
)

_SEM_RELEASE = _SEM_NOW + "return redis.call('ZREM', KEYS[1], ARGV[1])"
