#!/usr/bin/env python3
"""
Local test runner for the Lambda function.
This script allows you to test the Lambda function locally with your AWS credentials.
"""

import os
import sys
import json
from pathlib import Path

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment from {env_file}")
except ImportError:
    pass  # dotenv not installed, skip

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from website_check.lambda_function import lambda_handler


class MockLambdaContext:
    """Mock AWS Lambda context object for local testing."""

    def __init__(self):
        self.function_name = "website-monitor-local"
        self.function_version = "$LATEST"
        self.invoked_function_arn = "arn:aws:lambda:us-east-2:123456789012:function:website-monitor-local"
        self.memory_limit_in_mb = 128
        self.aws_request_id = "local-test-request-id"
        self.log_group_name = "/aws/lambda/website-monitor-local"
        self.log_stream_name = "local-test-stream"

    def get_remaining_time_in_millis(self):
        """Return mock remaining time."""
        return 300000  # 5 minutes


def main():
    """Run the Lambda function locally."""
    print("=" * 80)
    print("Local Lambda Function Test Runner")
    print("=" * 80)
    print()

    # Check for AWS credentials
    has_credentials = (
        os.environ.get('AWS_ACCESS_KEY_ID') or
        os.path.exists(os.path.expanduser('~/.aws/credentials'))
    )

    if not has_credentials:
        print("⚠️  WARNING: No AWS credentials found!")
        print("   Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables")
        print("   OR configure credentials in ~/.aws/credentials")
        print()
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Exiting...")
            sys.exit(1)
        print()

    # Check for dry-run mode
    dry_run = os.environ.get('DRY_RUN', '').lower() in ('true', '1', 'yes')

    if dry_run:
        print("🔵 DRY RUN MODE: SES emails will not be sent")
        print()
        # Monkey-patch SES client to prevent actual emails
        import website_check.lambda_function as lambda_module
        original_send_email = lambda_module.ses_client.send_email

        def mock_send_email(*args, **kwargs):
            print("📧 [DRY RUN] Would send email:")
            if 'Message' in kwargs:
                print(f"   Subject: {kwargs['Message']['Subject']['Data']}")
                print(f"   To: {kwargs['Destination']['ToAddresses']}")
            return {'MessageId': 'dry-run-message-id'}

        lambda_module.ses_client.send_email = mock_send_email

    # Create mock event and context
    event = {}
    context = MockLambdaContext()

    print("Starting Lambda function execution...")
    print("-" * 80)
    print()

    try:
        # Execute the Lambda handler
        result = lambda_handler(event, context)

        # Display results
        print()
        print("-" * 80)
        print("Lambda Function Execution Complete")
        print("=" * 80)
        print()
        print(f"Status Code: {result['statusCode']}")
        print()
        print("Response Body:")
        body = json.loads(result['body'])
        print(json.dumps(body, indent=2))

        # Exit with appropriate code
        sys.exit(0 if result['statusCode'] == 200 else 1)

    except Exception as e:
        print()
        print("-" * 80)
        print("Lambda Function Execution Failed")
        print("=" * 80)
        print()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
