# Survey Embedding

This document describes the iframe-based embedding flow for Privacy Forms Studio surveys.

## Overview

Embedding is configured per survey. The only supported embedding mode is **Iframe**. When enabled, a minimal viewer variant is exposed at ``@@viewer-embed`` and can be placed inside an iframe on external sites.

## Enable embedding

1. Edit the survey.
2. Set **Embedding mode** to **Iframe**.

When the mode is **None**, embedding is blocked.

## Embed the survey

Use the survey URL and append ``/@@viewer-embed``:

```html
<iframe
  src="https://your-plone-site.com/surveys/customer-satisfaction/@@viewer-embed"
  width="100%"
  height="800"
  style="border: 0;"
  loading="lazy"
  title="Customer Satisfaction Survey">
</iframe>
```

## Security headers

When embedding is enabled, the embed view clears ``X-Frame-Options`` and sets:

```
Content-Security-Policy: frame-ancestors *
```

If embedding is disabled, the embed view returns HTTP 403.
