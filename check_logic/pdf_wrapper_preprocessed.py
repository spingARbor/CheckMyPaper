"""
PDF wrapper that reads from preprocessed data in window.preprocessedPDFs
This avoids the Worker communication issue by having the main thread
preprocess the PDF when it's uploaded.
"""
import js

# Storage for preprocessed PDF data received from main thread
_worker_pdf_storage = {}

# Message handler to receive preprocessed data from main thread
def _handle_preprocessed_data(event):
    """Handle PREPROCESSED_PDF_DATA messages from main thread"""
    try:
        data = event.data
        if hasattr(data, 'to_py'):
            data = data.to_py()

        if isinstance(data, dict) and data.get('type') == 'PREPROCESSED_PDF_DATA':
            filename = data.get('filename')
            pdf_data = data.get('data')
            if filename and pdf_data:
                _worker_pdf_storage[filename] = pdf_data
                print(f"Received preprocessed PDF data for: {filename}")
    except Exception as e:
        print(f"Error handling preprocessed data: {e}")

# Register message handler
try:
    js.self.addEventListener('message', _handle_preprocessed_data)
    print("Registered preprocessed data message handler")
except Exception as e:
    print(f"Failed to register message handler: {e}")

# Check if we can access the required JavaScript objects during import
# If not, raise ImportError so the code falls back to async wrapper
_preprocessed_pdfs = None
try:
    # Try to access preprocessedPDFs from various global scopes
    if hasattr(js, 'globalThis') and hasattr(js.globalThis, 'preprocessedPDFs'):
        _preprocessed_pdfs = js.globalThis.preprocessedPDFs
    elif hasattr(js, 'window') and hasattr(js.window, 'preprocessedPDFs'):
        _preprocessed_pdfs = js.window.preprocessedPDFs
    elif hasattr(js, 'self') and hasattr(js.self, 'preprocessedPDFs'):
        _preprocessed_pdfs = js.self.preprocessedPDFs
    else:
        # Try using eval as last resort
        try:
            _preprocessed_pdfs = js.eval('typeof window !== "undefined" ? window.preprocessedPDFs : (typeof self !== "undefined" ? self.preprocessedPDFs : undefined)')
            if _preprocessed_pdfs is None or str(_preprocessed_pdfs) == 'undefined':
                _preprocessed_pdfs = None
        except:
            pass

    # If we can't access window.preprocessedPDFs, we'll use worker storage instead
    # Don't raise ImportError - we can still work with data sent via postMessage
    if _preprocessed_pdfs is None:
        print("preprocessedPDFs not accessible, will use worker storage")
except Exception as e:
    print(f"Note: {e}")


class Rect:
    """Simple rectangle class"""
    def __init__(self, x0, y0, x1, y1):
        self.x0 = float(x0)
        self.y0 = float(y0)
        self.x1 = float(x1)
        self.y1 = float(y1)

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0


class Pixmap:
    """Pixmap class for pixel data"""
    def __init__(self, width, height, pixels):
        self.width = int(width)
        self.height = int(height)
        self.samples = bytes(pixels)


class Page:
    """Page wrapper"""
    def __init__(self, doc, page_num, page_data):
        self.doc = doc
        self.page_num = page_num
        self._page_data = page_data
        self._rect = None

    @property
    def rect(self):
        if self._rect is None:
            w = float(self._page_data['width'])
            h = float(self._page_data['height'])
            self._rect = Rect(0, 0, w, h)
        return self._rect

    def get_text(self, mode="dict"):
        """Extract text content from page"""
        if mode != "dict":
            raise NotImplementedError(f"Mode '{mode}' not supported")

        blocks = []
        for block_data in self._page_data['blocks']:
            block = {
                'bbox': tuple(block_data['bbox']),
                'lines': []
            }

            for line_items in block_data['lines']:
                line = {
                    'bbox': self._calculate_line_bbox(line_items),
                    'spans': []
                }

                for item in line_items:
                    span = {
                        'text': item['text'],
                        'bbox': tuple(item['bbox']),
                        'font': item['font'],
                        'size': item['size']
                    }
                    line['spans'].append(span)

                block['lines'].append(line)

            blocks.append(block)

        return {
            'width': float(self._page_data['width']),
            'height': float(self._page_data['height']),
            'blocks': blocks
        }

    def _calculate_line_bbox(self, items):
        """Calculate bounding box for a line of text items"""
        if len(items) == 0:
            return (0.0, 0.0, 0.0, 0.0)

        x0_vals = [item['bbox'][0] for item in items]
        y0_vals = [item['bbox'][1] for item in items]
        x1_vals = [item['bbox'][2] for item in items]
        y1_vals = [item['bbox'][3] for item in items]

        return (min(x0_vals), min(y0_vals), max(x1_vals), max(y1_vals))

    def get_pixmap(self, clip=None, colorspace=None, alpha=False):
        """Get pixel data for a region - NOT IMPLEMENTED in preprocessed mode"""
        # Pixel rendering is not needed for the current checks
        # If needed in the future, we can implement it by calling back to main thread
        raise NotImplementedError("Pixel rendering not implemented in preprocessed mode")


