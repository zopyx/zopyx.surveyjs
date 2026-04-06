# SSRF Fix Implementation Guide

## The Vulnerability

**Location:** `src/zopyx/surveyjs/subscribers.py`, lines 560-572

**Current vulnerable code:**
```python
def post_submission_payload(context, event):
    ...
    endpoint_url = getattr(context, "post_endpoint_url", None)
    ...
    response = httpx.post(endpoint_url, json=payload, timeout=10.0)  # ❌ NO VALIDATION
```

---

## The Fix

### Step 1: Add URL Validation Function

Add this function at the top of `subscribers.py` (after imports):

```python
import ipaddress
from urllib.parse import urlparse

def _validate_post_url(url: str) -> tuple[bool, str]:
    """
    Validate POST action URL to prevent SSRF attacks.
    
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not url:
        return False, "URL is required"
    
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"
    
    # Require http/https scheme
    if parsed.scheme not in ('http', 'https'):
        return False, f"URL scheme must be http or https, got: {parsed.scheme}"
    
    hostname = parsed.hostname or ""
    hostname_lower = hostname.lower()
    
    # Block known internal/cloud metadata hosts
    blocked_hosts = {
        # Localhost variations
        'localhost', '127.0.0.1', '::1', '0.0.0.0',
        # AWS
        '169.254.169.254',
        # GCP
        'metadata.google.internal',
        'metadata.google.internal.',
        # Alibaba Cloud
        '100.100.100.200',
        # Oracle Cloud
        '192.0.0.192',
        # IPv6 localhost
        '[::]', '[::1]',
    }
    
    if hostname_lower in blocked_hosts:
        return False, f"URL hostname is blocked: {hostname}"
    
    # Block if hostname contains localhost
    if 'localhost' in hostname_lower:
        return False, f"URL hostname is blocked: {hostname}"
    
    # Block private/reserved IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private:
            return False, f"Private IP addresses are not allowed: {hostname}"
        if ip.is_loopback:
            return False, f"Loopback IP addresses are not allowed: {hostname}"
        if ip.is_reserved:
            return False, f"Reserved IP addresses are not allowed: {hostname}"
        if ip.is_multicast:
            return False, f"Multicast IP addresses are not allowed: {hostname}"
    except ValueError:
        # Not an IP address - hostname is okay
        pass
    
    return True, ""
```

### Step 2: Modify the Vulnerable Function

Replace the `post_submission_payload` function in `subscribers.py`:

```python
def post_submission_payload(context, event):
    """POST the accepted submission plus latest form schema to an external endpoint.
    
    This is useful for integrating with downstream systems while preserving enough
    context (survey URL + form schema + poll payload) for external processing.
    """
    actions = getattr(context, "actions", set()) or set()
    if "post" not in actions:
        return

    endpoint_url = getattr(context, "post_endpoint_url", None)
    if not endpoint_url:
        logger.info(
            "POST action enabled but no endpoint configured for %s",
            getattr(context, "absolute_url", lambda: repr(context))(),
        )
        return

    # ✅ NEW: Validate URL to prevent SSRF
    is_valid, error_msg = _validate_post_url(endpoint_url)
    if not is_valid:
        logger.error(
            "POST action rejected due to invalid URL: %s - %s",
            endpoint_url,
            error_msg
        )
        return  # Fail safe - don't POST if URL is invalid

    poll_entry = event.form_data or {}
    poll_id = poll_entry.get("poll_id") or str(uuid.uuid1())
    created = poll_entry.get("created")
    if isinstance(created, datetime):
        created = ensure_timezone_aware(created).isoformat()

    annos = IAnnotations(context)
    form_json = _latest_form_json(annos)
    if not form_json:
        logger.info(
            "POST action enabled but no form version available; skipping POST for %s",
            getattr(context, "absolute_url", lambda: repr(context))(),
        )
        return

    payload = {
        "poll": dict(poll_entry, poll_id=poll_id, created=created),
        "form": form_json,
        "survey_url": getattr(context, "absolute_url", lambda: "")(),
    }

    try:
        response = httpx.post(endpoint_url, json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info(
            "Submission POSTed for poll %s to %s with status %s",
            poll_id,
            endpoint_url,
            response.status_code,
        )
    except Exception:
        logger.exception(
            "Failed to POST submission for poll %s to %s", poll_id, endpoint_url
        )
```

---

## Alternative: Allowlist-Based Approach

If you need to allow specific internal endpoints, use an allowlist:

```python
def _validate_post_url_allowlist(url: str, allowed_urls: list = None) -> tuple[bool, str]:
    """
    Validate URL against an explicit allowlist.
    More restrictive than the default approach.
    """
    if not url:
        return False, "URL is required"
    
    # Default allowlist (empty = no restrictions beyond SSRF protection)
    allowed_patterns = allowed_urls or []
    
    # Always block dangerous destinations
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    
    # Block metadata services
    blocked_patterns = [
        '169.254.169.254',  # AWS
        'metadata.google',   # GCP
        '100.100.100.200',   # Alibaba
        'localhost',
        '127.0.0.1',
    ]
    
    for pattern in blocked_patterns:
        if pattern in hostname:
            return False, f"URL contains blocked pattern: {pattern}"
    
    # If allowlist is configured, enforce it
    if allowed_patterns:
        import fnmatch
        matched = False
        for pattern in allowed_patterns:
            if fnmatch.fnmatch(url, pattern):
                matched = True
                break
        if not matched:
            return False, f"URL not in allowlist"
    
    return True, ""
```

