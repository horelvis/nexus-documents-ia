# GCS Credentials

This directory contains Google Cloud Storage service account credentials.

## Required Files

For the storage service to work properly, you need:

- `nexus-document-ia-04252dae0146.json` - GCS service account key file

## Setup Instructions

1. Download your GCS service account key from Google Cloud Console
2. Place the JSON file in this directory
3. Ensure the filename matches what's configured in docker-compose files

## Security

- This directory is git-ignored for security
- Never commit credential files to version control
- Mount this directory as read-only in Docker containers