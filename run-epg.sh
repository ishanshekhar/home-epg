#!/bin/bash

# Change to the docker directory
cd docker

# Run the specified docker-compose command or 'up' by default
if [ $# -eq 0 ]; then
  docker-compose up
else
  docker-compose "$@"
fi

# Copy channel files to the docker directory
cp my_channels/channels_IN.xml docker/my_channels/
cp my_channels/test_channels.xml docker/my_channels/ # if it exists 