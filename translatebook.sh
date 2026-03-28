#!/bin/bash

# Book Translation Tool - Complete Pipeline Script
# Usage: ./translatebook.sh [options] input_file
# Example: ./translatebook.sh --olang zh --clean sample.pdf

set -e  # Exit on any error

# Script information
SCRIPT_NAME="translatebook.sh"
VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
INPUT_FILE=""
INPUT_LANG="auto"
OUTPUT_LANG="zh"
CUSTOM_PROMPT=""
EXTRACT_GLOSSARY=false
GLOSSARY_PATH=""
GLOSSARY_MIN_PRIORITY=""
CLEAN_TEMP=false
SKIP_EXISTING=true
VERBOSE=false
DRY_RUN=false
STEP_START=1
STEP_END=7
REINSTALL_PACKAGES=false
MODEL_OVERRIDE=""
SAMPLE_ONLY=false
OUTPUT_FORMAT="epub"
BILINGUAL_STYLE="alternating"
BENCHMARK_MODE=false
QUOTA_STATUS_MODE=false
EPUB_BASELINE=false
EPUB_TRANSLATE_ROUNDTRIP=false
WORKFLOW_OVERRIDE=""
RESOLVED_WORKFLOW=""
USED_LEGACY_ROUNDTRIP_FLAG=false
FORCE_RESUME=false
PROVIDER="cli"
FALLBACK_PROVIDER=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${PURPLE}[STEP $1]${NC} $2"
}

# Help function
show_help() {
    cat << EOF
${SCRIPT_NAME} v${VERSION} - Book Translation Tool

DESCRIPTION:
    Translates PDF, DOCX, or EPUB files with Gemini CLI.
    Uses workflow-based execution:
      - epub: package-preserving EPUB translation workflow
      - markdown: markdown conversion workflow
    Creates and manages Python virtual environment automatically.
    Uses Calibre for unified file conversion via HTMLZ format.

USAGE:
    ${SCRIPT_NAME} [OPTIONS] INPUT_FILE

OPTIONS:
    -l, --ilang LANG        Input language (default: auto)
    --olang LANG           Output language (default: zh)
    -p, --prompt TEXT      Custom prompt for translation (step 3)
    --extract-glossary     Extract terminology glossary before translation (EPUB input only)
    --glossary PATH        Path to pre-extracted glossary JSON (skip extraction step)
    --clean                Clean temp directory before starting
    --no-skip              Don't skip existing intermediate files
    --reinstall-packages   Reinstall Python packages in virtual environment
    --start-step NUM       Start from step NUM (1-7, default: 1)
    --end-step NUM         End at step NUM (1-7, default: 7)
    --model MODEL          Force model or alias for step 3 (e.g. pro|flash|lite or full model name)
    --sample-only          Run sample translation steps only (steps 3-4)
    --output-format FORMAT Preferred final format (epub|pdf|docx|html, default: epub)
    --bilingual-style STYLE Bilingual layout style (alternating, default: alternating)
    --benchmark            Run benchmark_models.py after conversion and exit
    --quota-status         Print today's quota usage and exit
    --epub-baseline        Run EPUB baseline mode (no text mutation) and exit
    --epub-translate-roundtrip Deprecated alias for --workflow epub
    --workflow MODE        Workflow mode: epub|markdown (default: epub for .epub, markdown otherwise)
    --provider MODE        Translation provider: cli|api (default: cli)
    --fallback-provider MODE Optional fallback provider when primary fails (currently: api)
    --force-resume         Allow resuming translation with different model (may cause quality inconsistency)
    --dry-run              Show what would be done without executing
    -v, --verbose          Enable verbose output
    -h, --help             Show this help message

STEPS:
    1. Environment preparation and parameter parsing
    2. Split file to markdown and extract images
    3. Translate markdown files using Gemini API
    4. Merge translated markdown files
    5. Convert markdown to HTML with template
    6. Generate and insert table of contents
    7. Generate DOCX and EPUB files in temp directory

NOTE:
    For PDF/DOCX/EPUB files, steps 1-2 are automatically replaced by Calibre HTMLZ conversion
    which creates optimized markdown chunks ready for translation.

EXAMPLES:
    # EPUB input defaults to package-preserving workflow
    ${SCRIPT_NAME} book.epub

    # Explicit workflow selection
    ${SCRIPT_NAME} --workflow epub book.epub
    ${SCRIPT_NAME} --workflow markdown book.pdf

    # Clean temp and run with verbose output
    ${SCRIPT_NAME} --clean -v book.epub
    
    # Use custom prompt for translation
    ${SCRIPT_NAME} -p "Focus on technical accuracy and use formal language" book.pdf

    # Run only translation steps (3-4)
    ${SCRIPT_NAME} --start-step 3 --end-step 4 book.docx
    
    # Run only format conversion steps (5-7)
    ${SCRIPT_NAME} --start-step 5 --end-step 7 book.docx

    # Deprecated alias (still supported)
    ${SCRIPT_NAME} --epub-translate-roundtrip book.epub

    # Dry run to see resolved workflow
    ${SCRIPT_NAME} --dry-run book.pdf

REQUIREMENTS:
    - Python 3.6+
    - Gemini CLI
    - Calibre (for PDF/DOCX/EPUB support): https://calibre-ebook.com/
    - Internet connection (for initial package installation)
    
NOTE:
    Python packages are automatically installed in a virtual environment.
    The virtual environment is created in the script directory.

EXIT CODES:
    0   Success
    1   General error
    2   Invalid arguments
    3   Missing dependencies
    4   Gemini CLI not found
    5   Input file not found

EOF
}

