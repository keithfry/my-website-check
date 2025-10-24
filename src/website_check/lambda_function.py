import json
import boto3
import requests
from bs4 import BeautifulSoup
import re
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
TARGET_IP = "3.23.206.196"
WEBSITE_URL = "https://www.keithfry.net"
PAGES_TO_CHECK = [
    "/",
    "/resume",
    "/services/",
    "/maker/",
]
SENDER_EMAIL = "alerts@keithfry.net"
RECIPIENT_EMAIL = "keithfry@gmail.com"
AWS_REGION = "us-east-2"

ses_client = boto3.client('ses', region_name=AWS_REGION)

def check_page(page_url):
    """
    Check a single page for images.
    Returns dict with page results.
    """
    try:
        print(f"Starting scan of {page_url}")

        # Fetch the webpage
        headers = {
            "X-Agent": "aws-lambda"
        }
        response = requests.get(page_url, timeout=10, headers=headers)
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all image tags
        images = soup.find_all('img')
        print(f"Found {len(images)} total images on page")

        # Look for images with the target IP
        broken_images = []
        ip_images = []

        for img in images:
            src = img.get('src', '')

            # Check if the image source contains the target IP
            if TARGET_IP in src:
                ip_images.append(src)
                print(f"Found image with target IP: {src}")

            # Test if the image is broken
            if is_image_broken(src):
                broken_images.append(src)
                print(f"Image is BROKEN: {src}")
            else:
                print(f"Image is accessible: {src}")

        return {
            'url': page_url,
            'status': 'success',
            'total_images': len(images),
            'ip_images': ip_images,
            'broken_images': broken_images,
            'error': None
        }

    except Exception as e:
        error_msg = f"Error checking page {page_url}: {str(e)}"
        print(error_msg)
        return {
            'url': page_url,
            'status': 'error',
            'total_images': 0,
            'ip_images': [],
            'broken_images': [],
            'error': str(e)
        }

def lambda_handler(event, context):
    """
    Main Lambda handler function.
    Scans multiple pages for images using specific IP address and broken images.
    Uses parallel execution to avoid timeouts.
    """
    try:
        all_results = []

        # Build full URLs
        urls_to_check = [WEBSITE_URL.rstrip('/') + page_path for page_path in PAGES_TO_CHECK]

        # Check pages in parallel using ThreadPoolExecutor
        print(f"Checking {len(urls_to_check)} pages in parallel...")
        with ThreadPoolExecutor(max_workers=len(urls_to_check)) as executor:
            # Submit all check_page tasks
            future_to_url = {executor.submit(check_page, url): url for url in urls_to_check}

            # Collect results as they complete
            for future in as_completed(future_to_url):
                result = future.result()
                all_results.append(result)

        # Send summary email with all results
        send_summary_email(all_results)

        # Count totals for response
        total_broken = sum(len(r['broken_images']) for r in all_results)
        total_ip_images = sum(len(r['ip_images']) for r in all_results)
        failed_pages = sum(1 for r in all_results if r['status'] == 'error')

        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'COMPLETE',
                'pages_checked': len(all_results),
                'pages_failed': failed_pages,
                'total_broken_images': total_broken,
                'total_ip_images': total_ip_images
            })
        }

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'ERROR',
                'message': error_msg
            })
        }

def is_image_broken(image_url):
    """
    Check if an image URL returns a valid response.
    Returns True if broken (4xx, 5xx, or connection error).
    """
    try:
        # Handle relative URLs
        if image_url.startswith('//'):
            image_url = 'https:' + image_url
        elif image_url.startswith('/'):
            image_url = WEBSITE_URL.rstrip('/') + image_url
        
        # Make HEAD request to check if image exists
        img_response = requests.head(image_url, timeout=5, allow_redirects=True)
        
        # Check status code
        if img_response.status_code >= 400:
            return True
        
        return False
        
    except requests.RequestException:
        # Any connection error means the image is broken
        return True

