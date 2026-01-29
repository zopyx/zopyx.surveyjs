---
title: "Embedding"
sidebar_position: 11
---

Surveys can be embedded into external sites via a dedicated iframe view.

## Quick start

1.  Edit the survey and set **Embedding mode** to **Iframe**.
2.  Use the embed view in an iframe: `/@@viewer-embed`.

``` html
<iframe
  src="https://your-plone-site.com/surveys/customer-satisfaction/@@viewer-embed"
  width="100%"
  height="800"
  style="border: 0;"
  loading="lazy"
  title="Customer Satisfaction Survey">
</iframe>
```

## Security

Embedding is opt-in per survey. When enabled:

- `X-Frame-Options` is cleared for the embed view.
- `Content-Security-Policy: frame-ancestors *` is set.

When embedding is disabled, the embed view returns HTTP 403.
