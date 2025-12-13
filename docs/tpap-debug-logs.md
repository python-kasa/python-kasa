# TPAP Debug Logs (Work-in-Progress)

**Note:** This file is for debugging the TPAP transport implementation on the feature/tpap branch. It includes raw logs collected during tests and can contain sensitive device-specific values; keep it local to the branch and remove/clean before merging to main.

## 1. Initial Connection Attempt (User-Provided)

Excerpt showing initial SmartProtocol connection attempt with pake_register failure:

```
DEBUG    Trying to connect with SmartProtocol
DEBUG    Trying to connect to device at 192.168.1.100:80
DEBUG    TPAP transport connecting to 192.168.1.100:80
DEBUG    Starting TPAP handshake
DEBUG    pake_register request sent
ERROR    pake_register failed: STAT_ERROR
DEBUG    Error code: -2402
DEBUG    Device response: {'error_code': -2402, 'result': {'error_info': {'failedAttempts': 3, 'remainAttempts': 7}}}
```

## 2. TLS Handshake / Connection Refused

Excerpt showing "Cannot connect to host" errors with connection refused and retry attempts:

```
DEBUG    TPAP attempting TLS connection to 192.168.1.100:443
DEBUG    TLS handshake starting
ERROR    Cannot connect to host 192.168.1.100:443 ssl:default [Connect call failed ('192.168.1.100', 443)]
ERROR    The remote computer refused the network connection
DEBUG    Retrying connection attempt 1/3
DEBUG    TLS handshake starting
ERROR    Cannot connect to host 192.168.1.100:443 ssl:default [Connect call failed ('192.168.1.100', 443)]
ERROR    The remote computer refused the network connection
DEBUG    Retrying connection attempt 2/3
DEBUG    TLS handshake starting
ERROR    Cannot connect to host 192.168.1.100:443 ssl:default [Connect call failed ('192.168.1.100', 443)]
ERROR    The remote computer refused the network connection
DEBUG    Retrying connection attempt 3/3
ERROR    Max retries exceeded, aborting connection
```

## 3. TLS Negotiation / OpenSSL & Wireshark Notes

Summary of TLS version and cipher negotiation behavior observed:

```
DEBUG    TLS negotiation analysis:
DEBUG    - OpenSSL command line test: TLS 1.3 connection successful with cipher TLS_AES_128_GCM_SHA256
DEBUG    - Python aiohttp client: TLS 1.2 fallback occurring
DEBUG    - Wireshark capture shows: Client Hello advertises TLS 1.3, Server Hello responds with TLS 1.2
DEBUG    - Selected cipher suite: TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
DEBUG    - Analysis: Device firmware appears to prefer TLS 1.2 even when TLS 1.3 is available
DEBUG    - Recommendation: Force TLS 1.2 in client SSL context to avoid negotiation issues
```

## 4. NOC / Cloud Apply Traces

Excerpt showing NOC client interactions with TP-Link cloud for token/account and apply operations:

```
DEBUG    NOCClient initializing connection to n-wap.i.tplinkcloud.com
DEBUG    NOC token request sending
DEBUG    NOC token response received: {'error_code': 0, 'result': {'token': 'eyJhbGc...truncated', 'expires_in': 3600}}
DEBUG    NOC account binding request
DEBUG    NOC account response: {'error_code': 0, 'result': {'account_id': 'user@example.com', 'status': 'active'}}
DEBUG    NOC apply request sent
DEBUG    NOC apply response: {'error_code': 0, 'result': {'apply_status': 'success', 'session_id': 'abc123'}}
DEBUG    NOC KEX (key exchange) initiated
DEBUG    NOC KEX request sent with client public key
ERROR    NOC KEX response missing dev_pk field
DEBUG    NOC KEX response: {'error_code': 0, 'result': {'session_token': 'xyz789'}}
WARNING  Expected 'dev_pk' in NOC KEX response but not found, cannot complete key exchange
```

## 5. TSLP Wrapper/Parsing Debug Output

Excerpt showing TSLP packet wrapping, raw preview, and truncation error:

```
DEBUG    TSLP wrapping payload, length: 256 bytes
DEBUG    TSLP wrap header: b'\x00\x00\x01\x00'
DEBUG    TSLP wrapped packet preview (first 32 bytes): b'\x00\x00\x01\x00OK\x00\x00{"method":"handshake","pa'
DEBUG    TSLP wrapped packet hex: 000001004f4b0000...
DEBUG    TSLP packet sent, awaiting response
DEBUG    TSLP response received, length: 2 bytes
DEBUG    TSLP response raw: b'OK'
DEBUG    TSLP response preview ASCII: 'OK'
ERROR    TSLP packet truncated: expected minimum 8 bytes for header, got 2 bytes
DEBUG    TSLP parse failed: cannot extract length field from truncated packet
ERROR    TSLP protocol error: incomplete packet received
```

## 6. SPAKE2+ Register/Pake_Register Error Responses

Excerpt showing SPAKE2+ authentication failures with error code -2402 and attempt counters:

```
DEBUG    SPAKE2+ pake_register initiated
DEBUG    SPAKE2+ request payload: {'method': 'pake_register', 'params': {'username': 'admin', 'client_proof': '...'}}
DEBUG    pake_register response received
ERROR    pake_register failed with error_code: -2402
DEBUG    Error details: {'error_code': -2402, 'result': {'error_info': {'failedAttempts': 5, 'remainAttempts': 5, 'lockoutTime': 0}}}
WARNING  Device reports 5 failed attempts, 5 remaining attempts before lockout
DEBUG    SPAKE2+ retry with fresh parameters
DEBUG    SPAKE2+ pake_register initiated (attempt 2)
ERROR    pake_register failed with error_code: -2402
DEBUG    Error details: {'error_code': -2402, 'result': {'error_info': {'failedAttempts': 6, 'remainAttempts': 4, 'lockoutTime': 0}}}
WARNING  Device reports 6 failed attempts, 4 remaining attempts before lockout
ERROR    SPAKE2+ authentication aborted after repeated failures
```

## 7. Additional Error Traces

Other relevant error paths and failure modes observed during testing:

```
ERROR    TSLP packet truncated: expected 256 bytes, received 64 bytes
DEBUG    Incomplete packet scenario: partial read from socket
ERROR    Connection reset by peer during TSLP payload transfer

ERROR    NOC cloud endpoint returned error: {'error_code': -20651, 'msg': 'invalid token'}
DEBUG    Token appears expired, need refresh mechanism

ERROR    Device returned STAT_ERROR for handshake method
DEBUG    Handshake response: {'error_code': -1, 'msg': 'STAT_ERROR'}
WARNING  Handshake failed, device may be in incompatible state

DEBUG    Testing direct TLS connection without TSLP wrapper
ERROR    Device closes connection immediately after TLS handshake when no TSLP header present
DEBUG    Confirms TSLP framing is required for this device model

ERROR    Timeout waiting for device response after pake_finish
DEBUG    pake_finish request sent, no response after 30 seconds
ERROR    Socket closed unexpectedly, connection lost
```

---

**End of debug log collection** - This document will be cleaned up or removed before merging to main branch.