---

## Testing the Fix

### Unit Tests

Add these tests to verify the fix:

```python
# File: src/zopyx/surveyjs/tests/test_ssrf_protection.py

import unittest
from zopyx.surveyjs.subscribers import _validate_post_url


class TestSSRFPrevention(unittest.TestCase):
    """Test SSRF protection in POST action URL validation."""
    
    def test_blocks_private_ips(self):
        """Private IP ranges should be blocked."""
        blocked_urls = [
            'http://169.254.169.254/latest/meta-data/',  # AWS metadata
            'http://localhost:8080/admin',                # Localhost
            'http://127.0.0.1:22/',                       # Loopback
            'http://10.0.0.1/internal',                   # Private 10.x
            'http://192.168.1.1/config',                  # Private 192.168.x
            'http://172.16.0.1/api',                      # Private 172.16-31.x
            'http://0.0.0.0/server',                      # All interfaces
        ]
        
        for url in blocked_urls:
            is_valid, error = _validate_post_url(url)
            self.assertFalse(is_valid, f"Should block: {url}")
            self.assertIn("blocked", error.lower())
    
    def test_blocks_cloud_metadata(self):
        """Cloud provider metadata endpoints should be blocked."""
        blocked_urls = [
            'http://metadata.google.internal/computeMetadata/v1/',
            'http://100.100.100.200/latest/meta-data/',   # Alibaba
            'https://169.254.169.254/latest/user-data',   # AWS
        ]
        
        for url in blocked_urls:
            is_valid, error = _validate_post_url(url)
            self.assertFalse(is_valid, f"Should block cloud metadata: {url}")
    
    def test_allows_valid_external_urls(self):
        """Valid external URLs should be allowed."""
        valid_urls = [
            'https://api.example.com/webhook',
            'http://hooks.zapier.com/hooks/catch/123/abc',
            'https://myapp.herokuapp.com/survey-callback',
        ]
        
        for url in valid_urls:
            is_valid, error = _validate_post_url(url)
            self.assertTrue(is_valid, f"Should allow: {url}")
            self.assertEqual(error, "")
    
    def test_blocks_file_protocol(self):
        """File protocol should be blocked."""
        is_valid, error = _validate_post_url('file:///etc/passwd')
        self.assertFalse(is_valid)
    
    def test_blocks_ftp_protocol(self):
        """FTP protocol should be blocked."""
        is_valid, error = _validate_post_url('ftp://internal.server/data')
        self.assertFalse(is_valid)
```

### Manual Testing

```bash
# Test 1: Blocked URL (AWS metadata)
curl -u "forms:formsarecool" \
  -X POST \
  -d "post_endpoint_url=http://169.254.169.254/latest/meta-data/" \
  http://localhost:8082/demo/survey/@@survey-metadata

# Check logs - should see: "POST action rejected due to invalid URL"

# Test 2: Valid URL
curl -u "forms:formsarecool" \
  -X POST \
  -d "post_endpoint_url=https://webhook.site/test" \
  http://localhost:8082/demo/survey/@@survey-metadata

# Should be accepted
```

---

## Quick Fix (Copy-Paste Ready)

Add to `src/zopyx/surveyjs/subscribers.py` after line 57 (after logger definition):

```python
import ipaddress
from urllib.parse import urlparse


def _validate_post_url(url: str) -> tuple[bool, str]:
    """Validate POST action URL to prevent SSRF attacks."""
    if not url:
        return False, "URL is required"
    
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"
    
    if parsed.scheme not in ('http', 'https'):
        return False, f"URL scheme must be http or https"
    
    hostname = (parsed.hostname or "").lower()
    
    blocked_hosts = {
        'localhost', '127.0.0.1', '::1', '0.0.0.0',
        '169.254.169.254',  # AWS
        'metadata.google.internal',  # GCP
        '100.100.100.200',  # Alibaba
    }
    
    if hostname in blocked_hosts or 'localhost' in hostname:
        return False, f"URL hostname is blocked"
    
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            return False, f"IP address is not allowed"
    except ValueError:
        pass
    
    return True, ""
```

Then modify `post_submission_payload` to use it (around line 531):

```python
    endpoint_url = getattr(context, "post_endpoint_url", None)
    if not endpoint_url:
        ...
        return

    # ADD THIS BLOCK:
    is_valid, error_msg = _validate_post_url(endpoint_url)
    if not is_valid:
        logger.error("POST action rejected - SSRF protection: %s - %s", 
                     endpoint_url, error_msg)
        return
    # END ADD
```

---

**Want me to apply this fix to the code?**
