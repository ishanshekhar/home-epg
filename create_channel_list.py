#!/usr/bin/env python3
import os
import re
import sys
import xml.etree.ElementTree as ET
import time
import argparse
from urllib.parse import urlparse
import requests
import gzip
import shutil
import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('channel_list_generator')

def download_playlist(url, output_dir="playlist_data", force_download=False):
    """Download M3U playlist from a specified URL, only if existing file is older than 7 days"""
    try:
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get today's date for the filename
        today = datetime.datetime.now()
        date_str = today.strftime("%Y%m%d")
        
        # Create filename with date format
        filename = f"playlist_{date_str}.m3u"
        output_path = os.path.join(output_dir, filename)
        
        # Check if we already have today's file
        if os.path.exists(output_path) and not force_download:
            logger.info(f"Using existing playlist file from today: {output_path}")
            return output_path
        
        # Check for existing files and their age
        if not force_download:
            files = [f for f in os.listdir(output_dir) if f.startswith("playlist_") and f.endswith(".m3u")]
            
            if files:
                # Sort by date (newest first)
                files.sort(reverse=True)
                newest_file = files[0]
                newest_path = os.path.join(output_dir, newest_file)
                
                # Extract date from filename
                try:
                    file_date_str = newest_file.replace("playlist_", "").replace(".m3u", "")
                    file_date = datetime.datetime.strptime(file_date_str, "%Y%m%d")
                    
                    # Check if file is less than 7 days old
                    age = today - file_date
                    if age.days < 7:
                        logger.info(f"Using recent playlist file (less than 7 days old): {newest_path}")
                        return newest_path
                    else:
                        logger.info(f"Existing playlist file is {age.days} days old. Downloading new one.")
                except ValueError:
                    # If we can't parse the date, download a new file
                    logger.info(f"Could not determine age of existing file. Downloading new one.")
        
        logger.info(f"Downloading playlist from {url}...")
        start_time = time.time()
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Save the downloaded file
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        download_time = time.time() - start_time
        logger.info(f"Downloaded to {output_path} in {download_time:.2f} seconds")
        
        # If it's a gzip file, decompress it
        if url.endswith('.gz'):
            decompressed_path = output_path.replace('.gz', '')
            
            logger.info(f"Decompressing {output_path}...")
            start_time = time.time()
            with gzip.open(output_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove the compressed file after decompression
            os.remove(output_path)
            decompress_time = time.time() - start_time
            logger.info(f"Decompressed to {decompressed_path} in {decompress_time:.2f} seconds")
            return decompressed_path
        
        return output_path
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        return None

def load_playlist_channels(file_path, country_prefix=None):
    """Load channels from M3U playlist file with optional country filtering"""
    if not os.path.exists(file_path):
        logger.error(f"Playlist file not found: {file_path}")
        return []
    
    logger.info(f"Loading playlist from {file_path}...")
    start_time = time.time()
    try:
        channels = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        lines = content.splitlines()
        
        # Get TV channels only
        for i in range(len(lines)):
            if lines[i].startswith("#EXTINF"):
                # Get the channel info from current line
                channel_info = lines[i]
                # Extract channel name
                channel_name_match = re.search(r',(.+)$', channel_info)
                if channel_name_match:
                    channel_name = channel_name_match.group(1).strip()
                    
                    # Apply country filter if specified
                    include_channel = True
                    if country_prefix:
                        # Only include channels that start with the prefix
                        include_channel = channel_name.startswith(country_prefix)
                    
                    if include_channel:
                        # Get the URL from the next line
                        if i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                            url = lines[i + 1].strip()
                            # Extract tvg-id if available
                            tvg_id_match = re.search(r'tvg-id="([^"]*)"', channel_info)
                            tvg_id = tvg_id_match.group(1) if tvg_id_match else ""
                            
                            # Clean name (remove country prefix)
                            clean_name = channel_name
                            if country_prefix and channel_name.startswith(country_prefix):
                                clean_name = channel_name[len(country_prefix):].strip()
                            
                            channels.append({
                                'name': channel_name,
                                'clean_name': clean_name,
                                'tvg_id': tvg_id,
                                'info': channel_info,
                                'url': url
                            })
        
        elapsed_time = time.time() - start_time
        if country_prefix:
            logger.info(f"Found {len(channels)} channels with prefix: {country_prefix} in {elapsed_time:.2f} seconds")
        else:
            logger.info(f"Found {len(channels)} channels in playlist in {elapsed_time:.2f} seconds")
        return channels
    except Exception as e:
        logger.error(f"Error loading playlist: {e}")
        return []

def load_channel_mappings(channels_dir):
    """Load channel mappings from XML files in the channels directory"""
    if not os.path.exists(channels_dir):
        logger.error(f"Channels directory not found: {channels_dir}")
        return {}
    
    logger.info(f"Loading channel mappings from {channels_dir}...")
    start_time = time.time()
    
    mappings = {}
    normalized_mappings = {}  # Pre-compute normalized names for faster matching
    
    # Get all XML files in the channels directory
    xml_files = [f for f in os.listdir(channels_dir) if f.endswith('.xml')]
    logger.info(f"Found {len(xml_files)} channel mapping files")
    
    for xml_file in xml_files:
        file_path = os.path.join(channels_dir, xml_file)
        try:
            # Parse the XML file
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Extract site name from filename (e.g., abc.com.channels.xml -> abc.com)
            site_name = xml_file.replace('.channels.xml', '')
            
            # Process each channel element
            channel_count = 0
            for channel in root.findall('.//channel'):
                site_id = channel.get('site_id', '')
                xmltv_id = channel.get('xmltv_id', '')
                lang = channel.get('lang', 'en')
                channel_name = channel.text.strip() if channel.text else ''
                
                if site_id and channel_name:
                    # Create a key for the channel name (normalized for better matching)
                    normalized_name = normalize_channel_name(channel_name)
                    
                    # Store the mapping
                    mapping_data = {
                        'site': site_name,
                        'site_id': site_id,
                        'xmltv_id': xmltv_id,
                        'lang': lang,
                        'original_name': channel_name
                    }
                    
                    mappings[channel_name] = mapping_data
                    normalized_mappings[normalized_name] = mapping_data
                    channel_count += 1
            
            logger.info(f"Loaded {channel_count} channel mappings from {xml_file}")
        except Exception as e:
            logger.error(f"Error loading channel mappings from {file_path}: {e}")
    
    elapsed_time = time.time() - start_time
    logger.info(f"Loaded a total of {len(mappings)} channel mappings in {elapsed_time:.2f} seconds")
    return normalized_mappings

def normalize_channel_name(name):
    """Normalize channel name for better matching"""
    # Convert to uppercase
    name = name.upper()
    
    # Remove common suffixes
    name = re.sub(r'\s+(HD|SD|FHD|UHD|4K|HEVC|H265|H\.265)\b', '', name)
    name = re.sub(r'\s+(CHANNEL|TV|NETWORK)\s*$', '', name)
    
    # Remove punctuation and standardize spacing
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def match_channels(playlist_channels, channel_mappings):
    """Match playlist channels with channel mappings using optimized approach"""
    from concurrent.futures import ThreadPoolExecutor
    
    logger.info(f"Starting channel matching process for {len(playlist_channels)} channels...")
    start_time = time.time()
    matches = []
    
    # Pre-compute normalized names for all playlist channels
    logger.info("Normalizing channel names...")
    normalized_playlist_channels = []
    for channel in playlist_channels:
        normalized_name = normalize_channel_name(channel['clean_name'])
        normalized_playlist_channels.append((channel, normalized_name))
    
    # Create a list of all normalized mapping names for faster partial matching
    mapping_names = list(channel_mappings.keys())
    
    # Function to process a single channel
    def process_channel(channel_data):
        channel, normalized_name = channel_data
        
        # Try direct match first (fastest)
        if normalized_name in channel_mappings:
            return {
                'playlist_channel': channel,
                'mapping': channel_mappings[normalized_name],
                'match_type': 'direct'
            }
        
        # If no direct match, try partial matching
        best_match = None
        best_score = 0
        
        # Only check partial matches for channels that share at least the first character
        # This significantly reduces the number of comparisons needed
        first_char = normalized_name[0] if normalized_name else ''
        potential_matches = [name for name in mapping_names if name and name[0] == first_char]
        
        for mapping_name in potential_matches:
            # Calculate similarity score
            score = calculate_similarity(normalized_name, mapping_name)
            
            if score > best_score and score > 0.8:  # 80% similarity threshold
                best_score = score
                best_match = channel_mappings[mapping_name]
        
        if best_match:
            return {
                'playlist_channel': channel,
                'mapping': best_match,
                'match_type': 'partial',
                'score': best_score
            }
        else:
            # No match found
            return {
                'playlist_channel': channel,
                'mapping': None,
                'match_type': 'none'
            }
    
    # Use ThreadPoolExecutor to process channels in parallel
    max_workers = min(32, os.cpu_count() * 4)
    logger.info(f"Processing matches using {max_workers} parallel workers...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        matches = list(executor.map(process_channel, normalized_playlist_channels))
    
    # Count matches
    direct_matches = sum(1 for m in matches if m['match_type'] == 'direct')
    partial_matches = sum(1 for m in matches if m['match_type'] == 'partial')
    no_matches = sum(1 for m in matches if m['match_type'] == 'none')
    
    elapsed_time = time.time() - start_time
    logger.info(f"Matching completed in {elapsed_time:.2f} seconds")
    logger.info(f"Results: {direct_matches} direct matches, {partial_matches} partial matches, {no_matches} no matches")
    
    return matches

def calculate_similarity(str1, str2):
    """Calculate similarity between two strings"""
    # Simple implementation using difflib
    from difflib import SequenceMatcher
    return SequenceMatcher(None, str1, str2).ratio()

def generate_channel_list_xml(matches, output_file, country_prefix=None):
    """Generate a channel list XML file from matches with each channel on a new line (optimized)"""
    logger.info(f"Generating channel list XML: {output_file}")
    start_time = time.time()
    
    # Create the XML content directly as a string for better performance
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<channels>']
    
    # Count matched channels
    matched_count = 0
    
    # Add channel elements for each match
    for match in matches:
        if match['mapping']:
            matched_count += 1
            channel = match['playlist_channel']
            mapping = match['mapping']
            
            # Format the channel element as a string
            site = mapping['site']
            lang = mapping['lang']
            xmltv_id = mapping['xmltv_id'] or channel['tvg_id'] or ''
            site_id = mapping['site_id']
            
            # Set channel name with country prefix if specified
            if country_prefix and not channel['name'].startswith(country_prefix):
                channel_text = f"{country_prefix} {channel['name']}"
            else:
                channel_text = channel['name']
            
            # Create the channel element string
            channel_line = f'  <channel site="{site}" lang="{lang}" xmltv_id="{xmltv_id}" site_id="{site_id}">{channel_text}</channel>'
            lines.append(channel_line)
    
    # Close the root element
    lines.append('</channels>')
    
    # Write to file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        elapsed_time = time.time() - start_time
        logger.info(f"Generated channel list XML with {matched_count} channels in {elapsed_time:.2f} seconds")
        return True
    except Exception as e:
        logger.error(f"Error generating channel list XML: {e}")
        return False

def export_unmatched_channels(matches, output_file="unmatched_channels.log"):
    """Export unmatched channels to a log file"""
    unmatched = [m['playlist_channel']['name'] for m in matches if m['match_type'] == 'none']
    
    if not unmatched:
        logger.info("All channels were matched successfully")
        return
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        # Write unmatched channels to log file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# Unmatched channels ({len(unmatched)}) - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for channel in sorted(unmatched):
                f.write(f"{channel}\n")
        
        logger.info(f"Exported {len(unmatched)} unmatched channels to {output_file}")
    except Exception as e:
        logger.error(f"Error exporting unmatched channels: {e}")

def main():
    # Record total execution time
    total_start_time = time.time()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Create a channel list XML from a playlist')
    parser.add_argument('--playlist-url', help='URL to download the playlist from')
    parser.add_argument('--playlist-file', help='Local playlist file to use instead of downloading')
    parser.add_argument('--country-prefix', help='Filter channels by country prefix (e.g., "IN:")')
    parser.add_argument('--channels-dir', default='channels', help='Directory containing channel mapping XML files')
    parser.add_argument('--output-file', default='channel_list.xml', help='Output XML file')
    parser.add_argument('--force-download', action='store_true', help='Force download of playlist even if it exists')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--unmatched-log', default='unmatched_channels.log', help='File to log unmatched channels')
    
    args = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info("Channel list generator started")
    
    # Check if either playlist URL or file is provided
    if not args.playlist_url and not args.playlist_file:
        logger.error("Error: Either --playlist-url or --playlist-file must be provided")
        parser.print_help()
        sys.exit(1)
    
    # Get playlist file
    playlist_file = None
    if args.playlist_url:
        playlist_file = download_playlist(args.playlist_url, force_download=args.force_download)
        if not playlist_file:
            logger.error("Failed to download playlist")
            sys.exit(1)
    else:
        playlist_file = args.playlist_file
        if not os.path.exists(playlist_file):
            logger.error(f"Playlist file not found: {playlist_file}")
            sys.exit(1)
    
    # Load playlist channels
    playlist_channels = load_playlist_channels(playlist_file, args.country_prefix)
    if not playlist_channels:
        logger.error("No channels found in playlist")
        sys.exit(1)
    
    # Load channel mappings
    channel_mappings = load_channel_mappings(args.channels_dir)
    if not channel_mappings:
        logger.error("No channel mappings found")
        sys.exit(1)
    
    # Match channels
    matches = match_channels(playlist_channels, channel_mappings)
    
    # Export unmatched channels to log file
    export_unmatched_channels(matches, args.unmatched_log)
    
    # Generate channel list XML
    generate_channel_list_xml(matches, args.output_file, args.country_prefix)
    
    # Report total execution time
    total_elapsed_time = time.time() - total_start_time
    logger.info(f"Total execution time: {total_elapsed_time:.2f} seconds")

if __name__ == "__main__":
    main()
