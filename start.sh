#!/bin/bash

# Internship Matcher - Automated Startup Script
# Usage: ./start.sh [OPTIONS]

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_DIR/venv"
FRONTEND_DIR="$PROJECT_DIR/frontend"

# Parse command line arguments
START_BACKEND=false
START_FRONTEND=false
REFRESH_CACHE=false
CHECK_STATUS=false
FORCE_FULL_REFRESH=false
HELP=false

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

print_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_error() {
    echo -e "${RED}✗${NC}  $1"
}

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Function to show help
show_help() {
    cat << EOF
Internship Matcher - Automated Startup Script

Usage: ./start.sh [OPTIONS]

OPTIONS:
    --all               Start both backend and frontend
    --backend           Start only the backend server
    --frontend          Start only the frontend dev server
    --refresh           Refresh cache after startup (smart refresh)
    --refresh-full      Force full cache refresh after startup
    --status            Check cache status only (no startup)
    --help              Show this help message

EXAMPLES:
    # Start everything with cache refresh
    ./start.sh --all --refresh

    # Start just the backend
    ./start.sh --backend

    # Check cache status
    ./start.sh --status

    # Start frontend only
    ./start.sh --frontend

    # Start everything with full cache refresh
    ./start.sh --all --refresh-full

NOTES:
    - Redis must be installed (run ./setup_redis.sh if needed)
    - Backend runs on port 8000
    - Frontend runs on port 3000
    - Cache auto-refreshes on backend startup if empty
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --all)
            START_BACKEND=true
            START_FRONTEND=true
            shift
            ;;
        --backend)
            START_BACKEND=true
            shift
            ;;
        --frontend)
            START_FRONTEND=true
            shift
            ;;
        --refresh)
            REFRESH_CACHE=true
            shift
            ;;
        --refresh-full)
            REFRESH_CACHE=true
            FORCE_FULL_REFRESH=true
            shift
            ;;
        --status)
            CHECK_STATUS=true
            shift
            ;;
        --help|-h)
            HELP=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Show help if requested
if [ "$HELP" = true ]; then
    show_help
    exit 0
fi

# If no options specified, show help
if [ "$START_BACKEND" = false ] && [ "$START_FRONTEND" = false ] && [ "$CHECK_STATUS" = false ]; then
    print_warning "No startup options specified"
    echo ""
    show_help
    exit 0
fi

# Header
print_header "Internship Matcher Startup"

# Step 1: Check Redis
print_info "Checking Redis server..."
if redis-cli ping > /dev/null 2>&1; then
    print_success "Redis is running"
else
    print_warning "Redis is not running. Attempting to start..."

    # Try to start Redis
    if command -v brew &> /dev/null; then
        # macOS with Homebrew
        brew services start redis > /dev/null 2>&1
        sleep 2
        if redis-cli ping > /dev/null 2>&1; then
            print_success "Redis started successfully"
        else
            print_error "Failed to start Redis. Please run './setup_redis.sh' first"
            exit 1
        fi
    else
        # Linux
        if command -v systemctl &> /dev/null; then
            sudo systemctl start redis
            sleep 2
            if redis-cli ping > /dev/null 2>&1; then
                print_success "Redis started successfully"
            else
                print_error "Failed to start Redis. Please run './setup_redis.sh' first"
                exit 1
            fi
        else
            print_error "Could not start Redis automatically. Please start it manually or run './setup_redis.sh'"
            exit 1
        fi
    fi
fi

# Step 2: Check Python virtual environment
if [ "$START_BACKEND" = true ]; then
    print_info "Checking Python virtual environment..."
    if [ -d "$VENV_PATH" ]; then
        print_success "Virtual environment found"
    else
        print_warning "Virtual environment not found. Creating one..."
        python3 -m venv "$VENV_PATH"
        print_success "Virtual environment created"

        # Activate and install dependencies
        source "$VENV_PATH/bin/activate"
        if [ -f "$PROJECT_DIR/requirements.txt" ]; then
            print_info "Installing Python dependencies..."
            pip install -q -r "$PROJECT_DIR/requirements.txt"
            print_success "Dependencies installed"
        fi
    fi
fi

# Step 3: Check Node modules
if [ "$START_FRONTEND" = true ]; then
    print_info "Checking frontend dependencies..."
    if [ -d "$FRONTEND_DIR/node_modules" ]; then
        print_success "Node modules found"
    else
        print_warning "Node modules not found. Installing..."
        cd "$FRONTEND_DIR"
        npm install
        cd "$PROJECT_DIR"
        print_success "Node modules installed"
    fi
fi

