#!/bin/bash

# Change to docker directory
cd docker

# Run docker-compose with provided arguments or default to 'up'
if [ "$1" == "rebuild" ]; then
  docker-compose build --no-cache
  shift
fi

if [ $# -eq 0 ]; then
  docker-compose up
else
  docker-compose "$@"
fi 