FROM node:18

# Install git and other dependencies
RUN apt-get update && apt-get install -y \
    git \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Clone the repositories
RUN git clone --depth 1 -b master https://github.com/iptv-org/epg.git && \
    git clone https://github.com/ishanshekhar/home-epg.git

# Install dependencies for the EPG repo
WORKDIR /app/epg
RUN npm install

# Set up git configuration for commits
RUN git config --global user.email "docker@example.com" && \
    git config --global user.name "Docker EPG Bot"

# Copy the entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"] 