# Setup Python virtual environment
setup_venv() {
    log_info "Setting up Python virtual environment..."
    
    local venv_dir="${SCRIPT_DIR}/venv"
    
    # Create virtual environment if it doesn't exist or if reinstall is requested
    if [[ ! -d "$venv_dir" ]] || [[ "$REINSTALL_PACKAGES" == true ]]; then
        if [[ "$REINSTALL_PACKAGES" == true ]] && [[ -d "$venv_dir" ]]; then
            log_info "Removing existing virtual environment for reinstall..."
            rm -rf "$venv_dir"
        fi
        
        log_info "Creating Python virtual environment..."
        python3 -m venv "$venv_dir"
        if [[ $? -ne 0 ]]; then
            log_error "Failed to create virtual environment"
            exit 3
        fi
    fi
    
    # Activate virtual environment
    source "$venv_dir/bin/activate"
    if [[ $? -ne 0 ]]; then
        log_error "Failed to activate virtual environment"
        exit 3
    fi
    
    log_success "Virtual environment activated"
    
    # Install required packages if needed
    local requirements_file="${SCRIPT_DIR}/requirements.txt"
    if [[ ! -f "$venv_dir/.packages_installed" ]] || [[ "$REINSTALL_PACKAGES" == true ]]; then
        log_info "Installing required Python packages..."
        
        if [[ -f "$requirements_file" ]]; then
            log_info "Installing packages from requirements.txt..."
            uv pip install -r "$requirements_file"
        else
            log_info "Installing essential packages..."
            uv pip install python-docx PyMuPDF ebooklib beautifulsoup4 lxml markdown Pillow pdf2image pypandoc
        fi
        
        if [[ $? -ne 0 ]]; then
            log_warning "Some packages failed to install, but continuing..."
            log_info "Missing packages will be handled gracefully by the scripts"
            log_info "If PIL/Pillow is missing, images will not be compressed but processing will continue"
        fi
        
        # Mark packages as installed
        touch "$venv_dir/.packages_installed"
        log_success "Python packages installation completed"
    else
        log_info "Python packages already installed, skipping installation"
    fi
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 3
    fi
    
    # Check required Python scripts
    local scripts=("01_prepare_env.py" "02_split_to_md.py" "03_translate_md.py" "04_merge_md.py" "05_md_to_html.py" "06_add_toc.py")
    for script in "${scripts[@]}"; do
        if [[ ! -f "${SCRIPT_DIR}/${script}" ]]; then
            log_error "Required script not found: ${script}"
            exit 3
        fi
    done
    
    # Check for file conversion script and Calibre for all supported formats
    if is_supported_source_file "$INPUT_FILE"; then
        if [[ ! -f "${SCRIPT_DIR}/01_convert_to_htmlz.py" ]]; then
            log_error "File converter not found: 01_convert_to_htmlz.py"
            log_error "This script is required for PDF/DOCX/EPUB file processing"
            exit 3
        fi
        
        # Check for Calibre ebook-convert
        local calibre_paths=(
            "/Applications/calibre.app/Contents/MacOS/ebook-convert"
            "/usr/bin/ebook-convert"
            "/usr/local/bin/ebook-convert"
        )
        
        local calibre_found=false
        for path in "${calibre_paths[@]}"; do
            if [[ -f "$path" ]]; then
                calibre_found=true
                break
            fi
        done
        
        if [[ "$calibre_found" == false ]] && ! command -v ebook-convert &> /dev/null; then
            log_error "Calibre ebook-convert not found"
            log_error "Please install Calibre: https://calibre-ebook.com/"
            exit 3
        fi
    fi
    
    # Check Gemini CLI availability
    if ! command -v gemini &> /dev/null; then
        log_error "Gemini CLI not found"
        log_error "Please install Gemini CLI and ensure 'gemini' is in PATH"
        exit 4
    fi
    
    log_success "Dependencies check passed"
}

is_epub_file() {
    local input_file="$1"
    [[ "$input_file" == *.epub ]] || [[ "$input_file" == *.EPUB ]]
}

resolve_workflow_for_input() {
    local input_file="$1"
    local workflow_override="${2:-}"
    if [[ -n "$workflow_override" ]]; then
        echo "$workflow_override"
        return 0
    fi
    if is_epub_file "$input_file"; then
        echo "epub"
    else
        echo "markdown"
    fi
}

