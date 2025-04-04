#!/bin/bash
set -e

# Navigate to the EPG directory
cd /app/epg

# Run the EPG grabber with the custom channels file
npm run grab --- --channels=/app/home-epg/my_channels/channels_IN.xml --output=/app/home-epg/export_epg/IN_guide.xml

# Run with test channels
#npm run grab --- --channels=/app/home-epg/my_channels/test_channels.xml --output=/app/home-epg/export_epg/test_guide.xml

# Navigate to the home-epg directory
cd /app/home-epg

# Configure git to use credentials if provided
if [ -n "$GIT_USERNAME" ] && [ -n "$GIT_PASSWORD" ]; then
    git config credential.helper '!f() { echo "username='$GIT_USERNAME'"; echo "password='$GIT_PASSWORD'"; }; f'
fi

# Get today's date for the commit message
TODAY=$(date +"%Y-%m-%d")

# Stage only the files in export_epg directory
git add export_epg/

# Commit and push changes
git commit -m "EPG update: $TODAY" || echo "No changes to commit"
git push origin master

echo "EPG update completed successfully!" 