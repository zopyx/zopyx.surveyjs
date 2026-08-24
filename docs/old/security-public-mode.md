# Public Mode (Default) Access

## Overview

**Public Mode** is the default access control setting for surveys. In this mode, the survey is accessible to anyone who can view the content item in Plone. This provides the simplest access model with no additional token or authentication requirements beyond standard Plone permissions.

Public mode is ideal for:

- Anonymous public surveys
- Internal surveys within an organization
- Quick testing and development
- Low-security requirements
- Open research questionnaires

## Architecture

### Components

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Survey        │────▶│   Standard       │────▶│   Plone         │
│   Content       │     │   Plone          │     │   Security      │
│   Item          │     │   Permissions    │     │   (roles,       │
│                 │     │   (View)         │     │   workflows)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │
         │
         ▼
┌─────────────────┐
│   No Additional │
│   Token Check   │
│   Required      │
└─────────────────┘
```

### Access Control Model

Public mode relies entirely on Plone's standard security:

| Layer | Control |
|-------|---------|
| **Workflow** | Content state (private, published, etc.) |
| **Permissions** | `View` permission on survey object |
| **Roles** | Anonymous, Authenticated, Member, etc. |
| **Sharing** | Per-object local roles (if enabled) |

## Usage

### Setting Public Mode

Public mode is the default. To explicitly set or return to public mode:

1. Navigate to the survey and click **Metadata**
2. Set **Access Mode** to `public` (or leave empty/default)
3. Save the survey

### URL Structure

```
# Standard survey access
https://example.com/path/to/survey

# With viewer
https://example.com/path/to/survey/@@viewer

# Embed in iframe
https://example.com/path/to/survey/@@viewer-embed
```

### Permission Requirements

| User Type | Can Access If... |
|-----------|------------------|
| **Anonymous** | Survey is published AND "Allow anonymous" is enabled globally |
| **Authenticated** | Has `View` permission on the survey object |
| **Owner/Editor** | Always (via ownership or local roles) |

## Technical Implementation

### Access Check

Located in `browser/services/auth.py`:

```python
def trusted_access_enabled(self):
    """Return whether trusted access mode is enabled."""
    mode = getattr(self.context, "access_mode", "") or "public"
    mode = str(mode).strip().lower()
    return mode in ("trusted", "trusted-tokens")
    # Returns False for 'public' mode - no token checks performed
```

### View Rendering

In `survey_viewer.pt`, the trusted access check is skipped:

```python
def _require_trusted_access(self) -> bool:
    """Validate trusted access requirements."""
    if self.can_manage_portal_content:
        return True
    if not self._auth().trusted_access_enabled():
        return True  # Public mode - always allow
    # ... token validation for trusted modes
```

## Security Model

### Default Plone Security

Public mode defers to Plone's standard security stack:

```
User Request
    │
    ▼
┌───────────────┐
│  Zope Access  │  ──▶  Check roles/permissions
│  Control      │
└───────────────┘
    │
    ▼
┌───────────────┐
│  Plone        │  ──▶  Check workflow state
│  Workflow     │
└───────────────┘
    │
    ▼
┌───────────────┐
│  Survey       │  ──▶  Render form (no token check)
│  Render       │
└───────────────┘
```

### Permission Inheritance

```
Plone Site
    │
    ├── Folder (inherits)
    │       │
    │       └── Survey (inherits + local settings)
    │               │
    │               └── View permission checked
```

### Common Permission Scenarios

#### Public Anonymous Survey

1. Survey workflow state: **Published**
2. Global setting: Allow anonymous submissions
3. Result: Anyone can access and submit

#### Members-Only Survey

1. Survey workflow state: **Published**
2. Global setting: Require authentication
3. Result: Only logged-in users can access

#### Private Survey (Testing)

1. Survey workflow state: **Private**
2. Result: Only owner and editors can access

#### Team Survey (Sharing)

1. Survey workflow state: **Published** or **Internal**
2. Sharing tab: Add specific users/groups
3. Result: Only shared users can access

## Configuration

### No Special Configuration Required

Public mode requires no additional settings beyond standard Plone configuration:

- No token cache path needed
- No token TTL settings
- No generation of access tokens

### Related Settings

| Setting | Location | Effect |
|---------|----------|--------|
| **Workflow** | Survey → State | Controls visibility |
| **Sharing** | Survey → Sharing | Local role assignments |
| **Anonymous** | Control Panel | Global anonymous access policy |

## Comparison with Trusted Modes

| Feature | Public | Trusted (Cached) | Trusted-Tokens |
|---------|--------|-----------------|---------------|
| **Access control** | Plone permissions only | Time-limited token | Single-use token |
| **URL complexity** | Simple | Token parameter | Token parameter |
| **Distribution** | Any Plone link sharing | Share token URL | Share individual tokens |
| **Revocation** | Change permissions/workflow | Revoke token or expire | Use token once |
| **Audit trail** | Plone audit only | Limited cache logging | Full token history |
| **Best for** | Open surveys, testing | Time-limited campaigns | Controlled single-use |

## Security Considerations

### Strengths

| Aspect | Security |
|--------|----------|
| **Simplicity** | No additional attack surface |
| **Integration** | Uses well-tested Plone security |
| **Flexibility** | Full workflow and sharing support |
| **Audit** | Standard Plone audit trail |

### Considerations

| Concern | Mitigation |
|---------|------------|
| **Link sharing** | Anyone with link can access (intended behavior) |
| **No submission limits** | Users can submit multiple times (configure via actions) |
| **No time limits** | Survey available until workflow state changes |

### When NOT to Use Public Mode

Avoid public mode when you need:

- **Single submission per person** → Use trusted-tokens
- **Time-limited access** → Use trusted (cached) mode
- **External distribution control** → Use trusted modes
- **Strict access tracking** → Use trusted-tokens with CSV audit

## Troubleshooting

### "You are not authorized to access this resource"

- Survey workflow state is **Private**
- User lacks `View` permission
- Check workflow state and publish survey

### Anonymous users cannot access

- Verify survey is **Published**
- Check global anonymous access settings
- Check if survey folder restricts anonymous access

### Survey visible but submissions fail

- Check user has `Add portal content` permission (for storing results)
- Verify survey actions include "store" if persisting data

## Best Practices

### For Public Surveys

1. **Clear survey description** - Users know what they're submitting
2. **Privacy notice** - Include data handling information
3. **Rate limiting** - Configure at proxy/load balancer level
4. **SPAM protection** - Consider CAPTCHA for anonymous submissions
5. **Data retention** - Define and document retention policies

### For Internal/Member Surveys

1. **Use internal workflow state** - If available in your Plone setup
2. **Folder-level permissions** - Restrict at folder level for cleaner security
3. **Group-based sharing** - Use Plone groups for easier management

### Migration to Trusted Modes

When moving from public to restricted access:

1. **Communication** - Notify existing users of access changes
2. **Grace period** - Consider keeping public during transition
3. **Token distribution** - Plan how to distribute access tokens/links
4. **Documentation** - Provide clear instructions for participants

## Future Considerations

Potential enhancements that could apply to public mode:

1. **Rate limiting** - Built-in per-IP submission limits
2. **CAPTCHA integration** - Native SPAM protection
3. **Submission quotas** - Max total submissions limit
4. **Time windows** - Scheduled availability without token complexity
