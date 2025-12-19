# SurveyJS Embedding Guide

This guide explains how to embed SurveyJS forms into external websites.

## Overview

The embedding system allows you to integrate surveys into any website using a simple JavaScript API. The surveys are loaded in secure iframes with automatic height adjustment and responsive design.

## Architecture

```
┌─────────────────────────────────────────┐
│   Remote Website (External)             │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  <div class="surveyjs-embed">      │ │
│  │    ┌─────────────────────────────┐ │ │
│  │    │  iframe                     │ │ │
│  │    │  ┌───────────────────────┐  │ │ │
│  │    │  │ Survey Content        │  │ │ │
│  │    │  │ (from Plone)          │  │ │ │
│  │    │  └───────────────────────┘  │ │ │
│  │    └─────────────────────────────┘ │ │
│  └────────────────────────────────────┘ │
│                                          │
│  embed.js (loaded from Plone)            │
└─────────────────────────────────────────┘
              ↑
              │ HTTPS
              │
┌─────────────┴───────────────────────────┐
│   Plone Site (Your Server)              │
│                                          │
│  • embed.js (Public API)                │
│  • @@viewer-embed (Embed View)          │
│  • Survey Content                       │
│  • allow_embedding flag (Security)      │
└──────────────────────────────────────────┘
```

## Quick Start

### 1. Enable Embedding for Your Survey

In Plone, edit your survey and check the **"Allow Embedding"** checkbox. This is required for security.

### 2. Get the Survey URL

Copy the full URL to your survey, for example:
```
https://your-plone-site.com/surveys/customer-satisfaction
```

### 3. Embed in Your Website

Add this code to your HTML:

```html
<!DOCTYPE html>
<html>
<head>
  <title>My Website</title>
</head>
<body>
  <h1>Customer Feedback</h1>

  <!-- Include the embed script -->
  <script src="https://your-plone-site.com/++resource++zopyx.surveyjs/embed.js"></script>

  <!-- Add the survey container -->
  <div class="surveyjs-embed"
       data-survey-url="https://your-plone-site.com/surveys/customer-satisfaction">
  </div>
</body>
</html>
```

That's it! The survey will automatically load and display.

## Configuration Options

### Data Attributes (Declarative)

```html
<div class="surveyjs-embed"
     data-survey-url="https://your-plone-site.com/survey1"
     data-height="800px"
     data-width="100%"
     data-auto-resize="true">
</div>
```

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `data-survey-url` | String | *Required* | Full URL to the survey |
| `data-height` | String | `600px` | Height of the iframe (e.g., "800px", "50vh") |
| `data-width` | String | `100%` | Width of the iframe (e.g., "100%", "800px") |
| `data-auto-resize` | Boolean | `false` | Automatically adjust height to content |

### JavaScript API (Programmatic)

```javascript
// Basic embed
SurveyJSEmbed.embed('#my-container', {
  surveyUrl: 'https://your-plone-site.com/survey1',
  height: '600px',
  width: '100%',
  autoResize: false
});

// Re-initialize all embeds on the page
SurveyJSEmbed.init();
```

## Advanced Examples

### Auto-Resizing Survey

Automatically adjust iframe height to match survey content:

```html
<div class="surveyjs-embed"
     data-survey-url="https://your-plone-site.com/survey1"
     data-auto-resize="true">
</div>
```

This uses `postMessage` API to communicate between the iframe and parent page.

### Multiple Surveys on One Page

```html
<div class="surveyjs-embed"
     data-survey-url="https://your-plone-site.com/survey1"
     data-height="500px">
</div>

<div class="surveyjs-embed"
     data-survey-url="https://your-plone-site.com/survey2"
     data-height="500px">
</div>
```

### Dynamic Embedding

```html
<div id="survey-placeholder"></div>

<button onclick="loadSurvey()">Load Survey</button>

<script src="https://your-plone-site.com/++resource++zopyx.surveyjs/embed.js"></script>
<script>
  function loadSurvey() {
    SurveyJSEmbed.embed('#survey-placeholder', {
      surveyUrl: 'https://your-plone-site.com/survey1',
      height: '700px',
      autoResize: true
    });
  }
</script>
```

### Responsive Design

```html
<style>
  .survey-wrapper {
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
  }
</style>

<div class="survey-wrapper">
  <div class="surveyjs-embed"
       data-survey-url="https://your-plone-site.com/survey1"
       data-width="100%"
       data-height="600px">
  </div>
</div>
```

## Security

### Allow Embedding Flag

Surveys must explicitly enable the `allow_embedding` flag. This prevents unauthorized embedding of your surveys.

**To enable:**
1. Edit the survey in Plone
2. Check "Allow Embedding"
3. Save

**Default:** Disabled (false)

### CORS and iframe Security

- Surveys are loaded in iframes for security isolation
- The iframe uses the same authentication as direct access
- Survey submissions are saved with proper authentication tokens
- Cross-origin communication uses `postMessage` API with origin validation

### X-Frame-Options Handling

