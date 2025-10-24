# Website Image Monitor

AWS Lambda function that monitors multiple pages on my website for broken images and sends email alerts via Amazon SES. If an image is referenced by IP address or cannot be retrieved (status != 2xx) then it will send me an email with results aggregated across all checked pages.

## Overview

This Lambda function performs the following tasks:
- Fetches and parses multiple pages from a target website in parallel
- Scans for images hosted on a specific IP address
- Tests image URLs for accessibility across all pages
- Sends a single summary email when broken images or IP-based images are detected
- Continues checking all pages even if some fail
- Notifies when the monitoring script encounters errors

## Configuration

Update the following constants in `src/website_check/lambda_function.py`:

```python
TARGET_IP = "3.23.206.196"        # IP address to monitor
WEBSITE_URL = "https://www.keithfry.net"  # Base website URL
PAGES_TO_CHECK = [                # List of page paths to check
    "/",
    "/resume",
    "/services/",
    "/maker/",
]
SENDER_EMAIL = <from_email>       # SES verified sender
RECIPIENT_EMAIL = <to_email>      # Alert recipient
AWS_REGION = "us-east-2"          # AWS region for SES
```

## Dependencies

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

Dependencies are defined in `pyproject.toml`:
- `boto3` - AWS SDK for Python
- `requests` - HTTP library for fetching pages and checking images
- `beautifulsoup4` - HTML parser for extracting image tags
- `concurrent.futures` - ThreadPoolExecutor for parallel page checking (built-in, Python 3.2+)

### Setup with uv

Install dependencies:
```bash
uv sync
```

Run with uv:
```bash
uv run python -m website_check.lambda_function
```

## Local Testing

You can test the Lambda function locally using boto3 and your AWS credentials.

### Prerequisites

1. **Install AWS CLI and configure credentials**:
   ```bash
   aws configure
   ```
   This creates `~/.aws/credentials` with your AWS access keys.

2. **Or set environment variables**:
   ```bash
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=us-east-2
   ```

### Running Tests

1. **Copy environment template**:
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` file** (optional):
   - Set `DRY_RUN=true` to prevent sending actual SES emails (recommended for testing)
   - Override AWS credentials if needed
   - Customize configuration values

3. **Run the test script**:
   ```bash
   uv run python test_lambda.py
   ```

### Test Modes

**Dry Run Mode** (default in `.env.example`):
```bash
DRY_RUN=true uv run python test_lambda.py
```
- Scans the website and checks images
- Shows what emails would be sent without actually sending them
- Safe for testing

**Live Mode** (sends real emails):
```bash
DRY_RUN=false uv run python test_lambda.py
```
- Actually sends SES emails
- Requires verified SES email addresses
- Use with caution

## AWS Setup

### Lambda Configuration

**Recommended Settings:**
- **Timeout**: 60 seconds (increased from default 3 seconds to handle multi-page checking)
- **Memory**: 128 MB (default is sufficient)

To update timeout via AWS CLI:
```bash
aws lambda update-function-configuration \
  --function-name check-my-website \
  --region us-east-2 \
  --timeout 60
```

Or update via AWS Console:
1. Go to Lambda Console → Functions → check-my-website
2. Navigate to **Configuration** → **General configuration**
3. Click **Edit**
4. Set **Timeout** to 60 seconds
5. Click **Save**

### IAM Permissions

The Lambda function requires the following IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

### Amazon SES Setup

1. Verify the sender email address in Amazon SES
2. If in SES sandbox, verify the recipient email address
3. Request production access for unrestricted sending

## Deployment

### Quick Deploy (Recommended)

Use the automated deployment script:

```bash
./deploy.sh
```

This script will:
- Install all dependencies with uv
- Package the Lambda function
- Deploy to AWS Lambda (`check-my-website` in `us-east-2`)
- Optionally test the deployed function
- Clean up build artifacts

**Prerequisites**: AWS CLI configured with valid credentials

### Manual Deployment

If you prefer to deploy manually:

1. Install dependencies:
   ```bash
   uv pip install --python 3.13 --target ./package boto3 requests beautifulsoup4
   ```

2. Copy Lambda function to package:
   ```bash
   cp src/website_check/lambda_function.py ./package/
   ```

3. Create deployment package:
   ```bash
   cd package && zip -r ../function.zip . && cd ..
   ```

4. Deploy to AWS:
   ```bash
   aws lambda update-function-code \
     --function-name check-my-website \
     --region us-east-2 \
     --zip-file fileb://function.zip
   ```

### Using AWS Console

1. Run `./deploy.sh` or create `function.zip` manually
2. Go to AWS Lambda Console → Functions → check-my-website
3. Click "Upload from" → ".zip file"
4. Select `function.zip`
5. Click "Save"

## Scheduling

Set up an EventBridge (CloudWatch Events) rule to trigger the function:
- **Rate expression**: `rate(1 hour)` - runs every hour
- **Cron expression**: `cron(0 * * * ? *)` - runs at the top of every hour

## Return Values

The function returns JSON responses with aggregated results from all checked pages:

### Success - Multi-page scan complete
```json
{
  "statusCode": 200,
  "body": {
    "status": "COMPLETE",
    "pages_checked": 4,
    "pages_failed": 0,
    "total_broken_images": 2,
    "total_ip_images": 0
  }
}
```

**Response Fields:**
- `status`: `COMPLETE` when scan finishes (even if some pages fail)
- `pages_checked`: Total number of pages attempted
- `pages_failed`: Number of pages that failed to load
- `total_broken_images`: Total broken images found across all pages
- `total_ip_images`: Total images using the target IP across all pages

**Email Behavior:**
- Email is sent only if: broken images found, IP-based images found, or pages failed
- Email contains results grouped by page with summary statistics
- No email is sent if all pages check successfully with no issues

### Error - Lambda execution failure
```json
{
  "statusCode": 500,
  "body": {
    "status": "ERROR",
    "message": "Error description"
  }
}
```

**Note:** Individual page failures (404, timeout, etc.) are captured in the success response with `pages_failed` > 0. The error response is only returned if the Lambda function itself encounters an unexpected error.

## Monitoring

### CloudWatch Logs

View real-time logs from your Lambda function:

```bash
# Tail logs (live streaming)
aws logs tail /aws/lambda/check-my-website --follow

# View recent logs
aws logs tail /aws/lambda/check-my-website --since 1h

# View logs from specific time range
aws logs tail /aws/lambda/check-my-website --since 2025-01-01T00:00:00 --until 2025-01-01T23:59:59
```

### AWS Console

1. Go to [CloudWatch Console](https://console.aws.amazon.com/cloudwatch/)
2. Navigate to **Logs** → **Log groups**
3. Find `/aws/lambda/check-my-website`
4. View execution details, scan results, image counts, and error messages

### What You'll See in Logs

- Parallel page checking initiation (e.g., "Checking 4 pages in parallel...")
- Individual page scan start/completion for each URL
- Number of images found per page
- IP-based image detections per page
- Broken image alerts per page
- Email sending confirmations with summary
- Page-level errors (404, timeouts, etc.)
- Lambda execution errors (if any)

## License

MIT