is_supported_source_file() {
    local input_file="$1"
    is_epub_file "$input_file" || [[ "$input_file" == *.pdf ]] || [[ "$input_file" == *.PDF ]] || [[ "$input_file" == *.docx ]] || [[ "$input_file" == *.DOCX ]]
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -l|--ilang)
                INPUT_LANG="$2"
                shift 2
                ;;
            --olang)
                OUTPUT_LANG="$2"
                shift 2
                ;;
            -p|--prompt)
                CUSTOM_PROMPT="$2"
                shift 2
                ;;
            --extract-glossary)
                EXTRACT_GLOSSARY=true
                shift
                ;;
            --glossary)
                GLOSSARY_PATH="$2"
                shift 2
                ;;
            --glossary-min-priority)
                GLOSSARY_MIN_PRIORITY="$2"
                shift 2
                ;;
            --clean)
                CLEAN_TEMP=true
                shift
                ;;
            --no-skip)
                SKIP_EXISTING=false
                shift
                ;;
            --reinstall-packages)
                REINSTALL_PACKAGES=true
                shift
                ;;
            --start-step)
                STEP_START="$2"
                if [[ ! "$STEP_START" =~ ^[1-7]$ ]]; then
                    log_error "Invalid start step: $STEP_START (must be 1-7)"
                    exit 2
                fi
                shift 2
                ;;
            --end-step)
                STEP_END="$2"
                if [[ ! "$STEP_END" =~ ^[1-7]$ ]]; then
                    log_error "Invalid end step: $STEP_END (must be 1-7)"
                    exit 2
                fi
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --model)
                MODEL_OVERRIDE="$2"
                shift 2
                ;;
            --sample-only)
                SAMPLE_ONLY=true
                shift
                ;;
            --output-format)
                OUTPUT_FORMAT="$2"
                shift 2
                ;;
            --bilingual-style)
                BILINGUAL_STYLE="$2"
                shift 2
                ;;
            --benchmark)
                BENCHMARK_MODE=true
                shift
                ;;
            --quota-status)
                QUOTA_STATUS_MODE=true
                shift
                ;;
            --epub-baseline)
                EPUB_BASELINE=true
                shift
                ;;
            --epub-translate-roundtrip)
                if [[ -n "$WORKFLOW_OVERRIDE" ]] && [[ "$WORKFLOW_OVERRIDE" != "epub" ]]; then
                    log_error "Conflict: --epub-translate-roundtrip cannot be used with --workflow $WORKFLOW_OVERRIDE"
                    exit 2
                fi
                EPUB_TRANSLATE_ROUNDTRIP=true
                WORKFLOW_OVERRIDE="epub"
                USED_LEGACY_ROUNDTRIP_FLAG=true
                shift
                ;;
            --workflow)
                WORKFLOW_OVERRIDE="$2"
                shift 2
                ;;
            --provider)
                PROVIDER="$2"
                shift 2
                ;;
            --fallback-provider)
                FALLBACK_PROVIDER="$2"
                shift 2
                ;;
            --force-resume)
                FORCE_RESUME=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            -*)
                log_error "Unknown option: $1"
                echo "Use -h or --help for usage information"
                exit 2
                ;;
            *)
                if [[ -z "$INPUT_FILE" ]]; then
                    INPUT_FILE="$1"
                else
                    log_error "Multiple input files specified"
                    exit 2
                fi
                shift
                ;;
        esac
    done
    
    # Validate arguments
    if [[ -z "$INPUT_FILE" ]]; then
        log_error "Input file is required"
        echo "Use -h or --help for usage information"
        exit 2
    fi
    
    if [[ ! -f "$INPUT_FILE" ]]; then
        log_error "Input file not found: $INPUT_FILE"
        exit 5
    fi
    
    if [[ $STEP_START -gt $STEP_END ]]; then
        log_error "Start step ($STEP_START) cannot be greater than end step ($STEP_END)"
        exit 2
    fi

    if [[ ! "$OUTPUT_FORMAT" =~ ^(epub|pdf|docx|html|all)$ ]]; then
        log_error "Invalid output format: $OUTPUT_FORMAT (must be epub|pdf|docx|html|all)"
        exit 2
    fi

    if [[ ! "$BILINGUAL_STYLE" =~ ^(alternating)$ ]]; then
        log_error "Invalid bilingual style: $BILINGUAL_STYLE (supported: alternating)"
        exit 2
    fi

    if [[ -n "$WORKFLOW_OVERRIDE" ]] && [[ ! "$WORKFLOW_OVERRIDE" =~ ^(epub|markdown)$ ]]; then
        log_error "Invalid workflow mode: $WORKFLOW_OVERRIDE (must be epub|markdown)"
        exit 2
    fi

    if [[ ! "$PROVIDER" =~ ^(cli|api)$ ]]; then
        log_error "Invalid provider: $PROVIDER (must be cli|api)"
        exit 2
    fi

    if [[ -n "$FALLBACK_PROVIDER" ]]; then
        if [[ ! "$FALLBACK_PROVIDER" =~ ^(api)$ ]]; then
            log_error "Invalid fallback provider: $FALLBACK_PROVIDER (supported: api)"
            exit 2
        fi
        if [[ "$PROVIDER" != "cli" ]]; then
            log_error "--fallback-provider is only supported when --provider cli"
            exit 2
        fi
    fi
}

