#!/usr/bin/env python3
import re
import os
import sys
import csv
import glob
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
import time
import requests
import datetime

try:
    from fuzzywuzzy import fuzz
except ImportError:
    print("Warning: fuzzywuzzy package not found. Install with: pip install fuzzywuzzy python-Levenshtein")
    # Define a simple fallback for fuzz functions
    class FuzzFallback:
        @staticmethod
        def ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100
        
        @staticmethod
        def partial_ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100
        
        @staticmethod
        def token_sort_ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100
        
        @staticmethod
        def token_set_ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100
    
    fuzz = FuzzFallback()

# Default output directory for filtered EPG files
DEFAULT_OUTPUT_DIR = "export_epg"
# Default directory where EPG files are stored
DEFAULT_EPG_DIR = "epg_data"

def load_playlist_from_xml(xml_content):
    """Load channels from XML content that contains channel information"""
    try:
        # Parse the XML content
        root = ET.fromstring(xml_content)
        
        channels = []
        
        # Extract channel information from XML
        for channel in root.findall(".//channel"):
            channel_id = channel.get('id', '')
            
            # Get display names
            display_names = []
            for display_name in channel.findall(".//display-name"):
                if display_name.text:
                    display_names.append(display_name.text.strip())
            
            if display_names:
                channel_name = display_names[0]
                
                # Create a channel entry
                channels.append({
                    'name': channel_name,
                    'clean_name': channel_name,  # Will be cleaned later if needed
                    'tvg_id': channel_id,
                    'info': f'#EXTINF:-1 tvg-id="{channel_id}",{channel_name}',
                    'url': f'#EXTURL:{channel_id}'  # Placeholder URL
                })
        
        print(f"Found {len(channels)} channels in XML playlist")
        return channels
    except Exception as e:
        print(f"Error parsing XML playlist: {e}")
        return []

def load_playlist_channels(file_path, country_prefix=None):
    """Load channels from M3U playlist file with optional country filtering"""
    if not os.path.exists(file_path):
        print(f"Playlist file not found: {file_path}")
        return []
    
    print(f"Loading playlist from {file_path}...")
    try:
        # Check if the file is XML
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # If it starts with XML declaration or contains <tv> tag, treat as XML
        if content.strip().startswith('<?xml') or '<tv>' in content:
            print("Detected XML format in playlist file")
            channels = load_playlist_from_xml(content)
            
            # Apply country filter if specified
            if country_prefix and channels:
                filtered_channels = []
                
                print(f"Filtering channels by country prefix: {country_prefix}")
                for channel in channels:
                    # Only include channels that start with the prefix
                    if channel['name'].startswith(country_prefix):
                        filtered_channels.append(channel)
                
                print(f"Found {len(filtered_channels)} channels with prefix: {country_prefix}")
                return filtered_channels
            
            return channels
        
        # Otherwise, process as M3U
        channels = []
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
        
        if country_prefix:
            print(f"Found {len(channels)} channels with prefix: {country_prefix}")
        else:
            print(f"Found {len(channels)} channels in playlist")
        return channels
    except Exception as e:
        print(f"Error loading playlist: {e}")
        return []

def load_epg_channels(epg_file_path):
    """Load channel information from EPG XML file"""
    if not os.path.exists(epg_file_path):
        print(f"EPG file not found: {epg_file_path}")
        return []
    
    print(f"Loading EPG data from {epg_file_path}...")
    try:
        # Parse the XML file
        tree = ET.parse(epg_file_path)
        root = tree.getroot()
        
        epg_channels = []
        
        # Extract channel information
        for channel in root.findall(".//channel"):
            channel_id = channel.get('id')
            
            # Get display names
            display_names = []
            for display_name in channel.findall(".//display-name"):
                if display_name.text:
                    display_names.append(display_name.text.strip())
            
            # Get icons
            icons = []
            for icon in channel.findall(".//icon"):
                src = icon.get('src')
                if src:
                    icons.append(src)
            
            if channel_id and display_names:
                epg_channels.append({
                    'id': channel_id,
                    'display_names': display_names,
                    'primary_name': display_names[0] if display_names else "",
                    'icons': icons
                })
        
        print(f"Loaded {len(epg_channels)} channels from EPG data")
        return epg_channels
    except Exception as e:
        print(f"Error loading EPG file: {e}")
        return []