class Document:
    """Document wrapper"""
    def __init__(self, filename, pdf_data):
        self.filename = filename
        self._pdf_data = pdf_data
        self.num_pages = pdf_data['numPages']
        self._pages = []

        # Create page objects
        for page_data in pdf_data['pages']:
            self._pages.append(Page(self, page_data['pageNum'], page_data))

    def __iter__(self):
        return iter(self._pages)

    def __len__(self):
        return self.num_pages


def open(stream=None, filetype=None, filename=None):
    """
    Open a PDF document from preprocessed data

    Args:
        stream: PDF file bytes (used to generate filename if not provided)
        filetype: File type (ignored, always PDF)
        filename: Filename to look up in preprocessedPDFs

    Returns:
        Document object with preprocessed data
    """
    if stream is None:
        raise ValueError("stream parameter is required")

    # If no filename provided, try to generate one from the stream
    if filename is None:
        import hashlib
        # Use first 1000 bytes to generate a hash
        sample = stream[:1000] if len(stream) > 1000 else stream
        filename = hashlib.md5(sample).hexdigest() + ".pdf"

    # Try to get preprocessed data from worker storage first, then window.preprocessedPDFs
    try:
        pdf_data = None

        # Method 1: Check worker storage (data sent via postMessage)
        if filename in _worker_pdf_storage:
            print(f"Using preprocessed data from worker storage: {filename}")
            pdf_data = _worker_pdf_storage[filename]
        # Method 2: Try to access window.preprocessedPDFs
        elif _preprocessed_pdfs is not None:
            preprocessed_pdfs = _preprocessed_pdfs

            # Check if our file has been preprocessed
            if not hasattr(preprocessed_pdfs, filename):
                # Try to find by checking all keys (in case filename doesn't match exactly)
                available_files = []
                try:
                    # Get all keys from the JavaScript object
                    keys = js.Object.keys(preprocessed_pdfs)
                    for i in range(len(keys)):
                        available_files.append(str(keys[i]))

                    if len(available_files) > 0:
                        # Use the first available file
                        filename = available_files[0]
                        print(f"Using preprocessed file: {filename}")
                    else:
                        raise Exception("No preprocessed PDF data found. Please upload a PDF file first.")
                except:
                    raise Exception("No preprocessed PDF data found. Please upload a PDF file first.")

            # Get the preprocessed data
            pdf_data_js = getattr(preprocessed_pdfs, filename)

            # Convert JavaScript object to Python dict
            pdf_data = pdf_data_js.to_py()
        else:
            # Check if we have any files in worker storage
            if _worker_pdf_storage:
                # Use the first available file
                filename = list(_worker_pdf_storage.keys())[0]
                print(f"Using first available file from worker storage: {filename}")
                pdf_data = _worker_pdf_storage[filename]
            else:
                raise Exception("No preprocessed PDF data found. Please upload a PDF file first.")

        if pdf_data:
            return Document(filename, pdf_data)
        else:
            raise Exception("Failed to retrieve PDF data")

    except Exception as e:
        import sys
        print(f"Error accessing preprocessed PDF data: {e}", file=sys.stderr)
        raise Exception(f"Failed to load preprocessed PDF data: {str(e)}")


# Colorspace constants (for compatibility)
csGRAY = "gray"
