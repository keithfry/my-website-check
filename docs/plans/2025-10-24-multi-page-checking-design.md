# Multi-Page Website Checking Design

**Date:** 2025-10-24
**Version:** 1.0.0

## Overview

Extend the website checker to monitor multiple pages instead of a single page, while maintaining the existing functionality of checking for images using a specific IP address and detecting broken images.

## Requirements

- Check 5-10 pages per Lambda execution
- Maintain current behavior: check for IP-based images (3.23.206.196) and broken images
- Single summary email with all results aggregated
- Report IP-based images and broken images separately
- Continue checking all pages even if some fail

## Architecture

### Configuration Structure

Separate the base URL from page paths for maintainability:

```python
WEBSITE_URL = "https://www.keithfry.net"
PAGES_TO_CHECK = [
    "/",              # Homepage
    "/about",
    "/projects",
    "/blog",
    # ... more paths
]
TARGET_IP = "3.23.206.196"
```

### Implementation Approach

**Sequential Loop:** Check pages one at a time in order. Simple, predictable execution time, easier to debug.

**Rationale:** For 5-10 pages, sequential checking takes 10-30 seconds, well within Lambda timeout limits. Simplicity trumps marginal performance gains from parallelization.

### Data Flow

```
Lambda Handler
    ↓
Loop over PAGES_TO_CHECK
    ↓
For each path:
    - Construct full URL (WEBSITE_URL + path)
    - Call check_page(url)
    - Collect result dict
    ↓
Aggregate all results
    ↓
Send single summary email
    ↓
Return response
```

### Result Structure

Each `check_page(url)` returns:

```python
{
    'url': 'https://www.keithfry.net/about',
    'status': 'success' | 'error',
    'total_images': 15,
    'ip_images': ['http://3.23.206.196/img1.jpg'],
    'broken_images': ['http://example.com/missing.jpg'],
    'error': None | 'Error message'
}
```

### Code Organization

**Refactored functions:**

1. `lambda_handler(event, context)` - Orchestrates multi-page checking
2. `check_page(url)` - Checks single page (extracted from current lambda_handler)
3. `is_image_broken(url)` - No change (existing function)
4. `send_summary_email(all_results)` - New aggregated reporting
5. `send_error_email(error_msg)` - Kept for Lambda-level errors

## Email Reporting

### Summary Email Structure

**Subject:** `⚠️ Website Alert: Issues Found Across {N} Pages`

**Sections:**

1. **Summary Statistics**
   - Pages checked: N
   - Total images scanned: N
   - Pages with IP-based images: N
   - Pages with broken images: N
   - Failed pages: N

2. **IP-Based Images** (if any)
   - Grouped by page
   - Shows which pages have images using TARGET_IP

3. **Broken Images** (if any)
   - Grouped by page
   - Lists broken image URLs per page

4. **Failed Pages** (if any)
   - Pages that couldn't be fetched
   - Error messages

### Email Trigger Logic

Send email if ANY of:
- Broken images found on any page
- IP-based images found on any page
- Any pages failed to fetch

Skip email only if: all pages checked successfully with no issues found.

## Error Handling

### Page-Level Errors

- If page fetch fails (timeout, 404, DNS error), capture error in result dict
- Continue checking remaining pages
- Include failed pages in email report

### Image-Level Errors

- If individual image check fails, mark as broken (existing behavior)
- Continue checking other images on same page

### Lambda-Level Errors

- Unexpected exceptions in main handler caught and logged
- Return 500 status with error details
- Send error notification email (existing `send_error_email()`)

### Error Isolation

Errors at one level don't cascade:
- Failed page doesn't stop other pages
- Failed image doesn't stop other images on page
- Page errors don't fail entire Lambda execution

## Testing Considerations

- Test with mix of valid/invalid page paths
- Test with pages having various image scenarios:
  - No images
  - All valid images
  - Mix of broken and valid images
  - Images with TARGET_IP
- Test page fetch failures (timeout, 404, DNS)
- Verify email content with multiple pages
- Check Lambda timeout handling (should complete in <1 minute for 10 pages)

## Implementation Notes

- Reuse existing `is_image_broken()` logic
- Reuse existing SES email sending infrastructure
- Maintain existing headers (`X-Agent: aws-lambda`)
- Keep existing timeout values (10s for page fetch, 5s for image checks)
- Preserve existing logging for CloudWatch

## Migration Path

1. Extract current `lambda_handler` logic into `check_page()` function
2. Add `PAGES_TO_CHECK` configuration list
3. Refactor `lambda_handler` to loop over pages
4. Create new `send_summary_email()` aggregation function
5. Update existing email templates for multi-page reporting
6. Test locally with `test_lambda.py`
7. Deploy to Lambda
8. Update version to 1.1.0

## Success Criteria

- Lambda successfully checks all configured pages
- Single email sent with results from all pages
- Email clearly shows which pages have which issues
- Page failures don't prevent checking other pages
- Execution completes within Lambda timeout
- Existing monitoring behavior preserved (IP detection + broken image detection)