def clean_channel_name(name):
    """Clean channel name for better matching"""
    # Remove common prefixes
    for prefix in ["UK:", "US:", "IN:", "CA:"]:
        if name.upper().startswith(prefix):
            name = name[len(prefix):].strip()
    
    # Standardize spacing
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Remove HD/SD/FHD/UHD quality indicators
    name = re.sub(r'\b(HD|SD|FHD|UHD|4K|HEVC|H265|H\.265)\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(HD|SD|FHD|UHD|4K)$', '', name, flags=re.IGNORECASE)
    
    # Remove other common suffixes
    name = re.sub(r'\s+(CHANNEL|TV|NETWORK|INDIA)\s*$', '', name, flags=re.IGNORECASE)
    
    # Remove common punctuation that might affect matching
    name = re.sub(r'[&+]', ' AND ', name)
    name = re.sub(r'[^\w\s]', ' ', name)
    
    # Standardize spacing again after all replacements
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name.strip().upper()

def find_best_match(channel, epg_channels, threshold=70, quiet=True):
    """Find the best matching EPG channel for a given playlist channel"""
    clean_name = clean_channel_name(channel['clean_name'])
    best_match = None
    best_score = 0
    best_method = None
    
    # For debugging
    if not quiet:
        print(f"Finding match for: {channel['name']} → Cleaned to: {clean_name}")
    
    # Try exact match first (case insensitive)
    for epg_channel in epg_channels:
        for display_name in epg_channel['display_names']:
            clean_epg_name = clean_channel_name(display_name)
            if clean_name == clean_epg_name:
                if not quiet:
                    print(f"  Exact match found: {display_name} ({epg_channel['id']})")
                return {
                    'epg_channel': epg_channel,
                    'score': 100,
                    'method': 'Exact match'
                }
    
    # Try fuzzy matching
    for epg_channel in epg_channels:
        for display_name in epg_channel['display_names']:
            clean_epg_name = clean_channel_name(display_name)
            
            # Try different fuzzy matching methods
            ratio = fuzz.ratio(clean_name, clean_epg_name)
            partial_ratio = fuzz.partial_ratio(clean_name, clean_epg_name)
            token_sort_ratio = fuzz.token_sort_ratio(clean_name, clean_epg_name)
            token_set_ratio = fuzz.token_set_ratio(clean_name, clean_epg_name)
            
            # Use the best score from any method
            current_best = best_score
            
            if ratio > best_score:
                best_score = ratio
                best_match = epg_channel
                best_method = 'String similarity'
            
            if partial_ratio > best_score:
                best_score = partial_ratio
                best_match = epg_channel
                best_method = 'Partial match'
            
            if token_sort_ratio > best_score:
                best_score = token_sort_ratio
                best_match = epg_channel
                best_method = 'Token sort'
                
            if token_set_ratio > best_score:
                best_score = token_set_ratio
                best_match = epg_channel
                best_method = 'Token set'
                
            # Print high-scoring matches for debugging
            if not quiet and best_score > current_best and best_score >= 80:
                print(f"  Good match: {display_name} - Score: {best_score}% ({best_method})")
    
    if best_score >= threshold:
        return {
            'epg_channel': best_match,
            'score': best_score,
            'method': best_method
        }
    else:
        if not quiet:
            print(f"  No good match found. Best score: {best_score}%")
        return None

def match_channels(playlist_channels, epg_file, threshold=70, quiet=True):
    """Match playlist channels with EPG data"""
    epg_channels = load_epg_channels(epg_file)
    if not epg_channels:
        return []
    
    matches = []
    for channel in playlist_channels:
        epg_match = find_best_match(channel, epg_channels, threshold, quiet)
        matches.append({
            'playlist_channel': channel,
            'epg_match': epg_match
        })
    
    # Count matches
    matched_count = sum(1 for m in matches if m['epg_match'])
    perfect_matches = sum(1 for m in matches if m['epg_match'] and m['epg_match']['score'] == 100)
    
    print(f"Found matches for {matched_count} out of {len(playlist_channels)} channels ({matched_count/len(playlist_channels)*100:.1f}%)")
    print(f"Perfect matches (100% score): {perfect_matches}")
    
    return matches

