# Website Image Monitor

AWS Lambda function that monitors my website for broken images and sends email alerts via Amazon SES. If the image is referenced by IP address or cannot be retrieved (status != 2xx) then it will send me an email.

## Overview

This Lambda function performs the following tasks:
- Fetches and parses a target website
- Scans for images hosted on a specific IP address
- Tests image URLs for accessibility
- Sends email alerts when broken images are detected
- Notifies when the monitoring script encounters errors

## Configuration

Update the following constants in `src/website_check/lambda_function.py`:

```python
TARGET_IP = "3.23.206.196"        # IP address to monitor
WEBSITE_URL = "https://www.keithfry.net"  # Website to scan
SENDER_EMAIL = <from_email>       # SES verified sender
RECIPIENT_EMAIL = <to_email>      # Alert recipient
AWS_REGION = "us-east-2"          # AWS region for SES
```

## Dependencies

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

Dependencies are defined in `pyproject.toml`:
- `boto3` - AWS SDK for Python
- `requests` - HTTP library
- `beautifulsoup4` - HTML parser

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

The function returns JSON responses:

### Success - All images working
```json
{
  "statusCode": 200,
  "body": {
    "status": "OK",
    "message": "Found 5 IP-based images, all working",
    "images": ["..."]
  }
}
```

### Success - Broken images found
```json
{
  "statusCode": 200,
  "body": {
    "status": "ALERT_SENT",
    "message": "Found 2 broken images out of 5 IP-based images",
    "broken_images": ["..."]
  }
}
```

### Error
```json
{
  "statusCode": 500,
  "body": {
    "status": "ERROR",
    "message": "Error description"
  }
}
```

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

- Website scan start/completion
- Number of images found
- IP-based image detections
- Broken image alerts
- Email sending confirmations
- Error messages (if any)

## License

MIT
