#!/bin/bash

# Script to run the spot price fetcher locally (without Docker)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Spot Price Fetcher - Local Run ===${NC}"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed${NC}"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source venv/bin/activate

# Install/update dependencies
echo -e "${GREEN}Installing dependencies...${NC}"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Load .env file if it exists
if [ -f .env ]; then
    echo -e "${GREEN}Loading environment variables from .env file...${NC}"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${YELLOW}Warning: .env file not found. Using system environment variables.${NC}"
fi

# Check required environment variables
if [ -z "$POSTGREST_API_KEY" ]; then
    echo -e "${RED}Error: POSTGREST_API_KEY environment variable is not set${NC}"
    echo -e "${YELLOW}Please set it in .env file or export it:${NC}"
    echo -e "  export POSTGREST_API_KEY=your_api_key_here"
    exit 1
fi

# Set default POSTGREST_URL if not set
if [ -z "$POSTGREST_URL" ]; then
    export POSTGREST_URL="http://localhost:3000"
    echo -e "${YELLOW}Using default POSTGREST_URL: ${POSTGREST_URL}${NC}"
fi

echo -e "${GREEN}Running fetch_15min_data.py...${NC}"
echo ""

# Run the Python script
python3 fetch_15min_data.py

# Check exit status
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Script completed successfully${NC}"
else
    echo ""
    echo -e "${RED}✗ Script failed${NC}"
    exit 1
fi

