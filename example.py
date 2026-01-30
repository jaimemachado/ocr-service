#!/usr/bin/env python3
"""
Example script demonstrating how to use the OCR service
"""
import os
import sys
from typing import Any

import requests


def process_pdf(
    pdf_path: str, output_path: str, service_url: str = "http://localhost:8000"
) -> bool:
    """
    Process a PDF file using the OCR service.

    Args:
        pdf_path: Path to input PDF file
        output_path: Path to save output PDF with text layer
        service_url: URL of the OCR service

    Returns:
        True if processing succeeded, False otherwise
    """
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        return False
    
    print(f"Processing: {pdf_path}")
    print(f"Service: {service_url}")
    
    try:
        # Upload and process PDF
        with open(pdf_path, "rb") as f:
            response = requests.post(
                f"{service_url}/process-pdf",
                files={"file": (os.path.basename(pdf_path), f, "application/pdf")}
            )
        
        if response.status_code == 200:
            # Save processed PDF
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"✓ Success! Saved to: {output_path}")
            return True
        else:
            print(f"✗ Error: {response.status_code}")
            print(f"Details: {response.text}")
            return False
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def extract_text(pdf_path: str, service_url: str = "http://localhost:8000") -> dict[str, Any] | None:
    """
    Extract text from a PDF file using the OCR service.

    Args:
        pdf_path: Path to input PDF file
        service_url: URL of the OCR service

    Returns:
        Dictionary with extracted text data, or None on failure
    """
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        return None
    
    print(f"Extracting text from: {pdf_path}")
    print(f"Service: {service_url}")
    
    try:
        # Upload and extract text
        with open(pdf_path, "rb") as f:
            response = requests.post(
                f"{service_url}/extract-text",
                files={"file": (os.path.basename(pdf_path), f, "application/pdf")}
            )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Extracted text from {len(data['pages'])} pages")
            print("\n--- Full Text ---")
            print(data['full_text'])
            return data
        else:
            print(f"✗ Error: {response.status_code}")
            print(f"Details: {response.text}")
            return None
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Process PDF:  python example.py process <input.pdf> [output.pdf]")
        print("  Extract text: python example.py extract <input.pdf>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "process":
        if len(sys.argv) < 3:
            print("Error: Input PDF required")
            sys.exit(1)
        
        input_pdf = sys.argv[2]
        output_pdf = sys.argv[3] if len(sys.argv) > 3 else f"ocr_{os.path.basename(input_pdf)}"
        
        success = process_pdf(input_pdf, output_pdf)
        sys.exit(0 if success else 1)
    
    elif command == "extract":
        if len(sys.argv) < 3:
            print("Error: Input PDF required")
            sys.exit(1)
        
        input_pdf = sys.argv[2]
        result = extract_text(input_pdf)
        sys.exit(0 if result else 1)
    
    else:
        print(f"Error: Unknown command '{command}'")
        print("Valid commands: process, extract")
        sys.exit(1)


if __name__ == "__main__":
    main()
