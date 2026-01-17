# Entry point for DamaDam Bot
# GitHub Actions yahin se run kare ga

import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from Scraper import main

if __name__ == "__main__":
    main()