# Resolve temp directory name based on input basename (matches 01_convert_to_htmlz.py)
resolve_temp_dir() {
    local input_file_path="${1:-$INPUT_FILE}"
    local input_file_name
    input_file_name="$(basename "$input_file_path")"
    echo "${input_file_name%.*}_temp"
}

# Execute Python script with error handling
execute_python_script() {
    local script_name="$1"
    local step_num="$2"
    local description="$3"
    
    log_step "$step_num" "$description"
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY RUN] Would execute: python3 ${script_name}"
        return 0
    fi
    
    # Ensure virtual environment is activated before running Python scripts
    local venv_dir="${SCRIPT_DIR}/venv"
    if [[ -d "$venv_dir" ]]; then
        source "$venv_dir/bin/activate"
    fi
    
    local cmd="python3 ${SCRIPT_DIR}/${script_name}"
    
    if [[ "$VERBOSE" == true ]]; then
        log_info "Executing: $cmd"
    fi
    
    if ! $cmd; then
        log_error "Step $step_num failed: $description"
        log_error "Command: $cmd"
        exit 1
    fi
    
    log_success "Step $step_num completed: $description"
}

# Clean temporary directory
clean_temp_directory() {
    local temp_dir="${1:-$(resolve_temp_dir "$INPUT_FILE")}"
    if [[ "$CLEAN_TEMP" == true ]]; then
        if [[ -d "$temp_dir" ]]; then
            log_info "Cleaning temporary directory: $temp_dir"
            if [[ "$DRY_RUN" == false ]]; then
                rm -rf "$temp_dir"
            fi
            log_success "Temporary directory cleaned"
        fi
    fi
}

# Show configuration
show_config() {
    log_info "Configuration:"
    echo "  Input file: $INPUT_FILE"
    echo "  Input language: $INPUT_LANG"
    echo "  Output language: $OUTPUT_LANG"
    echo "  Custom prompt: ${CUSTOM_PROMPT:-'None'}"
    echo "  Extract glossary: ${EXTRACT_GLOSSARY}"
    echo "  Glossary path:    ${GLOSSARY_PATH:-'None'}"
  echo "  Glossary min pri: ${GLOSSARY_MIN_PRIORITY:-'all'}"
    echo "  Steps to run: $STEP_START-$STEP_END"
    echo "  Clean temp: $CLEAN_TEMP"
    echo "  Skip existing: $SKIP_EXISTING"
    echo "  Model override: ${MODEL_OVERRIDE:-'auto'}"
    echo "  Sample only: $SAMPLE_ONLY"
    echo "  Output format: $OUTPUT_FORMAT"
    echo "  Bilingual style: $BILINGUAL_STYLE"
    echo "  Benchmark mode: $BENCHMARK_MODE"
    echo "  Quota status mode: $QUOTA_STATUS_MODE"
    echo "  EPUB baseline mode: $EPUB_BASELINE"
    echo "  EPUB translate roundtrip mode: $EPUB_TRANSLATE_ROUNDTRIP"
    echo "  Workflow override: ${WORKFLOW_OVERRIDE:-auto}"
    echo "  Resolved workflow: $RESOLVED_WORKFLOW"
    echo "  Provider: $PROVIDER"
    echo "  Fallback provider: ${FALLBACK_PROVIDER:-none}"
    echo "  Verbose: $VERBOSE"
    echo "  Dry run: $DRY_RUN"
    echo ""
}

show_quota_status() {
    local db_path="${HOME}/.config/translatebook/quota.db"
    log_info "Quota status for today (UTC):"
    if [[ ! -f "$db_path" ]]; then
        echo "  No quota database found at $db_path"
        return 0
    fi
    python3 - <<'PY'
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

db = Path.home() / ".config" / "translatebook" / "quota.db"
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
conn = sqlite3.connect(db)
rows = conn.execute(
    "SELECT model, COALESCE(SUM(token_count),0) FROM quota_usage WHERE date=? GROUP BY model ORDER BY model",
    (today,),
).fetchall()
conn.close()
if not rows:
    print("  No usage records for today.")
else:
    for model, total in rows:
        print(f"  {model}: {int(total)} tokens")
PY
}

