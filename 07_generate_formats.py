#!/usr/bin/env python3
"""
Step 7: Generate DOCX and EPUB files in temp directory
Uses existing html2docx.sh and html2epub.sh scripts to generate files in temp directory
"""

from __future__ import annotations

import os
import sys
import subprocess
import argparse
import glob


def log_info(message: str) -> None:
    """Log info message"""
    print(f"[INFO] {message}")


def log_success(message: str) -> None:
    """Log success message"""
    print(f"[SUCCESS] {message}")


def log_error(message: str) -> None:
    """Log error message"""
    print(f"[ERROR] {message}")


def log_warning(message: str) -> None:
    """Log warning message"""
    print(f"[WARNING] {message}")


def load_config() -> dict[str, str] | None:
    """Load configuration from temp directory"""
    # Look for config files in temp directories - use the same logic as main
    config_files = []

    # Check for config.txt files in temp directories
    import glob

    temp_dirs = glob.glob("*_temp")
    for temp_dir in temp_dirs:
        config_file = os.path.join(temp_dir, "config.txt")
        if os.path.exists(config_file):
            config_files.append(config_file)

    # Also check current directory as fallback
    if os.path.exists("config.txt"):
        config_files.append("config.txt")

    if not config_files:
        return None

    # Use the most recent config file
    config_file = max(config_files, key=os.path.getmtime)

    config = {}
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key] = value
        return config
    except Exception as e:
        log_warning(f"Could not read config file {config_file}: {e}")
        return None


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Step 7: Generate final output formats from HTML")
    parser.add_argument(
        "--temp-dir",
        default=None,
        help="Temp directory path. If omitted, auto-detect from *_temp/config.txt",
    )
    parser.add_argument(
        "--output-format",
        choices=["docx", "epub", "pdf", "html", "all"],
        default="all",
        help="Format to generate. 'html' means skip conversions in step 7.",
    )
    return parser.parse_args()


def resolve_output_formats(output_format: str) -> list[str]:
    """Resolve requested output format into concrete generation targets."""
    if output_format == "all":
        return ["docx", "epub", "pdf"]
    if output_format == "html":
        return []
    return [output_format]


def resolve_html_input_file(temp_dir: str) -> str:
    """Resolve source HTML file for format conversion."""
    preferred_names = ["book_doc.html", "book.html"]
    for name in preferred_names:
        candidate = os.path.join(temp_dir, name)
        if os.path.exists(candidate):
            return candidate

    html_files = glob.glob(os.path.join(temp_dir, "*.html"))
    if html_files:
        return max(html_files, key=os.path.getmtime)

    raise FileNotFoundError(f"No HTML files found in temp directory: {temp_dir}")


def _run_ebook_convert(
    html_file: str, output_file: str, metadata: dict[str, str] | None = None
) -> bool:
    """Convert HTML into a target format using Calibre ebook-convert."""
    cmd = ["ebook-convert", html_file, output_file]
    meta = metadata or {}
    title = meta.get("title")
    creator = meta.get("creator")
    publisher = meta.get("publisher")
    if title:
        cmd.extend(["--title", title])
    if creator:
        cmd.extend(["--authors", creator])
    if publisher:
        cmd.extend(["--publisher", publisher])

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if isinstance(e.stderr, str) else str(e.stderr)
        log_error(f"ebook-convert failed: {stderr}")
        if e.stdout:
            log_info(f"ebook-convert output: {e.stdout}")
        return False
    except FileNotFoundError:
        log_error("ebook-convert not found. Install Calibre: https://calibre-ebook.com/")
        return False

    if os.path.exists(output_file):
        if result.stdout:
            log_info(f"ebook-convert output: {result.stdout}")
        return True

    log_error(f"Conversion finished but output file not found: {output_file}")
    if result.stdout:
        log_info(f"ebook-convert output: {result.stdout}")
    return False


def generate_docx_with_script(
    html_file: str, temp_dir: str, metadata: dict[str, str] | None = None
) -> str | None:
    """Generate DOCX file using ebook-convert."""
    # Create output filename in temp directory - use book.docx as requested
    docx_file = os.path.join(temp_dir, "book.docx")

    # Skip if DOCX already exists
    if os.path.exists(docx_file):
        log_info(f"Skipping DOCX generation - file already exists: {docx_file}")
        file_size = os.path.getsize(docx_file)
        log_success(f"Found existing DOCX: {docx_file} ({file_size} bytes)")
        return docx_file

    log_info("Generating DOCX file using ebook-convert...")
    if _run_ebook_convert(html_file, docx_file, metadata):
        log_success(f"DOCX file created: {docx_file}")
        return docx_file
    return None


