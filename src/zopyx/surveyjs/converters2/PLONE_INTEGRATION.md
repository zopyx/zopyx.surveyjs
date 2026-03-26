# Converters2 Plone Integration

This document describes how `converters2` has been integrated into the Plone add-on.

## Overview

The `converters2` package has been hooked into the Plone add-on through a compatibility layer (`converters2/compat.py`) that provides the same API as the original `converters` package while using `converters2` internally.

## Changes Made

### 1. New Compatibility Module

**File:** `src/zopyx/surveyjs/converters2/compat.py`

Provides API-compatible wrappers:

- `SurveyConverter` - Wraps converters2 with original API
- `Item` - Compatibility wrapper around converters2 `Cell`
- All `write_*` functions - Compatibility wrappers for export functions
- `build_table_rows`, `build_markdown` - Compatibility functions

### 2. Updated Plone Files

#### subscribers.py
```python
# Before
from .converters.cli import SurveyConverter
from .converters import write_text, write_markdown, ...

# After  
from .converters2.compat import SurveyConverter
from .converters2.compat import write_text, write_markdown, ...
```

#### browser/survey_results.py
```python
# Before
from ..converters import build_markdown
from ..converters.cli import SurveyConverter
from ..converters.html import build_html

# After
from ..converters2.compat import build_markdown
from ..converters2.compat import SurveyConverter
from ..converters2.html import build_html
```

#### browser/services/export.py
```python
# Before
from zopyx.surveyjs.converters import write_text, write_markdown, ...

# After
from zopyx.surveyjs.converters2.compat import write_text, write_markdown, ...
```

## Benefits

### For Nested/Dynamic Fields

| Field Type | Old Behavior | New Behavior |
|------------|--------------|--------------|
| `matrix` | Joined string | Separate columns per row |
| `checkbox` | Joined values | One-hot boolean columns |
| `matrixdynamic` | JSON blob | Proper table rows |
| `paneldynamic` | JSON blob | Proper table rows |

### CSV Export Improvements

The new CSV exports are much more analytical-friendly:

**Before:**
```csv
Key,Field,Value
Q11,Rating,"Quality: 5; Price: 4"
Q12,Orders,"[{product: Widget}, {product: Gadget}]"
```

**After (Wide format):**
```csv
_ResponseID,Q11_Quality,Q11_Price,Q12_product_0,Q12_product_1
resp-001,5,4,Widget,Gadget
```

**After (Long format):**
```csv
_ResponseID,_RowIndex,Q11_Quality,Q11_Price,Q12_product
resp-001,,5,4,
resp-001,0,,,Widget
resp-001,1,,,Gadget
```

## Backward Compatibility

The integration maintains full backward compatibility:

- All existing imports work unchanged
- Same function signatures
- Same return types
- No changes required to calling code

## Internal Architecture

```
Plone Code
    │
    ├──→ converters2/compat.py (API wrapper)
    │       │
    │       ├──→ converters2/ResponseBuilder (cell-based)
    │       │       │
    │       │       └──→ converters2/Cell objects
    │       │
    │       └──→ converters2/write_* functions
    │
    └──→ Original converters (if needed)
```

## Migration Path

### Immediate (No Changes Required)

The Plone add-on now uses `converters2` automatically through the compatibility layer. No code changes are needed.

### Gradual Migration (Optional)

For new code, you can use `converters2` directly:

```python
# Direct converters2 usage for new features
from zopyx.surveyjs.converters2 import SurveyConverter, write_csv

converter = SurveyConverter.from_files(form_path)
response = converter.convert(data, "resp-001")

# Use new features like long format CSV
write_csv(response, Path("out.csv"), format="long")
```

## Testing

Run the test suite:

```bash
cd /Users/ajung/src/zopyx.surveyjs
python -m pytest src/zopyx/surveyjs/converters2/tests/ -v
```

## Rollback

If needed, you can rollback to the original converters by reverting the import changes:

```python
# Revert to original converters
from .converters.cli import SurveyConverter
from .converters import write_text, ...
```

## Future Improvements

1. **Direct converters2 usage**: Gradually migrate Plone code to use converters2 directly
2. **New CSV formats**: Expose wide/long format options in Plone UI
3. **Performance**: converters2's flat cell structure enables faster processing
4. **Type safety**: Leverage converters2's rich type system