When embedding is enabled (`allow_embedding=True`), the system automatically:
- Removes the `X-Frame-Options` header that would block iframe embedding
- Sets `Content-Security-Policy: frame-ancestors *` to allow embedding from any origin
- Adds CORS headers to permit cross-origin requests

This allows the survey to be embedded in iframes on external websites while maintaining security through the opt-in `allow_embedding` flag.

### Content Security Policy (CSP)

If your website uses CSP, you may need to add:

```html
<meta http-equiv="Content-Security-Policy"
      content="frame-src https://your-plone-site.com;">
```

## Styling

### Container Styling

Style the container div to position the survey:

```css
.surveyjs-embed {
  margin: 40px 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  border-radius: 8px;
  overflow: hidden;
}
```

### Loading State

The embed script shows a loading message while the survey loads:

```
Loading survey...
```

### Error States

If embedding fails, users see:

```
🔒 Embedding Not Allowed
This survey is not configured to be embedded.
Please contact the survey administrator.
```

## Troubleshooting

### Survey Not Loading

**Problem:** White screen or "Loading survey..." never completes

**Solutions:**
- Verify the survey URL is correct and accessible
- Check that "Allow Embedding" is enabled in survey settings
- Open browser developer console to see errors
- Test the embed URL directly: `https://your-site.com/survey1/@@viewer-embed`

### Embedding Not Allowed Error

**Problem:** Shows "🔒 Embedding Not Allowed"

**Solution:**
1. Go to the survey in Plone
2. Click "Edit"
3. Check "Allow Embedding"
4. Save

### X-Frame-Options Error

**Problem:** Console shows "Refused to display in a frame because it set 'X-Frame-Options' to 'sameorigin'"

**Solution:**
1. Ensure "Allow Embedding" is checked in the survey settings
2. Restart your Plone instance if you just updated the code
3. Clear your browser cache
4. Verify you're accessing the embed URL: `https://your-site.com/survey1/@@viewer-embed`

**Technical Details:**
When `allow_embedding=True`, the `EmbedViewer` class automatically:
- Removes the `X-Frame-Options` header
- Sets `Content-Security-Policy: frame-ancestors *`
- Adds CORS headers for cross-origin access

### Height Issues

**Problem:** Survey is cut off or has scrollbars

**Solutions:**
- Use `data-auto-resize="true"` for automatic height
- Set a larger fixed height: `data-height="800px"`
- Check that parent containers have enough space

### CORS Errors

**Problem:** Console shows CORS-related errors

**Solutions:**
- Verify "Allow Embedding" is enabled
- Check that the Plone site is accessible from the remote website
- Ensure HTTPS is used if the parent site uses HTTPS

### Multiple Surveys Not Loading

**Problem:** Only first survey loads

**Solution:**
- Ensure each div has a unique container
- Check browser console for JavaScript errors
- Verify all surveys have "Allow Embedding" enabled

## Performance

### Loading Speed

- The embed script is ~15KB minified
- Surveys load asynchronously
- Multiple surveys load in parallel
- Consider lazy-loading for surveys below the fold

### Best Practices

1. **Use Auto-Resize Sparingly**: It adds overhead for height calculation
2. **Set Fixed Heights When Possible**: Better performance than auto-resize
3. **Limit Surveys Per Page**: Consider pagination for many surveys
4. **CDN Deployment**: Host embed.js on a CDN for better performance

## API Reference

### Global Object

```javascript
window.SurveyJSEmbed
```

### Methods

#### `init()`

Re-initialize all survey embeds on the page.

```javascript
SurveyJSEmbed.init();
```

#### `embed(element, options)`

Embed a survey into a specific element.

**Parameters:**
- `element` (String|HTMLElement): CSS selector or DOM element
- `options` (Object): Embed configuration

```javascript
SurveyJSEmbed.embed('#container', {
  surveyUrl: 'https://...',
  height: '600px',
  width: '100%',
  autoResize: false
});
```

### Options Object

```typescript
interface EmbedOptions {
  surveyUrl: string;      // Required: Full URL to survey
  height?: string;        // Optional: Height (default: "600px")
  width?: string;         // Optional: Width (default: "100%")
  autoResize?: boolean;   // Optional: Auto-resize (default: false)
}
```

### Properties

#### `version`

Get the embed library version.

```javascript
console.log(SurveyJSEmbed.version); // "1.0.0"
```

## Browser Support

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

## Files

| File | Path | Purpose |
|------|------|---------|
| Embed Library | `++resource++zopyx.surveyjs/embed.js` | Public JavaScript API |
| Embed View | `@@viewer-embed` | Minimal survey viewer for iframes |
| Example Page | `++resource++zopyx.surveyjs/embed-example.html` | Usage examples |
| Documentation | `EMBEDDING.md` | This file |

## Support

For issues or questions:

1. Check browser console for errors
2. Verify survey URL and "Allow Embedding" setting
3. Review this documentation
4. Contact your system administrator

## Changelog

### Version 1.0.0
- Initial release
- Basic iframe embedding
- Auto-resize support
- Multiple surveys per page
- Security with `allow_embedding` flag
- Comprehensive error handling