def send_summary_email(all_results):
    """
    Send single summary email aggregating results from all pages.
    """
    # Aggregate results
    total_pages = len(all_results)
    successful_pages = sum(1 for r in all_results if r['status'] == 'success')
    failed_pages = [r for r in all_results if r['status'] == 'error']
    total_images = sum(r['total_images'] for r in all_results if r['status'] == 'success')

    # Group broken images by page
    pages_with_broken = [r for r in all_results if r['status'] == 'success' and r['broken_images']]
    total_broken = sum(len(r['broken_images']) for r in pages_with_broken)

    # Group IP images by page
    pages_with_ip = [r for r in all_results if r['status'] == 'success' and r['ip_images']]
    total_ip = sum(len(r['ip_images']) for r in pages_with_ip)

    # Only send email if there are issues
    if not (pages_with_broken or pages_with_ip or failed_pages):
        print("No issues found across all pages. Skipping email.")
        return

    # Build subject
    issues = []
    if pages_with_broken:
        issues.append(f"{total_broken} Broken Images")
    if pages_with_ip:
        issues.append(f"{total_ip} IP-Based Images")
    if failed_pages:
        issues.append(f"{len(failed_pages)} Failed Pages")

    subject = f"⚠️ Website Alert: {', '.join(issues)} Found"

    # Build text body
    body_text = f"""Website Monitoring Alert - Multi-Page Scan

Website: {WEBSITE_URL}
Target IP: {TARGET_IP}

SUMMARY:
- Pages Checked: {total_pages}
- Pages Successful: {successful_pages}
- Pages Failed: {len(failed_pages)}
- Total Images Scanned: {total_images}
- Broken Images Found: {total_broken}
- IP-Based Images Found: {total_ip}

"""

    if pages_with_broken:
        body_text += "\n=== BROKEN IMAGES ===\n\n"
        for result in pages_with_broken:
            body_text += f"Page: {result['url']}\n"
            for img in result['broken_images']:
                body_text += f"  - {img}\n"
            body_text += "\n"

    if pages_with_ip:
        body_text += "\n=== IP-BASED IMAGES ===\n\n"
        for result in pages_with_ip:
            body_text += f"Page: {result['url']}\n"
            for img in result['ip_images']:
                body_text += f"  - {img}\n"
            body_text += "\n"

    if failed_pages:
        body_text += "\n=== FAILED PAGES ===\n\n"
        for result in failed_pages:
            body_text += f"Page: {result['url']}\n"
            body_text += f"Error: {result['error']}\n\n"

    body_text += """
---
This is an automated alert from your AWS Lambda monitoring function.
"""

    # Build HTML body
    body_html = f"""
    <html>
    <head></head>
    <body>
        <h2 style="color: #d9534f;">⚠️ Website Monitoring Alert - Multi-Page Scan</h2>
        <p><strong>Website:</strong> {WEBSITE_URL}</p>
        <p><strong>Target IP:</strong> {TARGET_IP}</p>

        <h3>Summary</h3>
        <ul>
            <li>Pages Checked: {total_pages}</li>
            <li>Pages Successful: {successful_pages}</li>
            <li>Pages Failed: {len(failed_pages)}</li>
            <li>Total Images Scanned: {total_images}</li>
            <li style="color: #d9534f;"><strong>Broken Images Found: {total_broken}</strong></li>
            <li style="color: #f0ad4e;"><strong>IP-Based Images Found: {total_ip}</strong></li>
        </ul>
"""

    if pages_with_broken:
        body_html += """
        <h3 style="color: #d9534f;">Broken Images</h3>
"""
        for result in pages_with_broken:
            body_html += f"""
        <h4>{result['url']}</h4>
        <ul>
            {''.join(f'<li><code>{img}</code></li>' for img in result['broken_images'])}
        </ul>
"""

    if pages_with_ip:
        body_html += """
        <h3 style="color: #f0ad4e;">IP-Based Images</h3>
"""
        for result in pages_with_ip:
            body_html += f"""
        <h4>{result['url']}</h4>
        <ul>
            {''.join(f'<li><code>{img}</code></li>' for img in result['ip_images'])}
        </ul>
"""

    if failed_pages:
        body_html += """
        <h3 style="color: #333;">Failed Pages</h3>
"""
        for result in failed_pages:
            body_html += f"""
        <h4>{result['url']}</h4>
        <p style="color: #d9534f;">{result['error']}</p>
"""

    body_html += """
        <hr>
        <p style="font-size: 12px; color: #666;">
            This is an automated alert from your AWS Lambda monitoring function.
        </p>
    </body>
    </html>
    """

    try:
        response = ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={
                'ToAddresses': [RECIPIENT_EMAIL]
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': body_text,
                        'Charset': 'UTF-8'
                    },
                    'Html': {
                        'Data': body_html,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        print(f"Summary email sent successfully. Message ID: {response['MessageId']}")
    except ClientError as e:
        print(f"Error sending email: {e.response['Error']['Message']}")

def send_error_email(error_message):
    """
    Send email notification when the monitoring script itself encounters an error.
    """
    subject = f"❌ Website Monitor Error: {WEBSITE_URL}"
    
    body_text = f"""
Website Monitoring Error

Website: {WEBSITE_URL}

The monitoring script encountered an error:

{error_message}

Please check the Lambda function logs for more details.

---
This is an automated alert from your AWS Lambda monitoring function.
"""
    
    try:
        ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={
                'ToAddresses': [RECIPIENT_EMAIL]
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': body_text,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        print(f"Error notification email sent successfully")
    except ClientError as e:
        print(f"Error sending error email: {e.response['Error']['Message']}")