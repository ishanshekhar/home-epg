# Home EPG

A repository for managing and generating Electronic Program Guide (EPG) data for home use.

## Repository Maintenance

### Keeping the Repository Clean

This repository is configured to ignore large data files and temporary files. To keep it clean:

1. **Regular Cleanup:**
   ```
   # Clean up ignored files
   git clean -Xdf logs/ data/ playlist_data/ epg_data/
   
   # Remove any Python cache files
   find . -name "__pycache__" -o -name "*.pyc" | xargs rm -rf
   ```

2. **Data Management:**
   - EPG data files are stored in `/epg_data/` - these are temporary and regenerated
   - Playlist data is stored in `/playlist_data/` - these are input files
   - Generated EPG files are exported to `/export_epg/` - only these XML files are tracked in git

3. **Ignored File Types:**
   - `.m3u`, `.m3u8`: M3U playlist files
   - `.log`, `.tmp`, `.temp`: Temporary and log files
   - `.DS_Store` and other OS-specific files
   - Python cache files and virtual environments

### Docker Environment

Docker-related files are in the `docker/` directory. Environment variables should be stored in `.env` files which are gitignored.

The Docker setup directly uses channel files from the `my_channels/` directory. To run the Docker container:

```bash
./run-epg.sh
```

To rebuild the Docker image before running:

```bash
./run-epg.sh rebuild
```

## Usage

[Add usage instructions here] 