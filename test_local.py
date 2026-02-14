#!/usr/bin/env python3
"""
Local test script for PDF checking
Uses PyMuPDF directly instead of browser wrappers
"""
import sys
import os

# Add check_logic to path
sys.path.insert(0, os.path.dirname(__file__))

# Force use of PyMuPDF by blocking the custom wrappers
import sys
class BlockImport:
    def find_module(self, fullname, path=None):
        if 'pdf_wrapper' in fullname and 'check_logic' in fullname:
            raise ImportError(f"Blocked import of {fullname} for local testing")
        return None

sys.meta_path.insert(0, BlockImport())

# Mock uploaded file object
class MockUploadedFile:
    def __init__(self, filepath):
        self.filepath = filepath
        self.name = os.path.basename(filepath)
        self._file = None

    def read(self):
        with open(self.filepath, 'rb') as f:
            return f.read()

    def seek(self, pos):
        pass

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_local.py <pdf_file>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Testing with PDF: {pdf_path}")
    print("-" * 60)

    # Import the checker module
    from check_logic import usenix_2026

    # Create mock uploaded file
    uploaded_file = MockUploadedFile(pdf_path)

    # Run the check
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
                    print(f"   Text: {v.get('text', 'N/A')[:100]}")
            else:
                print("\n✓ No violations found!")

    except Exception as e:
        print(f"\nEXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
