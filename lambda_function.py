import json
import boto3
import requests
from bs4 import BeautifulSoup
import re
from botocore.exceptions import ClientError

# Configuration
TARGET_IP = "3.23.206.196"
WEBSITE_URL = "https://www.keithfry.net"
SENDER_EMAIL = "alerts@keithfry.net"
RECIPIENT_EMAIL = "keithfry@gmail.com"
AWS_REGION = "us-east-2"

ses_client = boto3.client('ses', region_name=AWS_REGION)

def lambda_handler(event, context):
    """
    Main Lambda handler function.
    Scans website for images using specific IP address and sends alert if broken.
    """
    try:
        print(f"Starting scan of {WEBSITE_URL}")
        
        # Fetch the webpage
        response = requests.get(WEBSITE_URL, timeout=10)
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
        
        # Report results
        if ip_images or broken_images:
            # Send alert email
            send_alert_email(broken_images, ip_images)
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'ALERT_SENT',
                    'message': f'Found {len(broken_images)} broken images out of {len(ip_images)} IP-based images',
                    'broken_images': broken_images
                })
            }
        else:
            print(f"No images found with IP address {TARGET_IP} or broken images")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'NO_IP_IMAGES',
                    'message': f'No images found with IP {TARGET_IP} or broken images'
                })
            }
            
    except requests.RequestException as e:
        error_msg = f"Error fetching website: {str(e)}"
        print(error_msg)
        send_error_email(error_msg)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'ERROR',
                'message': error_msg
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

def send_alert_email(broken_images, all_ip_images):
    """
    Send email alert via Amazon SES when broken images are detected.
    """
    subject = f"⚠️ Website Alert: Broken Images Detected on {WEBSITE_URL}"
    
    body_text = f"""
Website Monitoring Alert

Website: {WEBSITE_URL}
Target IP: {TARGET_IP}

BROKEN IMAGES FOUND: {len(broken_images)} out of {len(all_ip_images)} IP-based images are broken.

Broken Image URLs:
{chr(10).join('- ' + img for img in broken_images)}

All IP-based Images:
{chr(10).join('- ' + img for img in all_ip_images)}

Please check the website and fix the broken image references.

---
This is an automated alert from your AWS Lambda monitoring function.
"""
    
    body_html = f"""
    <html>
    <head></head>
    <body>
        <h2 style="color: #d9534f;">⚠️ Website Monitoring Alert</h2>
        <p><strong>Website:</strong> {WEBSITE_URL}</p>
        <p><strong>Target IP:</strong> {TARGET_IP}</p>
        
        <p style="color: #d9534f; font-weight: bold;">
            BROKEN IMAGES FOUND: {len(broken_images)} out of {len(all_ip_images)} IP-based images are broken.
        </p>
        
        <h3>Broken Image URLs:</h3>
        <ul>
            {''.join(f'<li><code>{img}</code></li>' for img in broken_images)}
        </ul>
        
        <h3>All IP-based Images:</h3>
        <ul>
            {''.join(f'<li><code>{img}</code></li>' for img in all_ip_images)}
        </ul>
        
        <p>Please check the website and fix the broken image references.</p>
        
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
        print(f"Alert email sent successfully. Message ID: {response['MessageId']}")
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