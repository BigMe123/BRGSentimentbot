#!/bin/bash
# BSG Bot Master Runner - Always uses the unified master source list

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🌍 BSG Sentiment Bot - Master Source Edition${NC}"
echo "=========================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

# Check if the SKB catalog database exists
if [ ! -f "skb_catalog.db" ]; then
    echo -e "${YELLOW}Warning: SKB catalog database not found${NC}"
    echo "Creating new catalog database..."
    python3 -c "from sentiment_bot.master_sources import get_master_sources; get_master_sources()"
fi

# Show source statistics
echo -e "\n${GREEN}📊 Master Source Statistics:${NC}"
python3 -c "
from sentiment_bot.master_sources import get_source_statistics
stats = get_source_statistics()
print(f\"  Total sources: {stats['total_sources']}\")
print(f\"  High priority: {stats['priority_ranges']['high']}\")
print(f\"  With RSS feeds: {stats['with_rss']}\")
"

# Parse command line arguments
COMMAND=$1
shift

case "$COMMAND" in
    run)
        echo -e "\n${BLUE}Running sentiment analysis...${NC}"
        python3 run_with_master_sources.py "$@"
        ;;
    
    stats)
        echo -e "\n${BLUE}Detailed source statistics:${NC}"
        python3 -m sentiment_bot.master_sources
        ;;
    
    list)
        echo -e "\n${BLUE}Listing sources:${NC}"
        python3 run_with_master_sources.py --list-sources "$@"
        ;;
    
    export)
        OUTPUT_FILE=${1:-"config/master_sources_export.yaml"}
        echo -e "\n${BLUE}Exporting master sources to $OUTPUT_FILE...${NC}"
        python3 -c "
from sentiment_bot.master_sources import export_master_list
export_master_list('$OUTPUT_FILE')
print('✅ Export complete')
"
        ;;
    
    harvest)
        echo -e "\n${BLUE}Running stealth harvester to discover RSS feeds...${NC}"
        python3 harvest_global_news.py
        ;;
    
    update)
        echo -e "\n${BLUE}Updating source catalog from seeds...${NC}"
        python3 add_sources_to_skb.py
        ;;
    
    high-priority)
        echo -e "\n${BLUE}Running analysis on high-priority sources only...${NC}"
        python3 run_with_master_sources.py --min-priority 0.7 "$@"
        ;;
    
    by-region)
        REGION=$1
        shift
        if [ -z "$REGION" ]; then
            echo -e "${RED}Error: Please specify a region${NC}"
            echo "Available regions: americas, europe, asia, middle_east, africa, oceania, latam"
            exit 1
        fi
        echo -e "\n${BLUE}Running analysis on $REGION sources...${NC}"
        python3 run_with_master_sources.py --regions "$REGION" "$@"
        ;;
    
    by-topic)
        TOPIC=$1
        shift
        if [ -z "$TOPIC" ]; then
            echo -e "${RED}Error: Please specify a topic${NC}"
            echo "Common topics: economy, politics, tech, security, science"
            exit 1
        fi
        echo -e "\n${BLUE}Running analysis on $TOPIC sources...${NC}"
        python3 run_with_master_sources.py --topics "$TOPIC" "$@"
        ;;
    
    help|--help|-h|"")
        echo -e "\n${GREEN}Available commands:${NC}"
        echo "  run [options]        - Run sentiment analysis with all sources"
        echo "  stats               - Show detailed source statistics"
        echo "  list [options]      - List sources (with optional filters)"
        echo "  export [file]       - Export master sources to YAML"
        echo "  harvest             - Run stealth harvester for RSS discovery"
        echo "  update              - Update catalog from seed files"
        echo "  high-priority       - Run on high-priority sources only"
        echo "  by-region <region>  - Run on specific region"
        echo "  by-topic <topic>    - Run on specific topic"
        echo ""
        echo -e "${GREEN}Filter options:${NC}"
        echo "  --regions <r1 r2>   - Filter by regions"
        echo "  --topics <t1 t2>    - Filter by topics"
        echo "  --min-priority <n>  - Minimum priority threshold"
        echo "  --max-sources <n>   - Maximum number of sources"
        echo ""
        echo -e "${GREEN}Examples:${NC}"
        echo "  ./bsgbot_master.sh run                    # Run with all sources"
        echo "  ./bsgbot_master.sh high-priority          # High-priority only"
        echo "  ./bsgbot_master.sh by-region europe       # Europe only"
        echo "  ./bsgbot_master.sh by-topic economy       # Economy sources"
        echo "  ./bsgbot_master.sh list --min-priority 0.8  # List top sources"
        ;;
    
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo "Run './bsgbot_master.sh help' for usage information"
        exit 1
        ;;
esac