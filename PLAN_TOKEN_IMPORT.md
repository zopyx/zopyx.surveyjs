# Plan: CSV Token Import Feature

## Overview
Add a dedicated import form within the existing token-store view that allows uploading a custom CSV file with a "token" column.

## Requirements
1. **CSV Upload Form**: Add file upload field to token_store.pt template
2. **Validation**:
   - CSV must have a "token" column
   - Each token must be at least 8 characters long
   - Handle malformed CSV files gracefully
3. **Success Message**: Show "#items tokens imported" after successful import
4. **Error Handling**: Clear error messages for validation failures

## Implementation Steps

### Step 1: Add `import_tokens()` method to TokenStore adapter
**File**: `src/zopyx/surveyjs/adapters/token_store.py`

Add a method that accepts a list of token strings and stores them:
```python
def import_tokens(self, tokens: list) -> dict:
    """Import a list of tokens into the store.
    
    :param tokens: List of token strings to import
    :return: Dict with 'imported' count and 'skipped' list (duplicates/invalid)
    """
```

### Step 2: Add CSV import handling to TokenStoreView
**File**: `src/zopyx/surveyjs/browser/token_store.py`

Add handling for `import_csv` form submission:
- Parse uploaded CSV file
- Validate "token" column exists
- Validate each token (min 8 chars)
- Call `token_store.import_tokens()`
- Show success/error message via `api.portal.show_message()`

### Step 3: Update Template with Import Form
**File**: `src/zopyx/surveyjs/browser/token_store.pt`

Add new section in the tv-action-grid:
```html
<!-- Import Section -->
<div class="tv-import">
  <h3>Import Tokens from CSV</h3>
  <form method="post" class="tv-form" enctype="multipart/form-data">
    <input type="file" name="csv_file" accept=".csv" required />
    <button type="submit" name="import_csv" class="tv-btn tv-btn-secondary">Import</button>
  </form>
</div>
```

### Step 4: Add Tests
**File**: `src/zopyx/surveyjs/browser/tests/test_token_store_view.py`

Add tests for:
- Valid CSV import with tokens
- Invalid CSV (missing token column)
- Invalid tokens (too short)
- Duplicate token handling
- Empty CSV file

## Validation Rules

| Rule | Description | Error Message |
|------|-------------|---------------|
| Column exists | CSV must have "token" column | "CSV must contain a 'token' column" |
| Token length | Each token >= 8 characters | "Token at row N is too short (min 8 chars)" |
| File type | Must be text/csv or text/plain | "Invalid file type. Please upload a CSV file" |
| Empty file | File must not be empty | "CSV file is empty" |

## Success Behavior

On successful import:
1. All valid tokens are stored with `created` timestamp
2. Duplicate tokens are skipped (not an error)
3. Message: "{count} token(s) imported successfully"
4. Page redirects to refresh stats

## UI Layout

The import form will be added to the existing `tv-action-grid`, creating a 3-column layout:
- Column 1: Generate New Tokens
- Column 2: Export & Manage  
- Column 3: Import Tokens from CSV

## CSS Considerations

The import form will reuse existing CSS classes:
- `.tv-form` - Form styling
- `.tv-btn-secondary` - Button styling
- File input will use default browser styling (consistent with existing UI)
