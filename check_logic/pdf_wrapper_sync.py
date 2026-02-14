"""
Synchronous PDF wrapper using SharedArrayBuffer for Worker-to-main-thread communication
"""
import js
from pyodide.ffi import to_js
import json
import time


# Global state for synchronous communication
_request_id_counter = 0
_pending_requests = {}


def _make_sync_request(request_type, **kwargs):
    """Make a synchronous request to the main thread"""
    global _request_id_counter
    _request_id_counter += 1
    request_id = _request_id_counter

    # Send request to main thread
    js.self.postMessage(to_js({
        'type': request_type,
        'requestId': request_id,
        **kwargs
    }))

    # Wait for response (polling approach since we can't use Atomics.wait in Pyodide)
    max_wait = 10  # seconds
    start_time = time.time()

    while request_id not in _pending_requests:
        if time.time() - start_time > max_wait:
            raise TimeoutError(f"Request {request_type} timed out")
        # Small sleep to avoid busy waiting
        time.sleep(0.01)

    response = _pending_requests.pop(request_id)
    return response


# Message handler for responses from main thread
def _handle_response(event):
    """Handle responses from main thread"""
    data = event.data.to_py() if hasattr(event.data, 'to_py') else event.data
    if 'requestId' in data:
        _pending_requests[data['requestId']] = data


# Register message handler
try:
    js.self.addEventListener('message', _handle_response)
except:
    pass  # May fail if already registered


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
        """Get pixel data for a region"""
        if clip is None:
            clip = self.rect

        # Make synchronous request to main thread
        response = _make_sync_request(
            'GET_PIXEL_DATA',
            filename=self.doc.filename,
            pageNum=self.page_num,
            x=clip.x0,
            y=clip.y0,
            width=clip.width,
            height=clip.height
        )

        if response.get('success'):
            data = response['data']
            return Pixmap(
                data['width'],
                data['height'],
                data['pixels']
            )
        else:
            raise Exception(f"Failed to render PDF region: {response.get('error', 'Unknown error')}")


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
    Open a PDF document from bytes

    The PDF is processed in the main thread and the data is retrieved synchronously.
    """
    if stream is None:
        raise ValueError("stream parameter is required")

    if filename is None:
        # Generate a filename based on the stream content
        import hashlib
        filename = hashlib.md5(stream[:1000] if len(stream) > 1000 else stream).hexdigest() + ".pdf"

    # Send PDF data to main thread for processing
    response = _make_sync_request(
        'PROCESS_PDF',
        filename=filename,
        pdfData=list(stream)
    )

    if response.get('success'):
        pdf_data = response['data']
        return Document(filename, pdf_data)
    else:
        raise Exception(f"Failed to process PDF: {response.get('error', 'Unknown error')}")


# Colorspace constants (for compatibility)
csGRAY = "gray"