# Step 4: Check cache status only if requested
if [ "$CHECK_STATUS" = true ]; then
    print_header "Cache Status"
    if curl -s http://localhost:8000/api/cache-status > /dev/null 2>&1; then
        curl -s http://localhost:8000/api/cache-status | python3 -m json.tool
    else
        print_error "Backend is not running. Start it first with: ./start.sh --backend"
        exit 1
    fi
    exit 0
fi

# Step 5: Start Backend
if [ "$START_BACKEND" = true ]; then
    print_header "Starting Backend Server"

    # Check if backend is already running
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_warning "Backend server is already running on port 8000"
        print_info "To restart, kill the existing process first:"
        print_info "  kill \$(lsof -t -i:8000)"
    else
        print_info "Starting backend on port 8000..."
        print_info "Backend will auto-initialize cache on startup"
        echo ""

        # Activate virtual environment and start backend
        source "$VENV_PATH/bin/activate"

        # Run backend in background or foreground based on if frontend is also starting
        if [ "$START_FRONTEND" = true ]; then
            print_warning "Starting backend in background (logs in backend.log)"
            nohup python "$PROJECT_DIR/app.py" > "$PROJECT_DIR/backend.log" 2>&1 &
            BACKEND_PID=$!
            print_success "Backend started (PID: $BACKEND_PID)"

            # Wait a bit for backend to start
            print_info "Waiting for backend to initialize..."
            sleep 5
        else
            print_info "Starting backend in foreground (Ctrl+C to stop)"
            echo ""
            python "$PROJECT_DIR/app.py"
            exit 0
        fi
    fi
fi

# Step 6: Refresh cache if requested
if [ "$REFRESH_CACHE" = true ]; then
    print_header "Refreshing Cache"

    # Wait for backend to be ready
    print_info "Waiting for backend to be ready..."
    RETRIES=0
    MAX_RETRIES=30
    while ! curl -s http://localhost:8000/api/cache-status > /dev/null 2>&1; do
        sleep 1
        RETRIES=$((RETRIES + 1))
        if [ $RETRIES -ge $MAX_RETRIES ]; then
            print_error "Backend did not start in time"
            exit 1
        fi
    done

    if [ "$FORCE_FULL_REFRESH" = true ]; then
        print_info "Forcing full cache refresh..."
        RESPONSE=$(curl -s -X POST "http://localhost:8000/api/refresh-cache?force_full=true")
    else
        print_info "Performing smart cache refresh..."
        RESPONSE=$(curl -s -X POST "http://localhost:8000/api/refresh-cache")
    fi

    echo "$RESPONSE" | python3 -m json.tool
    print_success "Cache refresh completed"
fi

# Step 7: Display cache status
if [ "$START_BACKEND" = true ]; then
    print_header "Current Cache Status"

    # Ensure backend is ready
    RETRIES=0
    MAX_RETRIES=30
    while ! curl -s http://localhost:8000/api/cache-status > /dev/null 2>&1; do
        sleep 1
        RETRIES=$((RETRIES + 1))
        if [ $RETRIES -ge $MAX_RETRIES ]; then
            print_warning "Could not fetch cache status"
            break
        fi
    done

    if curl -s http://localhost:8000/api/cache-status > /dev/null 2>&1; then
        curl -s http://localhost:8000/api/cache-status | python3 -m json.tool
    fi
fi

# Step 8: Start Frontend
if [ "$START_FRONTEND" = true ]; then
    print_header "Starting Frontend Dev Server"

    # Check if frontend is already running
    if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_warning "Frontend server is already running on port 3000"
        print_info "To restart, kill the existing process first:"
        print_info "  kill \$(lsof -t -i:3000)"
    else
        print_info "Starting frontend on port 3000..."
        cd "$FRONTEND_DIR"

        if [ "$START_BACKEND" = true ]; then
            print_warning "Starting frontend in background (logs in frontend.log)"
            nohup npm start > "$PROJECT_DIR/frontend.log" 2>&1 &
            FRONTEND_PID=$!
            cd "$PROJECT_DIR"
            print_success "Frontend started (PID: $FRONTEND_PID)"
        else
            print_info "Starting frontend in foreground (Ctrl+C to stop)"
            echo ""
            npm start
            exit 0
        fi
    fi
fi

# Final summary
if [ "$START_BACKEND" = true ] && [ "$START_FRONTEND" = true ]; then
    print_header "Startup Complete"
    print_success "Backend running on: http://localhost:8000"
    print_success "Frontend running on: http://localhost:3000"
    echo ""
    print_info "Logs:"
    print_info "  Backend:  tail -f backend.log"
    print_info "  Frontend: tail -f frontend.log"
    echo ""
    print_info "To stop services:"
    print_info "  kill \$(lsof -t -i:8000)  # Stop backend"
    print_info "  kill \$(lsof -t -i:3000)  # Stop frontend"
    echo ""
fi

print_success "All done!"
