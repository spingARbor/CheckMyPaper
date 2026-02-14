"""
Async PDF wrapper using postMessage for Worker-to-main-thread communication
This is the correct approach for Stlite/Pyodide in a Worker.
"""
import js
from pyodide.ffi import to_js
import asyncio
import uuid


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

    async def get_pixmap(self, clip=None, colorspace=None, alpha=False):
        """Get pixel data for a region (async)"""
        if clip is None:
            clip = self.rect

        # Create a future to wait for the response
        request_id = str(uuid.uuid4())
        future = asyncio.Future()

        # Store the future so the message handler can resolve it
        if not hasattr(js, '_pdf_futures'):
            js._pdf_futures = {}
        js._pdf_futures[request_id] = future

        # Send request to main thread
        js.self.postMessage(to_js({
            'type': 'GET_PIXEL_DATA',
            'requestId': request_id,
            'filename': self.doc.filename,
            'pageNum': self.page_num,
            'x': clip.x0,
            'y': clip.y0,
            'width': clip.width,
            'height': clip.height
        }))

        # Wait for response
        response = await future

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


async def open(stream=None, filetype=None, filename=None):
    """
    Open a PDF document from bytes (async)

    The PDF is processed in the main thread and the data is retrieved asynchronously.
    """
    if stream is None:
        raise ValueError("stream parameter is required")

    if filename is None:
        # Generate a filename based on the stream content
        import hashlib
        filename = hashlib.md5(stream[:1000] if len(stream) > 1000 else stream).hexdigest() + ".pdf"

    # Create a future to wait for the response
    request_id = str(uuid.uuid4())
    future = asyncio.Future()

    # Store the future so the message handler can resolve it
    if not hasattr(js, '_pdf_futures'):
        js._pdf_futures = {}
    js._pdf_futures[request_id] = future

    # Send PDF data to main thread for processing
    js.self.postMessage(to_js({
        'type': 'PROCESS_PDF',
        'requestId': request_id,
        'filename': filename,
        'pdfData': list(stream)
    }))

    # Wait for response
    response = await future

    if response.get('success'):
        pdf_data = response['data']
        return Document(filename, pdf_data)
    else:
        raise Exception(f"Failed to process PDF: {response.get('error', 'Unknown error')}")


# Message handler for responses from main thread
def _handle_message(event):
    """Handle messages from main thread"""
    try:
        data = event.data
        if hasattr(data, 'to_py'):
            data = data.to_py()

        if isinstance(data, dict) and 'requestId' in data:
            request_id = data['requestId']
            if hasattr(js, '_pdf_futures') and request_id in js._pdf_futures:
                future = js._pdf_futures.pop(request_id)
                future.set_result(data)
    except Exception as e:
        print(f"Error handling message: {e}")


# Register message handler
try:
    js.self.addEventListener('message', _handle_message)
except Exception as e:
    print(f"Failed to register message handler: {e}")


# Colorspace constants (for compatibility)
csGRAY = "gray"