# Main execution function
main() {
    # Show banner
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  Book Translation Tool v${VERSION}${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
    
    # Parse arguments
    parse_args "$@"

    if [[ "$SAMPLE_ONLY" == true ]]; then
        STEP_START=3
        STEP_END=4
    fi

    local base_temp_dir
    base_temp_dir="$(resolve_temp_dir "$INPUT_FILE")"
    RESOLVED_WORKFLOW="$(resolve_workflow_for_input "$INPUT_FILE" "$WORKFLOW_OVERRIDE")"
    
    # Show configuration
    show_config

    if [[ "$USED_LEGACY_ROUNDTRIP_FLAG" == true ]]; then
        log_warning "Deprecated option: --epub-translate-roundtrip is kept for compatibility; use --workflow epub"
    fi
    
    if [[ "$QUOTA_STATUS_MODE" == true ]]; then
        show_quota_status
        exit 0
    fi

    if [[ "$EPUB_BASELINE" == true ]]; then
        if ! is_epub_file "$INPUT_FILE"; then
            log_error "--epub-baseline requires an EPUB input file"
            exit 2
        fi

        local baseline_output="${base_temp_dir}/baseline_roundtrip.epub"
        local baseline_script="${SCRIPT_DIR}/08_epub_roundtrip_baseline.py"
        local baseline_cmd_display="python3 ${baseline_script} \"$INPUT_FILE\" --output \"$baseline_output\""

        if [[ ! -f "$baseline_script" ]]; then
            log_error "Baseline script not found: $baseline_script"
            exit 3
        fi

        if ! command -v python3 &> /dev/null; then
            log_error "Python 3 is required but not installed"
            exit 3
        fi

        log_step "baseline" "Roundtrip EPUB baseline mode (no text mutation)"
        if [[ "$DRY_RUN" == true ]]; then
            log_info "[DRY RUN] Would execute: $baseline_cmd_display"
            exit 0
        fi

        if [[ "$VERBOSE" == true ]]; then
            log_info "Executing: $baseline_cmd_display"
        fi

        if ! python3 "$baseline_script" "$INPUT_FILE" --output "$baseline_output"; then
            log_error "EPUB baseline roundtrip failed"
            exit 1
        fi

        log_success "EPUB baseline completed: ${baseline_output}"
        exit 0
    fi

    if [[ "$RESOLVED_WORKFLOW" == "epub" ]]; then
        if ! is_epub_file "$INPUT_FILE"; then
            log_error "workflow 'epub' requires an EPUB input file"
            exit 2
        fi

        local translate_output="${base_temp_dir}/translated_roundtrip.epub"
        local checkpoint_dir="${base_temp_dir}/roundtrip_checkpoint"
        local translate_script="${SCRIPT_DIR}/09_epub_translate_roundtrip.py"

        if [[ ! -f "$translate_script" ]]; then
            log_error "Translate roundtrip script not found: $translate_script"
            exit 3
        fi

        if ! command -v python3 &> /dev/null; then
            log_error "Python 3 is required but not installed"
            exit 3
        fi

        # Optional: glossary extraction
        local _glossary_output=""
        if [[ "$EXTRACT_GLOSSARY" == true ]]; then
            local _glossary_output="${base_temp_dir}/extracted_glossary.json"
            log_step "workflow-epub" "Extracting terminology glossary"
            local _extract_cmd=(
                python3 -u "${SCRIPT_DIR}/00_extract_glossary.py"
                "$INPUT_FILE"
                --output "$_glossary_output"
                --model "${MODEL_OVERRIDE:-pro}"
                --provider "$PROVIDER"
            )
            if [[ "$DRY_RUN" == true ]]; then
                log_info "[DRY RUN] Would execute: ${_extract_cmd[*]}"
                _glossary_output=""
            else
                "${_extract_cmd[@]}" || { log_error "Glossary extraction failed"; exit 1; }
            fi
        elif [[ -n "$GLOSSARY_PATH" ]]; then
            _glossary_output="$GLOSSARY_PATH"
        fi

        local cmd=(
            python3 -u "$translate_script" "$INPUT_FILE"
            --output "$translate_output"
            --output-lang "$OUTPUT_LANG"
            --bilingual-style "$BILINGUAL_STYLE"
            --checkpoint-dir "$checkpoint_dir"
            --provider "$PROVIDER"
        )
        if [[ -n "$MODEL_OVERRIDE" ]]; then
            cmd+=(--model "$MODEL_OVERRIDE")
        fi
        if [[ -n "$CUSTOM_PROMPT" ]]; then
            cmd+=(-p "$CUSTOM_PROMPT")
        fi
        if [[ -n "$_glossary_output" ]]; then
            cmd+=(--glossary "$_glossary_output")
            if [[ -n "$GLOSSARY_MIN_PRIORITY" ]]; then
                cmd+=(--glossary-min-priority "$GLOSSARY_MIN_PRIORITY")
            fi
        fi
        if [[ "$FORCE_RESUME" == true ]]; then
            cmd+=(--force-resume)
        fi
        if [[ "$FALLBACK_PROVIDER" == "api" ]]; then
            cmd+=(--cli-api-fallback)
        fi

        local translate_cmd_display
        translate_cmd_display="$(printf '%q ' "${cmd[@]}")"

        log_step "workflow-epub" "EPUB package-preserving translation workflow"
        if [[ "$DRY_RUN" == true ]]; then
            log_info "[DRY RUN] Would execute: $translate_cmd_display"
            exit 0
        fi

        setup_venv
        if [[ "$PROVIDER" == "api" ]]; then
            if ! python3 -c "from google import genai" >/dev/null 2>&1; then
                log_info "Installing Gemini API SDK into venv..."
                if ! uv pip install google-genai; then
                    log_error "Failed to install google-genai for API provider"
                    exit 3
                fi
            fi
        fi
        log_info "Starting translate roundtrip (progress logs will show per spine document)..."
        if [[ "$PROVIDER" == "cli" ]]; then
            if ! command -v gemini &> /dev/null; then
                log_error "Gemini CLI not found"
                log_error "Please install Gemini CLI and ensure 'gemini' is in PATH"
                exit 4
            fi
        fi

        if [[ "$VERBOSE" == true ]]; then
            log_info "Executing: $translate_cmd_display"
        fi

        if ! "${cmd[@]}"; then
            log_error "EPUB translate roundtrip failed"
            exit 1
        fi

        log_success "EPUB translate roundtrip completed: ${translate_output}"
        exit 0
    fi

    # Setup Python virtual environment
    setup_venv
    
    # Check dependencies
    check_dependencies
    
    # Clean temp directory if requested
    clean_temp_directory "$base_temp_dir"
    
    # Record start time
    local start_time=$(date +%s)
    
    # Convert supported file formats using Calibre HTMLZ method
    if is_supported_source_file "$INPUT_FILE"; then
        log_info "Detected supported file format, converting via Calibre HTMLZ..."
        
        local original_file="$INPUT_FILE"
        
        if [[ "$DRY_RUN" == true ]]; then
            log_info "[DRY RUN] Would convert file to markdown chunks: $original_file"
        else
            # Ensure virtual environment is activated
            local venv_dir="${SCRIPT_DIR}/venv"
            if [[ -d "$venv_dir" ]]; then
                source "$venv_dir/bin/activate"
            fi
            
            # Check if 01_convert_to_htmlz.py exists
            if [[ ! -f "${SCRIPT_DIR}/01_convert_to_htmlz.py" ]]; then
                log_error "File converter not found: 01_convert_to_htmlz.py"
                exit 3
            fi
            
            # Convert file using new method
            local convert_cmd="python3 ${SCRIPT_DIR}/01_convert_to_htmlz.py \"$original_file\" -l \"$INPUT_LANG\" --olang \"$OUTPUT_LANG\""
            
            if [[ "$VERBOSE" == true ]]; then
                log_info "Executing: $convert_cmd"
            fi
            
            if ! eval $convert_cmd; then
                log_error "File conversion failed"
                exit 1
            fi
            
            log_success "File converted to markdown chunks successfully"
            
            # The conversion creates a temp directory with markdown files
            # Skip step 1 and 2 since conversion is already done
            STEP_START=3
        fi
    fi

    if [[ "$BENCHMARK_MODE" == true ]]; then
        local benchmark_cmd="python3 ${SCRIPT_DIR}/benchmark_models.py --temp-dir \"$base_temp_dir\" --output-lang \"$OUTPUT_LANG\""
        if [[ "$DRY_RUN" == true ]]; then
            log_info "[DRY RUN] Would execute: $benchmark_cmd"
            exit 0
        fi
        if [[ "$VERBOSE" == true ]]; then
            log_info "Executing: $benchmark_cmd"
        fi
        if ! eval $benchmark_cmd; then
            log_error "Benchmark failed"
            exit 1
        fi
        log_success "Benchmark complete"
        exit 0
    fi
    
    # Execute steps
    local step_descriptions=(
        "Environment preparation and parameter parsing"
        "Split file to markdown and extract images"
        "Translate markdown files using Gemini CLI"
        "Merge translated markdown files"
        "Convert markdown to HTML with template"
        "Generate and insert table of contents"
        "Generate final format files in temp directory"
    )
    
    local step_scripts=(
        "01_prepare_env.py"
        "02_split_to_md.py"
        "03_translate_md.py"
        "04_merge_md.py"
        "05_md_to_html.py"
        "06_add_toc.py"
        "07_generate_formats.py"
    )
    
    # Execute Step 1 with parameters if it's in range
    if [[ $STEP_START -le 1 && $STEP_END -ge 1 ]]; then
        log_step "1" "${step_descriptions[0]}"
        
        if [[ "$DRY_RUN" == true ]]; then
            log_info "[DRY RUN] Would execute: python3 ${step_scripts[0]} with parameters"
        else
            # Ensure virtual environment is activated before running Python scripts
            local venv_dir="${SCRIPT_DIR}/venv"
            if [[ -d "$venv_dir" ]]; then
                source "$venv_dir/bin/activate"
            fi
            
            local cmd="python3 ${SCRIPT_DIR}/${step_scripts[0]} \"$INPUT_FILE\" -l \"$INPUT_LANG\" --olang \"$OUTPUT_LANG\""
            
            if [[ "$VERBOSE" == true ]]; then
                log_info "Executing: $cmd"
            fi
            
            if ! eval $cmd; then
                log_error "Step 1 failed: ${step_descriptions[0]}"
                exit 1
            fi
            
            log_success "Step 1 completed: ${step_descriptions[0]}"
        fi
    fi
    
    # Execute remaining steps
    for i in $(seq 2 7); do
        if [[ $STEP_START -le $i && $STEP_END -ge $i ]]; then
            # Special handling for step 3 (translation) with custom prompt
            if [[ $i -eq 3 && -n "$CUSTOM_PROMPT" ]]; then
                log_step "3" "${step_descriptions[2]}"
                
                if [[ "$DRY_RUN" == true ]]; then
                    local cmd="python3 ${SCRIPT_DIR}/${step_scripts[2]} --temp-dir \"$base_temp_dir\" -p \"$CUSTOM_PROMPT\""
                    if [[ "$SKIP_EXISTING" == false ]]; then
                        cmd="$cmd --no-resume"
                    fi
                    if [[ -n "$MODEL_OVERRIDE" ]]; then
                        cmd="$cmd --model \"$MODEL_OVERRIDE\""
                    fi
                    log_info "[DRY RUN] Would execute: $cmd"
                    local preview_cmd="$cmd --preview-model-selection --skip-probe"
                    log_info "[DRY RUN] Previewing prompt profile and model selection..."
                    if ! eval $preview_cmd; then
                        log_warning "[DRY RUN] Model selection preview failed"
                    fi
                else
                    # Ensure virtual environment is activated before running Python scripts
                    local venv_dir="${SCRIPT_DIR}/venv"
                    if [[ -d "$venv_dir" ]]; then
                        source "$venv_dir/bin/activate"
                    fi
                    
                    local cmd="python3 ${SCRIPT_DIR}/${step_scripts[2]} --temp-dir \"$base_temp_dir\" -p \"$CUSTOM_PROMPT\""
                    if [[ "$SKIP_EXISTING" == false ]]; then
                        cmd="$cmd --no-resume"
                    fi
                    if [[ -n "$MODEL_OVERRIDE" ]]; then
                        cmd="$cmd --model \"$MODEL_OVERRIDE\""
                    fi
                    
                    if [[ "$VERBOSE" == true ]]; then
                        log_info "Executing: $cmd"
                    fi
                    
                    if ! eval $cmd; then
                        log_error "Step 3 failed: ${step_descriptions[2]}"
                        log_error "Translation is incomplete. Please fix the issues and run again."
                        exit 1
                    fi
                    
                    log_success "Step 3 completed: ${step_descriptions[2]}"
                fi
            elif [[ $i -eq 6 ]]; then
                # Special handling for step 6 (TOC generation) with base_temp/book.html output
                log_step "6" "${step_descriptions[5]}"
                
                if [[ "$DRY_RUN" == true ]]; then
                    log_info "[DRY RUN] Would execute: python3 ${step_scripts[5]} with base_temp/book.html output"
                else
                    # Ensure virtual environment is activated before running Python scripts
                    local venv_dir="${SCRIPT_DIR}/venv"
                    if [[ -d "$venv_dir" ]]; then
                        source "$venv_dir/bin/activate"
                    fi
                    
                    if [[ ! -d "$base_temp_dir" ]]; then
                        log_error "Temp directory not found: $base_temp_dir"
                        exit 1
                    fi
                    
                    # Step 6 will process book.html in the temp directory directly
                    local cmd="python3 ${SCRIPT_DIR}/${step_scripts[5]}"
                    
                    if [[ "$VERBOSE" == true ]]; then
                        log_info "Executing: $cmd"
                    fi
                    
                    if ! eval $cmd; then
                        log_error "Step 6 failed: ${step_descriptions[5]}"
                        exit 1
                    fi
                    
                    log_success "Step 6 completed: ${step_descriptions[5]} -> ${base_temp_dir}/book.html"
                fi
            else
                # Special handling for step 3 (translation) to pass temp directory
                if [[ $i -eq 3 ]]; then
                    log_step "3" "${step_descriptions[2]}"
                    
                    if [[ "$DRY_RUN" == true ]]; then
                        local cmd="python3 ${SCRIPT_DIR}/${step_scripts[2]} --temp-dir \"$base_temp_dir\""
                        if [[ "$SKIP_EXISTING" == false ]]; then
                            cmd="$cmd --no-resume"
                        fi
                        if [[ -n "$MODEL_OVERRIDE" ]]; then
                            cmd="$cmd --model \"$MODEL_OVERRIDE\""
                        fi
                        log_info "[DRY RUN] Would execute: $cmd"
                        local preview_cmd="$cmd --preview-model-selection --skip-probe"
                        log_info "[DRY RUN] Previewing prompt profile and model selection..."
                        if ! eval $preview_cmd; then
                            log_warning "[DRY RUN] Model selection preview failed"
                        fi
                    else
                        # Ensure virtual environment is activated before running Python scripts
                        local venv_dir="${SCRIPT_DIR}/venv"
                        if [[ -d "$venv_dir" ]]; then
                            source "$venv_dir/bin/activate"
                        fi
                        
                        local cmd="python3 ${SCRIPT_DIR}/${step_scripts[2]} --temp-dir \"$base_temp_dir\""
                        if [[ "$SKIP_EXISTING" == false ]]; then
                            cmd="$cmd --no-resume"
                        fi
                        if [[ -n "$MODEL_OVERRIDE" ]]; then
                            cmd="$cmd --model \"$MODEL_OVERRIDE\""
                        fi
                        
                        if [[ "$VERBOSE" == true ]]; then
                            log_info "Executing: $cmd"
                        fi
                        
                        if ! eval $cmd; then
                            log_error "Step 3 failed: ${step_descriptions[2]}"
                            exit 1
                        fi
                        
                        log_success "Step 3 completed: ${step_descriptions[2]}"
                    fi
                elif [[ $i -eq 4 ]]; then
                    # Special handling for step 4 (merge) to pass temp directory
                    log_step "4" "${step_descriptions[3]}"
                    
                    if [[ "$DRY_RUN" == true ]]; then
                        log_info "[DRY RUN] Would execute: python3 ${step_scripts[3]} --temp-dir \"$base_temp_dir\""
                    else
                        # Ensure virtual environment is activated before running Python scripts
                        local venv_dir="${SCRIPT_DIR}/venv"
                        if [[ -d "$venv_dir" ]]; then
                            source "$venv_dir/bin/activate"
                        fi
                        
                        local cmd="python3 ${SCRIPT_DIR}/${step_scripts[3]} --temp-dir \"$base_temp_dir\""
                        
                        if [[ "$VERBOSE" == true ]]; then
                            log_info "Executing: $cmd"
                        fi
                        
                        if ! eval $cmd; then
                            log_error "Step 4 failed: ${step_descriptions[3]}"
                            exit 1
                        fi
                        
                        log_success "Step 4 completed: ${step_descriptions[3]}"
                    fi
                elif [[ $i -eq 5 ]]; then
                    # Special handling for step 5 (md to html) to pass temp directory
                    log_step "5" "${step_descriptions[4]}"
                    
                    if [[ "$DRY_RUN" == true ]]; then
                        log_info "[DRY RUN] Would execute: python3 ${step_scripts[4]} --temp-dir \"$base_temp_dir\" --bilingual-style \"$BILINGUAL_STYLE\""
                    else
                        # Ensure virtual environment is activated before running Python scripts
                        local venv_dir="${SCRIPT_DIR}/venv"
                        if [[ -d "$venv_dir" ]]; then
                            source "$venv_dir/bin/activate"
                        fi
                        
                        local cmd="python3 ${SCRIPT_DIR}/${step_scripts[4]} --temp-dir \"$base_temp_dir\" --bilingual-style \"$BILINGUAL_STYLE\""
                        
                        if [[ "$VERBOSE" == true ]]; then
                            log_info "Executing: $cmd"
                        fi
                        
                        if ! eval $cmd; then
                            log_error "Step 5 failed: ${step_descriptions[4]}"
                            exit 1
                        fi
                        
                        log_success "Step 5 completed: ${step_descriptions[4]}"
                    fi
                elif [[ $i -eq 7 ]]; then
                    # Special handling for step 7 (format generation) to pass temp directory and output format
                    log_step "7" "${step_descriptions[6]}"

                    if [[ "$DRY_RUN" == true ]]; then
                        log_info "[DRY RUN] Would execute: python3 ${step_scripts[6]} --temp-dir \"$base_temp_dir\" --output-format \"$OUTPUT_FORMAT\""
                    else
                        local venv_dir="${SCRIPT_DIR}/venv"
                        if [[ -d "$venv_dir" ]]; then
                            source "$venv_dir/bin/activate"
                        fi

                        local cmd="python3 ${SCRIPT_DIR}/${step_scripts[6]} --temp-dir \"$base_temp_dir\" --output-format \"$OUTPUT_FORMAT\""

                        if [[ "$VERBOSE" == true ]]; then
                            log_info "Executing: $cmd"
                        fi

                        if ! eval $cmd; then
                            log_error "Step 7 failed: ${step_descriptions[6]}"
                            exit 1
                        fi

                        log_success "Step 7 completed: ${step_descriptions[6]}"
                    fi
                else
                    execute_python_script "${step_scripts[$((i-1))]}" "$i" "${step_descriptions[$((i-1))]}"
                fi
            fi
        fi
    done
    
    # Calculate execution time
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Show completion message
    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}  Translation Complete!${NC}"
    echo -e "${GREEN}================================${NC}"
    
    if [[ "$DRY_RUN" == false ]]; then
        echo -e "${GREEN}✓ Input file:${NC} $INPUT_FILE"
        echo -e "${GREEN}✓ Execution time:${NC} ${duration}s"
        echo -e "${GREEN}✓ Files generated in temp directory:${NC} ${base_temp_dir}/"
    else
        echo -e "${YELLOW}Note: This was a dry run. No files were modified.${NC}"
    fi
    
    echo ""
    log_success "All steps completed successfully!"
}

# Handle interruption
trap 'log_error "Script interrupted by user"; exit 1' INT TERM

# Run main function only when executed directly (not when sourced by tests)
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