def generate_epub_with_script(
    html_file: str, temp_dir: str, metadata: dict[str, str] | None = None
) -> str | None:
    """Generate EPUB file using ebook-convert."""
    # Create output filename in temp directory - use book.epub as requested
    epub_file = os.path.join(temp_dir, "book.epub")

    # Skip if EPUB already exists
    if os.path.exists(epub_file):
        log_info(f"Skipping EPUB generation - file already exists: {epub_file}")
        file_size = os.path.getsize(epub_file)
        log_success(f"Found existing EPUB: {epub_file} ({file_size} bytes)")
        return epub_file

    log_info("Generating EPUB file using ebook-convert...")
    if _run_ebook_convert(html_file, epub_file, metadata):
        log_success(f"EPUB file created: {epub_file}")
        return epub_file
    return None


def generate_pdf_with_script(
    html_file: str, temp_dir: str, metadata: dict[str, str] | None = None
) -> str | None:
    """Generate PDF file using ebook-convert."""
    # Create output filename in temp directory - use book.pdf as requested
    pdf_file = os.path.join(temp_dir, "book.pdf")

    # Skip if PDF already exists
    if os.path.exists(pdf_file):
        log_info(f"Skipping PDF generation - file already exists: {pdf_file}")
        file_size = os.path.getsize(pdf_file)
        log_success(f"Found existing PDF: {pdf_file} ({file_size} bytes)")
        return pdf_file

    log_info("Generating PDF file using ebook-convert...")
    if _run_ebook_convert(html_file, pdf_file, metadata):
        log_success(f"PDF file created: {pdf_file}")
        return pdf_file
    return None


def main() -> None:
    """Main function"""
    args = parse_arguments()
    requested_formats = resolve_output_formats(args.output_format)
    if requested_formats:
        log_info(f"Starting Step 7: Generate {', '.join(fmt.upper() for fmt in requested_formats)}")
    else:
        log_info("Starting Step 7: Output format is HTML, skipping format conversion")

    # Load configuration
    config = load_config()
    if not config:
        log_error("Could not find configuration file. Please ensure step 1 completed successfully.")
        sys.exit(1)

    # Get temp directory
    temp_dir = args.temp_dir or config.get("temp_dir")
    output_lang = config.get("output_lang", "zh")

    # If temp_dir not specified in config, try to determine from config file location
    if not temp_dir:
        # Try to determine from the config file path
        config_files = []

        # Check for config.txt files in temp directories
        import glob

        temp_dirs = glob.glob("*_temp")
        for temp_dir_candidate in temp_dirs:
            config_file = os.path.join(temp_dir_candidate, "config.txt")
            if os.path.exists(config_file):
                config_files.append((config_file, temp_dir_candidate))

        if config_files:
            # Use the most recent config file's directory
            _, temp_dir = max(config_files, key=lambda x: os.path.getmtime(x[0]))
            log_info(f"Using temp directory from config location: {temp_dir}")
        else:
            log_error("No temp directory found and none specified in config.")
            sys.exit(1)

    try:
        html_file = resolve_html_input_file(temp_dir)
    except FileNotFoundError as e:
        log_error(str(e))
        log_error("Please ensure step 5 (HTML generation) completed successfully.")
        sys.exit(1)

    # Extract metadata from config (title should already be translated in step 5)
    original_title = config.get("original_title", "")
    creator = config.get("creator", "")
    publisher = config.get("publisher", "")

    log_info(f"Processing HTML file: {html_file}")
    log_info(f"Output directory: {temp_dir}")

    # Ensure temp directory exists
    os.makedirs(temp_dir, exist_ok=True)

    # Prepare metadata dictionary for generation scripts
    book_metadata = {}
    if original_title:
        book_metadata["title"] = original_title  # Use original title for metadata
    if creator:
        book_metadata["creator"] = creator
    if publisher:
        book_metadata["publisher"] = publisher

    if not requested_formats:
        log_success("No format conversion requested (output-format=html).")
        log_success(f"HTML remains available at: {html_file}")
        return

    docx_file = None
    epub_file = None
    pdf_file = None

    if "docx" in requested_formats:
        docx_file = generate_docx_with_script(html_file, temp_dir, book_metadata)
    if "epub" in requested_formats:
        epub_file = generate_epub_with_script(html_file, temp_dir, book_metadata)
    if "pdf" in requested_formats:
        pdf_file = generate_pdf_with_script(html_file, temp_dir, book_metadata)

    # Report results
    generated_files = []
    if docx_file:
        file_size = os.path.getsize(docx_file)
        log_success(f"DOCX: {docx_file} ({file_size} bytes)")
        generated_files.append("DOCX")
    if epub_file:
        file_size = os.path.getsize(epub_file)
        log_success(f"EPUB: {epub_file} ({file_size} bytes)")
        generated_files.append("EPUB")
    if pdf_file:
        file_size = os.path.getsize(pdf_file)
        log_success(f"PDF: {pdf_file} ({file_size} bytes)")
        generated_files.append("PDF")

    if generated_files:
        log_success(f"Format generation completed! Generated: {', '.join(generated_files)}")
        log_success(f"All files saved to: {temp_dir}")
    else:
        log_error("No files were generated")
        sys.exit(1)


if __name__ == "__main__":
    main()
