# Offline Installation Guide

## Prerequisites
1. Python 3.8 or higher installed on the computer
2. pip (Python package installer)

## Installation Steps

### 1. Copy Application Files
Copy the entire application folder to the target computer.

### 2. Install Required Packages
On a computer with internet access:
1. Download all required packages:
   ```
   pip download -r requirements.txt -d ./packages
   ```
2. Copy the `packages` folder to the target computer
3. On the target computer, install the packages:
   ```
   pip install --no-index --find-links ./packages -r requirements.txt
   ```

### 3. Initialize the Application
1. Open a terminal/command prompt
2. Navigate to the application folder
3. Run the following command to start the application:
   ```
   python app.py
   ```
4. Access the application at `http://localhost:5000`

### 4. First-time Setup
1. Create an admin user when first running the application
2. Configure company details and receipt templates
3. Add necessary customer information

## Printing Receipts
1. Navigate to Transactions
2. Click on the receipt you want to print
3. Click the "Print Receipt" button
4. Select your printer in the browser print dialog

## Troubleshooting
- If the application fails to start, ensure all packages are properly installed
- For printing issues, make sure the printer is properly connected and set as default
- The database file (billing.db) will be created automatically on first run