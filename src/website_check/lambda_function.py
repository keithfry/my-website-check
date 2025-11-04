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
    Check a single page for images and CSS files.
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

        # Check CSS files for URLs with target IP
        css_urls = extract_css_links(soup, page_url)
        print(f"Found {len(css_urls)} local CSS files to check")

        css_ip_urls = []
        css_broken_urls = []

        for css_url in css_urls:
            css_result = check_css_file(css_url)
            css_ip_urls.extend(css_result['ip_urls'])
            css_broken_urls.extend(css_result['broken_urls'])

        return {
            'url': page_url,
            'status': 'success',
            'total_images': len(images),
            'ip_images': ip_images,
            'broken_images': broken_images,
            'css_files_checked': len(css_urls),
            'css_ip_urls': css_ip_urls,
            'css_broken_urls': css_broken_urls,
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
            'css_files_checked': 0,
            'css_ip_urls': [],
            'css_broken_urls': [],
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
        total_css_broken = sum(len(r['css_broken_urls']) for r in all_results)
        total_css_ip = sum(len(r['css_ip_urls']) for r in all_results)
        failed_pages = sum(1 for r in all_results if r['status'] == 'error')

        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'COMPLETE',
                'pages_checked': len(all_results),
                'pages_failed': failed_pages,
                'total_broken_images': total_broken,
                'total_ip_images': total_ip_images,
                'total_css_broken_urls': total_css_broken,
                'total_css_ip_urls': total_css_ip
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

def extract_css_links(soup, page_url):
    """
    Extract CSS file URLs from HTML that belong to the same domain.
    Returns list of absolute CSS file URLs.
    """
    css_urls = []
    link_tags = soup.find_all('link', rel='stylesheet')

    for link in link_tags:
        href = link.get('href', '')
        if not href:
            continue

        # Convert to absolute URL
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = WEBSITE_URL.rstrip('/') + href
        elif not href.startswith('http'):
            # Relative path - construct from page URL
            base_url = page_url.rsplit('/', 1)[0]
            href = base_url + '/' + href

        # Only include CSS from our domain
        if href.startswith(WEBSITE_URL):
            css_urls.append(href)
            print(f"Found local CSS file: {href}")

    return css_urls

def check_css_file(css_url):
    """
    Fetch CSS file and check for URLs containing target IP.
    Returns dict with ip_urls and broken_urls found in the CSS.
    """
    try:
        print(f"Checking CSS file: {css_url}")
        response = requests.get(css_url, timeout=10)
        response.raise_for_status()
        css_content = response.text

        # Extract all url(...) patterns from CSS
        # Matches: url("..."), url('...'), url(...)
        url_pattern = r'url\(["\']?([^"\'()]+)["\']?\)'
        matches = re.findall(url_pattern, css_content)

        print(f"Found {len(matches)} URL references in CSS")

        ip_urls = []
        broken_urls = []

        for url in matches:
            url = url.strip()

            # Check if URL contains target IP
            if TARGET_IP in url:
                ip_urls.append(url)
                print(f"Found URL with target IP in CSS: {url}")

            # Check if URL is broken (only check image-like URLs)
            if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']):
                if is_image_broken(url):
                    broken_urls.append(url)
                    print(f"CSS URL is BROKEN: {url}")

        return {
            'ip_urls': ip_urls,
            'broken_urls': broken_urls
        }

    except Exception as e:
        print(f"Error checking CSS file {css_url}: {str(e)}")
        return {
            'ip_urls': [],
            'broken_urls': []
        }

def send_summary_email(all_results):
    """
    Send single summary email aggregating results from all pages.
    """
    # Aggregate results
    total_pages = len(all_results)
    successful_pages = sum(1 for r in all_results if r['status'] == 'success')
    failed_pages = [r for r in all_results if r['status'] == 'error']
    total_images = sum(r['total_images'] for r in all_results if r['status'] == 'success')
    total_css_files = sum(r['css_files_checked'] for r in all_results if r['status'] == 'success')

    # Group broken images by page
    pages_with_broken = [r for r in all_results if r['status'] == 'success' and r['broken_images']]
    total_broken = sum(len(r['broken_images']) for r in pages_with_broken)

    # Group IP images by page
    pages_with_ip = [r for r in all_results if r['status'] == 'success' and r['ip_images']]
    total_ip = sum(len(r['ip_images']) for r in pages_with_ip)

    # Group CSS broken URLs by page
    pages_with_css_broken = [r for r in all_results if r['status'] == 'success' and r['css_broken_urls']]
    total_css_broken = sum(len(r['css_broken_urls']) for r in pages_with_css_broken)

    # Group CSS IP URLs by page
    pages_with_css_ip = [r for r in all_results if r['status'] == 'success' and r['css_ip_urls']]
    total_css_ip = sum(len(r['css_ip_urls']) for r in pages_with_css_ip)

    # Only send email if there are issues
    if not (pages_with_broken or pages_with_ip or pages_with_css_broken or pages_with_css_ip or failed_pages):
        print("No issues found across all pages. Skipping email.")
        return

    # Build subject
    issues = []
    if pages_with_broken:
        issues.append(f"{total_broken} Broken Images")
    if pages_with_ip:
        issues.append(f"{total_ip} IP-Based Images")
    if pages_with_css_broken:
        issues.append(f"{total_css_broken} CSS Broken URLs")
    if pages_with_css_ip:
        issues.append(f"{total_css_ip} CSS IP-Based URLs")
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
- Total CSS Files Checked: {total_css_files}
- Broken Images Found: {total_broken}
- IP-Based Images Found: {total_ip}
- CSS Broken URLs Found: {total_css_broken}
- CSS IP-Based URLs Found: {total_css_ip}

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

    if pages_with_css_broken:
        body_text += "\n=== CSS BROKEN URLs ===\n\n"
        for result in pages_with_css_broken:
            body_text += f"Page: {result['url']}\n"
            for url in result['css_broken_urls']:
                body_text += f"  - {url}\n"
            body_text += "\n"

    if pages_with_css_ip:
        body_text += "\n=== CSS IP-BASED URLs ===\n\n"
        for result in pages_with_css_ip:
            body_text += f"Page: {result['url']}\n"
            for url in result['css_ip_urls']:
                body_text += f"  - {url}\n"
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
            <li>Total CSS Files Checked: {total_css_files}</li>
            <li style="color: #d9534f;"><strong>Broken Images Found: {total_broken}</strong></li>
            <li style="color: #f0ad4e;"><strong>IP-Based Images Found: {total_ip}</strong></li>
            <li style="color: #d9534f;"><strong>CSS Broken URLs Found: {total_css_broken}</strong></li>
            <li style="color: #f0ad4e;"><strong>CSS IP-Based URLs Found: {total_css_ip}</strong></li>
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

    if pages_with_css_broken:
        body_html += """
        <h3 style="color: #d9534f;">CSS Broken URLs</h3>
"""
        for result in pages_with_css_broken:
            body_html += f"""
        <h4>{result['url']}</h4>
        <ul>
            {''.join(f'<li><code>{url}</code></li>' for url in result['css_broken_urls'])}
        </ul>
"""

    if pages_with_css_ip:
        body_html += """
        <h3 style="color: #f0ad4e;">CSS IP-Based URLs</h3>
"""
        for result in pages_with_css_ip:
            body_html += f"""
        <h4>{result['url']}</h4>
        <ul>
            {''.join(f'<li><code>{url}</code></li>' for url in result['css_ip_urls'])}
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