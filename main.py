#!/usr/bin/env python3
"""
VoiceMap Main Entry Point
Updated for new package structure
"""

import sys
import os
import time
from pathlib import Path
import logging

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from analyzer import VoiceMapAnalyzer
from config import VoiceMapConfig, DEFAULT_CONFIG
from logger import setup_logger, get_logger


def main():
    """Main entry point for VoiceMap analysis"""
    # Set up logging
    setup_logger("voicemap", level=logging.INFO)
    logger = get_logger("voicemap")
    
    logger.info("VoiceMap Voice Range Profile Analyzer")
    logger.info("=" * 50)
    
    # Check command line arguments
    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        if not os.path.exists(audio_file):
            logger.error(f"Audio file not found: {audio_file}")
            sys.exit(1)
    else:
        # Use default audio file
        audio_file = DEFAULT_CONFIG.audio_file
        if not os.path.exists(audio_file):
            logger.error(f"Default audio file not found: {audio_file}")
            logger.error("Please provide an audio file as command line argument")
            sys.exit(1)
    
    try:
        # Create analyzer with default configuration
        analyzer = VoiceMapAnalyzer()
        
        # Run analysis
        logger.info(f"Analyzing audio file: {audio_file}")
        t_start = time.time()
        data, output_file = analyzer.analyze_and_output_vrp(audio_file)
        elapsed = time.time() - t_start

        logger.info("=" * 50)
        logger.info("Analysis completed successfully!")
        logger.info(f"Output file: {output_file}")
        logger.info(f"Data points: {len(data['midi']):,}")
        logger.info(f"Runtime: {elapsed:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()