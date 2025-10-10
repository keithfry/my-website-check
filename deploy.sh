#!/bin/bash
#
# Lambda Deployment Script
# Packages and deploys the website checker Lambda function to AWS
#

set -e  # Exit on error

# Configuration
FUNCTION_NAME="check-my-website"
REGION="us-east-2"
PYTHON_VERSION="3.13"
SOURCE_FILE="src/website_check/lambda_function.py"
PACKAGE_DIR="package"
ZIP_FILE="function.zip"

echo "=========================================="
echo "Lambda Deployment Script"
echo "=========================================="
echo "Function: $FUNCTION_NAME"
echo "Region: $REGION"
echo "Python: $PYTHON_VERSION"
echo ""

# Clean up previous build artifacts
echo "🧹 Cleaning up previous build artifacts..."
rm -rf "$PACKAGE_DIR" "$ZIP_FILE"

# Create package directory
echo "📦 Creating package directory..."
mkdir -p "$PACKAGE_DIR"

# Install dependencies
echo "📥 Installing dependencies with uv..."
uv pip install --python "$PYTHON_VERSION" --target "./$PACKAGE_DIR" \
    boto3 \
    requests \
    beautifulsoup4

# Copy Lambda function
echo "📄 Copying Lambda function..."
cp "$SOURCE_FILE" "./$PACKAGE_DIR/"

# Create deployment package
echo "🗜️  Creating deployment package..."
cd "$PACKAGE_DIR"
zip -r "../$ZIP_FILE" . -q -x "*.pyc" -x "*__pycache__*"
cd ..

# Get package size
PACKAGE_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "✅ Package created: $ZIP_FILE ($PACKAGE_SIZE)"
echo ""

# Deploy to AWS Lambda
echo "🚀 Deploying to AWS Lambda..."
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --zip-file "fileb://$ZIP_FILE" \
    --output json \
    > /dev/null

# Wait for deployment to complete
echo "⏳ Waiting for deployment to complete..."
sleep 3

# Check deployment status
STATUS=$(aws lambda get-function \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --query 'Configuration.[State,LastUpdateStatus]' \
    --output text)

echo "📊 Deployment Status: $STATUS"

if [[ "$STATUS" == *"Active"*"Successful"* ]]; then
    echo "✅ Deployment successful!"
    echo ""

    # Optional: Test the function
    read -p "Do you want to test the function? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🧪 Testing Lambda function..."
        aws lambda invoke \
            --function-name "$FUNCTION_NAME" \
            --region "$REGION" \
            --payload '{}' \
            --cli-binary-format raw-in-base64-out \
            response.json \
            > /dev/null

        echo "📝 Test Response:"
        cat response.json | python3 -m json.tool
        rm response.json
    fi
else
    echo "❌ Deployment may have failed. Check AWS Console for details."
    exit 1
fi

echo ""
echo "🎉 Done!"
echo ""

# Optional: Clean up
read -p "Do you want to clean up build artifacts? (Y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "🧹 Cleaning up..."
    rm -rf "$PACKAGE_DIR" "$ZIP_FILE"
    echo "✅ Cleanup complete!"
fi

echo ""
echo "=========================================="
echo "View logs: aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
echo "=========================================="
