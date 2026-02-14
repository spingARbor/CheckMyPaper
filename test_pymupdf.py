#!/usr/bin/env python3
"""
Direct test with PyMuPDF - bypasses all wrapper imports
"""
import sys
import os

# Temporarily replace the fitz import in usenix_2026
import pymupdf as fitz_real

# Mock the check_logic.pdf_wrapper modules to force fallback to pymupdf
sys.modules['check_logic.pdf_wrapper_preprocessed'] = None
sys.modules['check_logic.pdf_wrapper_sync'] = None
sys.modules['check_logic.pdf_wrapper_async'] = None
sys.modules['check_logic.pdf_wrapper_component'] = None
sys.modules['check_logic.pdf_wrapper'] = None

# Now we can import and it will use pymupdf
sys.path.insert(0, os.path.dirname(__file__))

class MockUploadedFile:
    def __init__(self, filepath):
        self.filepath = filepath
        self.name = os.path.basename(filepath)

    def read(self):
        with open(self.filepath, 'rb') as f:
            return f.read()

    def seek(self, pos):
        pass

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_pymupdf.py <pdf_file>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Testing with PDF: {pdf_path}")
    print(f"Using PyMuPDF version: {fitz_real.__version__}")
    print("-" * 60)

    # Import after mocking
    from check_logic import usenix_2026

    uploaded_file = MockUploadedFile(pdf_path)

    try:
        results = usenix_2026.run_check(uploaded_file)

        print("\n" + "=" * 60)
        print("CHECK RESULTS")
        print("=" * 60)

        if results["status"] == "error":
            print(f"\nERROR: {results['message']}")
            if "traceback" in results:
                print("\nTraceback:")
                print(results["traceback"])
        else:
            violations = results["violations"]
            print(f"\nTotal violations found: {len(violations)}")

            if violations:
                print("\nViolations:")
                for i, v in enumerate(violations, 1):
                    print(f"\n{i}. Page {v.get('page', '?')}: {v['type']}")
                    print(f"   BBox: {v.get('bbox', 'N/A')}")
                    text = v.get('text', 'N/A')
                    if len(text) > 100:
                        text = text[:100] + "..."
                    print(f"   Text: {text}")
            else:
                print("\n✓ No violations found!")

    except Exception as e:
        print(f"\nEXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
