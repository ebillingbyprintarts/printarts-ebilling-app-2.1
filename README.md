# Billing System - Online Deployment Guide

## Overview
This is a Flask-based billing system that can be deployed online using GitHub and Render.

## Prerequisites
- GitHub account
- Render account (sign up at https://render.com)
- Python 3.8 or higher

## Deployment Steps

### 1. GitHub Setup
1. Create a new repository on GitHub
2. Initialize git in your local project:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```
3. Add your GitHub repository as remote and push:
   ```bash
   git remote add origin your-github-repo-url
   git push -u origin main
   ```

### 2. Render Setup
1. Log in to your Render account
2. Click "New +" and select "Web Service"
3. Connect your GitHub repository
4. Configure the service:
   - Name: billing-system (or your preferred name)
   - Environment: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`

### 3. Environment Variables
Set the following environment variables in Render:
- `SECRET_KEY`: A secure random string
- `DATABASE_URL`: Your database connection string (Render will provide this if using their managed PostgreSQL)

### 4. Database Setup
Render provides PostgreSQL databases:
1. Create a new PostgreSQL database in Render
2. The `DATABASE_URL` will be automatically added to your web service

## Development vs Production
- Development: Uses SQLite database locally
- Production: Uses PostgreSQL database on Render

## Monitoring
- View logs in Render dashboard
- Monitor application performance and errors
- Set up alerts for service status

## Maintenance
To update the application:
1. Make changes locally
2. Commit and push to GitHub
3. Render will automatically deploy updates

## Security Notes
- Never commit sensitive data or environment variables
- Use environment variables for all secrets
- Keep dependencies updated