"""
Python wrapper for PDF.js bridge
Provides a PyMuPDF-like API using PDF.js in the browser
"""
import js
from pyodide.ffi import to_js


class Rect:
    """Simple rectangle class compatible with PyMuPDF's Rect"""
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
    """Page wrapper that uses PDF.js"""
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

        # Convert JavaScript data to Python format
        blocks = []
        js_blocks = self._page_data['blocks']

        for i in range(len(js_blocks)):
            block_data = js_blocks[i]
            bbox_js = block_data['bbox']
            block = {
                'bbox': (float(bbox_js[0]), float(bbox_js[1]), float(bbox_js[2]), float(bbox_js[3])),
                'lines': []
            }

            lines_js = block_data['lines']
            for j in range(len(lines_js)):
                line_items = lines_js[j]
                line = {
                    'bbox': self._calculate_line_bbox(line_items),
                    'spans': []
                }

                for k in range(len(line_items)):
                    item = line_items[k]
                    bbox_js = item['bbox']
                    span = {
                        'text': str(item['text']),
                        'bbox': (float(bbox_js[0]), float(bbox_js[1]), float(bbox_js[2]), float(bbox_js[3])),
                        'font': str(item['font']),
                        'size': float(item['size'])
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

        x0_vals = []
        y0_vals = []
        x1_vals = []
        y1_vals = []

        for i in range(len(items)):
            bbox = items[i]['bbox']
            x0_vals.append(float(bbox[0]))
            y0_vals.append(float(bbox[1]))
            x1_vals.append(float(bbox[2]))
            y1_vals.append(float(bbox[3]))

        return (min(x0_vals), min(y0_vals), max(x1_vals), max(y1_vals))

    async def get_pixmap(self, clip=None, colorspace=None, alpha=False):
        """Get pixel data for a region"""
        if clip is None:
            clip = self.rect

        # Access pdfBridge from window object
        try:
            pdfBridge = js.window.pdfBridge
        except AttributeError:
            pdfBridge = js.pdfBridge

        # Call JavaScript bridge - it returns a Promise
        promise = pdfBridge.getPixelData(
            self.page_num,
            clip.x0, clip.y0,
            clip.width, clip.height
        )

        # Await the promise to get the resolved value
        result = await promise

        pixels_js = result.pixels
        pixels_list = [int(pixels_js[i]) for i in range(len(pixels_js))]

        return Pixmap(
            result.width,
            result.height,
            pixels_list
        )


class Document:
    """Document wrapper that uses PDF.js"""
    def __init__(self, file_bytes):
        self.file_bytes = file_bytes
        self.num_pages = 0
        self._pages = []
        self._pdf_data = None

    async def _load(self):
        """Load PDF using PDF.js bridge"""
        try:
            # Convert bytes to Uint8Array for JavaScript
            uint8_array = to_js(self.file_bytes)

            # Access pdfBridge from window object
            # In Pyodide, js gives access to the JavaScript global scope
            try:
                pdfBridge = js.window.pdfBridge
            except AttributeError:
                try:
                    pdfBridge = js.pdfBridge
                except AttributeError:
                    raise Exception("pdfBridge not found. Please ensure the page has fully loaded.")

            # Call the async JavaScript function - it returns a Promise
            promise = pdfBridge.loadPdfComplete(uint8_array)

            # Await the promise to get the resolved value
            result = await promise

            if not result.success:
                raise Exception(f"Failed to load PDF: {result.error}")

            self._pdf_data = result
            self.num_pages = int(result.numPages)

            # Create page objects
            pages_js = result.pages
            for i in range(len(pages_js)):
                page_data = pages_js[i]
                self._pages.append(Page(self, int(page_data.pageNum), page_data))
        except Exception as e:
            raise Exception(f"Error in Document._load(): {type(e).__name__}: {str(e)}")

    def __iter__(self):
        """Iterate over pages"""
        return iter(self._pages)

    def __len__(self):
        return self.num_pages


async def open(stream=None, filetype=None):
    """Open a PDF document from bytes"""
    if stream is None:
        raise ValueError("stream parameter is required")
    doc = Document(stream)
    await doc._load()
    return doc


# Colorspace constants (for compatibility)
csGRAY = "gray"
