# Website Image Monitor

AWS Lambda function that monitors a website for broken images hosted on a specific IP address and sends email alerts via Amazon SES.

## Overview

This Lambda function performs the following tasks:
- Fetches and parses a target website
- Scans for images hosted on a specific IP address
- Tests image URLs for accessibility
- Sends email alerts when broken images are detected
- Notifies when the monitoring script encounters errors

## Configuration

Update the following constants in `lambda_function.py`:

```python
TARGET_IP = "3.23.206.196"        # IP address to monitor
WEBSITE_URL = "https://www.keithfry.net"  # Website to scan
SENDER_EMAIL = <from_email>       # SES verified sender
RECIPIENT_EMAIL = <to_email>      # Alert recipient
AWS_REGION = "us-east-2"          # AWS region for SES
```

## Dependencies

- `boto3` - AWS SDK for Python (included in Lambda runtime)
- `requests` - HTTP library
- `beautifulsoup4` - HTML parser
- `botocore` - AWS low-level client library

Install dependencies with:
```bash
pip install -r requirements.txt -t .
```

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

1. Package dependencies:
   ```bash
   pip install requests beautifulsoup4 -t .
   ```

2. Create deployment package:
   ```bash
   zip -r function.zip .
   ```

3. Upload to AWS Lambda or use AWS SAM/CloudFormation

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

Check CloudWatch Logs for execution details:
- Log group: `/aws/lambda/<function-name>`
- View scan results, image counts, and error messages

## License

MIT


## Improvements
1. Make a CloudFormation script to deploy