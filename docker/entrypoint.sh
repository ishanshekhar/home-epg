#!/bin/bash
set -e

# Update EPG repository
cd /app/epg
git pull

# Update home-epg repository
cd /app/home-epg
if [ -n "$GIT_USERNAME" ] && [ -n "$GIT_PASSWORD" ]; then
    git config credential.helper '!f() { echo "username='$GIT_USERNAME'"; echo "password='$GIT_PASSWORD'"; }; f'
fi

# Determine default branch
DEFAULT_BRANCH="main"
if git show-ref --verify --quiet refs/heads/master; then
    DEFAULT_BRANCH="master"
fi

git checkout $DEFAULT_BRANCH
git pull origin $DEFAULT_BRANCH

# Create export_epg directory if it doesn't exist
mkdir -p /app/home-epg/export_epg

# Run EPG grabber with optimized settings
echo "Memory settings: $NODE_OPTIONS"
cd /app/epg

# Run each country one at a time with conservative connection settings
echo "Processing India channels..."
npm run grab --- --channels=/app/home-epg/my_channels/channels_IN.xml --output=/app/home-epg/export_epg/epg_IN.xml --maxConnections 6 --timeout 60000

echo "Processing US channels..."
npm run grab --- --channels=/app/home-epg/my_channels/channels_US.xml --output=/app/home-epg/export_epg/epg_US.xml --maxConnections 6 --timeout 60000

echo "Processing UK channels..."
npm run grab --- --channels=/app/home-epg/my_channels/channels_UK.xml --output=/app/home-epg/export_epg/epg_UK.xml --maxConnections 6 --timeout 60000

# Commit and push changes
cd /app/home-epg
git add export_epg/*.xml
TODAY=$(date +"%Y-%m-%d")

# Only commit if there are changes
if ! git diff --cached --quiet; then
    git commit -m "EPG update: $TODAY"
    git push origin $DEFAULT_BRANCH
    echo "Changes committed and pushed successfully"
else
    echo "No changes to commit"
fi

echo "EPG update completed successfully!" 