def generate_filtered_epg_xml(matches, input_epg_file, output_file, only_perfect=True):
    """Generate a filtered EPG XML file containing only matched channels and their programs"""
    if not os.path.exists(input_epg_file):
        print(f"EPG file not found: {input_epg_file}")
        return False
    
    # Filter for perfect matches if requested
    if only_perfect:
        matches_to_include = [m for m in matches if m['epg_match'] and m['epg_match']['score'] == 100]
    else:
        matches_to_include = [m for m in matches if m['epg_match']]
    
    if not matches_to_include:
        print("No matches to include in the filtered EPG file.")
        return False
    
    try:
        # Parse the original EPG file
        tree = ET.parse(input_epg_file)
        root = tree.getroot()
        
        # Create a new XML root with the same structure
        new_root = ET.Element('tv')
        for attr_name, attr_value in root.attrib.items():
            new_root.set(attr_name, attr_value)
        
        # Track channel IDs to include (for programs), but still allow duplicate channels
        channel_ids_to_include = set()
        channel_count = 0
        
        # Add matched channels to the new XML
        for match in matches_to_include:
            epg_channel_id = match['epg_match']['epg_channel']['id']
            channel_ids_to_include.add(epg_channel_id)
            
            # Find the original channel template (we'll use just the first one as template)
            channel_template = root.find(".//channel[@id='{}']".format(epg_channel_id))
            if not channel_template:
                continue
            
            # Create a new channel element
            new_channel = ET.SubElement(new_root, 'channel', id=epg_channel_id)
            channel_count += 1
            
            # Use the playlist channel name as the display name
            display_name = ET.SubElement(new_channel, 'display-name')
            display_name.text = match['playlist_channel']['name']
            
            # Copy icons if they exist
            for icon in channel_template.findall('.//icon'):
                new_icon = ET.SubElement(new_channel, 'icon', src=icon.get('src', ''))
            
            # Copy any other elements
            for child in channel_template:
                if child.tag != 'display-name' and child.tag != 'icon':
                    new_channel.append(child)
        
        # Add program entries for the included channels
        for program in root.findall(".//programme"):
            channel_id = program.get('channel')
            if channel_id in channel_ids_to_include:
                # Copy the program element and all its children
                new_program = ET.Element('programme')
                for attr_name, attr_value in program.attrib.items():
                    new_program.set(attr_name, attr_value)
                
                for child in program:
                    new_program.append(child)
                
                new_root.append(new_program)
        
        # Create a new XML tree and write to file
        new_tree = ET.ElementTree(new_root)
        
        # Count the number of programs included
        program_count = len(new_root.findall(".//programme"))
        
        # Write the new XML file with proper formatting
        with open(output_file, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            new_tree.write(f, encoding='utf-8')
        
        print(f"Generated filtered EPG file: {output_file}")
        print(f"Included {channel_count} channels and {program_count} program entries")
        return True
    
    except Exception as e:
        print(f"Error generating filtered EPG file: {e}")
        return False

def consolidate_epg_files(epg_files, output_file):
    """Consolidate multiple EPG files into a single file"""
    if not epg_files:
        print("No EPG files to consolidate")
        return None
    
    if len(epg_files) == 1:
        print(f"Only one EPG file provided, no consolidation needed: {epg_files[0]}")
        return epg_files[0]
    
    try:
        # Create a new XML root
        new_root = ET.Element('tv')
        new_root.set('generator-info-name', 'Consolidated EPG Generator')
        
        # Modified: Track channel IDs for reference, but don't use for exclusion
        channel_ids_count = {}
        program_count = 0
        
        print(f"Consolidating {len(epg_files)} EPG files...")
        
        for file_path in epg_files:
            print(f"Processing {file_path}...")
            
            # Parse the EPG file
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Copy attributes from the first file
            if not new_root.attrib:
                for attr, value in root.attrib.items():
                    if attr != 'generator-info-name':
                        new_root.set(attr, value)
            
            # Modified: Add all channels, even with duplicate IDs
            for channel in root.findall(".//channel"):
                channel_id = channel.get('id')
                # Instead of skipping, we keep a count for reporting
                if channel_id in channel_ids_count:
                    channel_ids_count[channel_id] += 1
                else:
                    channel_ids_count[channel_id] = 1
                
                # Always add the channel
                new_root.append(channel)
            
            # Add all programs
            for program in root.findall(".//programme"):
                new_root.append(program)
                program_count += 1
        
        # Create a new XML tree
        new_tree = ET.ElementTree(new_root)
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        # Write the consolidated EPG file
        with open(output_file, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            new_tree.write(f, encoding='utf-8')
        
        unique_ids = len(channel_ids_count)
        total_channels = sum(channel_ids_count.values())
        duplicate_count = total_channels - unique_ids
        
        print(f"Consolidated EPG file created: {output_file}")
        print(f"Included {total_channels} total channels ({unique_ids} unique IDs, {duplicate_count} duplicates) and {program_count} program entries")
        
        return output_file
    except Exception as e:
        print(f"Error consolidating EPG files: {e}")
        return None

def find_epg_files_for_country(epg_dir, country_code):
    """Find all EPG files for a specific country code"""
    if not country_code:
        return []
    
    # Look for files with the country code in the filename
    pattern = os.path.join(epg_dir, f"*_{country_code}_*.xml")
    files = glob.glob(pattern)
    
    # Also try alternative pattern
    alt_pattern = os.path.join(epg_dir, f"*_{country_code}[0-9]*.xml")
    files.extend(glob.glob(alt_pattern))
    
    # Remove duplicates
    files = list(set(files))
    
    return files

def extract_country_from_prefix(prefix):
    """Extract country code from a prefix like 'UK:', 'US:', etc."""
    if not prefix:
        return None
    
    # Remove colon if present
    country_code = prefix.rstrip(':').upper()
    
    # Validate that it's a 2-letter country code
    if len(country_code) == 2 and country_code.isalpha():
        return country_code
    
    return None

def match_epg_for_country(playlist_file, country_prefix, epg_dir=DEFAULT_EPG_DIR, 
                         output_dir=DEFAULT_OUTPUT_DIR, threshold=70, only_perfect=False,
                         verbose=False):
    """Match playlist channels with EPG data for a specific country"""
    # Extract country code from prefix
    country_code = extract_country_from_prefix(country_prefix)
    if not country_code:
        print(f"Invalid country prefix: {country_prefix}")
        return False
    
    # Find EPG files for this country
    epg_files = find_epg_files_for_country(epg_dir, country_code)
    if not epg_files:
        print(f"No EPG files found for country code: {country_code}")
        return False
    
    print(f"Found {len(epg_files)} EPG file(s) for country code {country_code}:")
    for file in epg_files:
        print(f"  - {file}")
    
    # Load playlist channels with country filter
    playlist_channels = load_playlist_channels(playlist_file, country_prefix)
    if not playlist_channels:
        print(f"No channels found in playlist for country prefix: {country_prefix}")
        return False
    
    print(f"Loaded {len(playlist_channels)} channels from playlist with prefix: {country_prefix}")
    
    # If multiple EPG files, consolidate them first
    if len(epg_files) > 1:
        print("Multiple EPG files found, consolidating...")
        consolidated_file = os.path.join(epg_dir, f"consolidated_{country_code}.xml")
        epg_file = consolidate_epg_files(epg_files, consolidated_file)
        if not epg_file:
            print("Failed to consolidate EPG files.")
            return False
    else:
        epg_file = epg_files[0]
    
    # Match channels
    matches = match_channels(playlist_channels, epg_file, threshold, not verbose)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filtered EPG file
    output_file = os.path.join(output_dir, f"epg_{country_code}.xml")
    success = generate_filtered_epg_xml(matches, epg_file, output_file, only_perfect)
    
    if success:
        print(f"Generated filtered EPG file: {output_file}")
    else:
        print("Failed to generate filtered EPG file.")
    
    return success

def download_playlist_from_url(url, output_dir="playlist_data", force_download=False):
    """Download M3U playlist from a specified URL, with date in filename and only if needed"""
    try:
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get today's date for the filename
        today = datetime.datetime.now().strftime("%Y%m%d")
        
        # Use a filename with date
        filename = f"playlist_{today}.m3u"
        output_path = os.path.join(output_dir, filename)
        
        # Check if we already have today's file
        if os.path.exists(output_path) and not force_download:
            print(f"Using existing playlist file from today: {output_path}")
            return output_path, 'm3u'
        
        # Check for older files
        if not force_download:
            files = os.listdir(output_dir)
            playlist_files = [f for f in files if f.startswith("playlist_") and f.endswith(".m3u")]
            
            if playlist_files:
                # Sort by date (newest first)
                playlist_files.sort(reverse=True)
                newest_file = playlist_files[0]
                newest_path = os.path.join(output_dir, newest_file)
                
                # Extract date from filename
                try:
                    file_date_str = newest_file.replace("playlist_", "").replace(".m3u", "")
                    file_date = datetime.datetime.strptime(file_date_str, "%Y%m%d")
                    
                    # Check if file is less than one day old
                    age = datetime.datetime.now() - file_date
                    if age.days < 1:
                        print(f"Using recent playlist file (less than 1 day old): {newest_path}")
                        return newest_path, 'm3u'
                    else:
                        print(f"Existing playlist file is {age.days} days old. Downloading new one.")
                except ValueError:
                    # If we can't parse the date, download a new file
                    pass
        
        print(f"Downloading playlist from {url}...")
        
        # Use requests to download the file
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Save the content to a file
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        print(f"Downloaded to {output_path}")
        
        # Check if the content is XML by decoding a copy of the content
        content_text = response.content.decode('utf-8', errors='ignore')
        if content_text.strip().startswith('<?xml') or '<tv>' in content_text:
            print("Detected XML format in playlist file")
            # If it's XML, rename the file to reflect that
            xml_path = output_path.replace(".m3u", ".xml")
            os.rename(output_path, xml_path)
            return xml_path, 'xml'
        
        return output_path, 'm3u'
    except Exception as e:
        print(f"Error downloading playlist from {url}: {e}")
        return None, None

def main():
    # Parse command line arguments
    playlist_file = None
    playlist_url = None
    country_prefix = None
    epg_dir = DEFAULT_EPG_DIR
    output_dir = DEFAULT_OUTPUT_DIR
    threshold = 70
    only_perfect = False
    verbose = False
    force_download = False
    playlist_dir = "playlist_data"
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--playlist" and i + 1 < len(sys.argv):
            playlist_file = sys.argv[i + 1]
            i += 2
        elif arg == "--playlist-url" and i + 1 < len(sys.argv):
            playlist_url = sys.argv[i + 1]
            i += 2
        elif arg == "--country" and i + 1 < len(sys.argv):
            country_prefix = sys.argv[i + 1]
            i += 2
        elif arg == "--epg-dir" and i + 1 < len(sys.argv):
            epg_dir = sys.argv[i + 1]
            i += 2
        elif arg == "--output-dir" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        elif arg == "--playlist-dir" and i + 1 < len(sys.argv):
            playlist_dir = sys.argv[i + 1]
            i += 2
        elif arg == "--threshold" and i + 1 < len(sys.argv):
            try:
                threshold = int(sys.argv[i + 1])
            except ValueError:
                print(f"Invalid threshold value: {sys.argv[i + 1]}")
            i += 2
        elif arg == "--force-download":
            force_download = True
            i += 1
        elif arg == "--only-perfect":
            only_perfect = True
            i += 1
        elif arg == "--verbose":
            verbose = True
            i += 1
        else:
            i += 1
    
    # If playlist URL is provided, download it
    if playlist_url:
        try:
            downloaded_playlist, format_type = download_playlist_from_url(playlist_url, playlist_dir, force_download)
            if downloaded_playlist:
                playlist_file = downloaded_playlist
                print(f"Using playlist from {playlist_url}: {playlist_file}")
            else:
                print(f"Failed to download playlist from {playlist_url}")
                return
        except ImportError:
            print("Error: The requests package is required for downloading files.")
            print("Please install it using: pip install requests")
            return
    
    # Check required parameters
    if not playlist_file:
        print("Error: Playlist file is required. Use --playlist or --playlist-url to specify the file.")
        print("Usage: python epg_matcher.py --playlist playlist.m3u --country UK [options]")
        print("   or: python epg_matcher.py --playlist-url http://example.com/playlist.m3u --country UK [options]")
        print("Options:")
        print("  --country PREFIX        Specify the country prefix (e.g., UK, US, IN)")
        print("  --epg-dir DIR           Specify the directory containing EPG files (default: epg_data)")
        print("  --output-dir DIR        Specify the output directory (default: export_epg)")
        print("  --playlist-dir DIR      Specify the directory to save downloaded playlists (default: playlist_data)")
        print("  --threshold N           Set the matching threshold (default: 70)")
        print("  --only-perfect          Include only perfect matches (100% score)")
        print("  --verbose               Show detailed matching information")
        print("  --force-download        Force download of playlist even if recent file exists")
        return
    
    if not country_prefix:
        print("Error: Country prefix is required. Use --country to specify the prefix.")
        return
    
    # Match EPG for the specified country
    match_epg_for_country(playlist_file, country_prefix, epg_dir, output_dir, threshold, only_perfect, verbose)

if __name__ == "__main__":
    main() 