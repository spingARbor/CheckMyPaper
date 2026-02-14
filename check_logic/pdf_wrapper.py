"""
Python wrapper for PDF.js bridge
Provides a PyMuPDF-like API using PDF.js in the browser
"""
import js
from pyodide.ffi import to_js
import asyncio


class Rect:
    """Simple rectangle class compatible with PyMuPDF's Rect"""
    def __init__(self, x0, y0, x1, y1):
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0


class Pixmap:
    """Pixmap class for pixel data"""
    def __init__(self, width, height, pixels):
        self.width = width
        self.height = height
        self.samples = bytes(pixels)


class Page:
    """Page wrapper that uses PDF.js"""
    def __init__(self, doc, page_num):
        self.doc = doc
        self.page_num = page_num
        self._rect = None

    @property
    def rect(self):
        if self._rect is None:
            # Get page dimensions synchronously (cached)
            dims = self.doc._page_dimensions.get(self.page_num)
            if dims:
                self._rect = Rect(0, 0, dims['width'], dims['height'])
        return self._rect

    def get_text(self, mode="dict"):
        """Extract text content from page"""
        if mode != "dict":
            raise NotImplementedError(f"Mode '{mode}' not supported")

        # Get cached text content
        text_data = self.doc._text_content.get(self.page_num, {})

        # Convert to PyMuPDF-like format
        blocks = []
        for block_data in text_data.get('blocks', []):
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
            'width': text_data.get('width', 0),
            'height': text_data.get('height', 0),
            'blocks': blocks
        }

    def _calculate_line_bbox(self, items):
        """Calculate bounding box for a line of text items"""
        if not items:
            return (0, 0, 0, 0)
        x0 = min(item['bbox'][0] for item in items)
        y0 = min(item['bbox'][1] for item in items)
        x1 = max(item['bbox'][2] for item in items)
        y1 = max(item['bbox'][3] for item in items)
        return (x0, y0, x1, y1)

    def get_pixmap(self, clip=None, colorspace=None, alpha=False):
        """Get pixel data for a region"""
        if clip is None:
            clip = self.rect

        # Call JavaScript bridge to get pixel data
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            js.pdfBridge.getPixelData(
                self.page_num,
                clip.x0, clip.y0,
                clip.width, clip.height
            )
        )

        return Pixmap(
            result.width,
            result.height,
            list(result.pixels)
        )


class Document:
    """Document wrapper that uses PDF.js"""
    def __init__(self, file_bytes):
        self.file_bytes = file_bytes
        self.num_pages = 0
        self._pages = []
        self._page_dimensions = {}
        self._text_content = {}
        self._load()

    def _load(self):
        """Load PDF using PDF.js bridge"""
        # Convert bytes to Uint8Array for JavaScript
        uint8_array = to_js(self.file_bytes)

        # Load PDF
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(js.pdfBridge.loadPdf(uint8_array))

        if not result.success:
            raise Exception(f"Failed to load PDF: {result.error}")

        self.num_pages = result.numPages

        # Pre-load all page dimensions and text content
        for page_num in range(1, self.num_pages + 1):
            # Get dimensions
            dims = loop.run_until_complete(
                js.pdfBridge.getPageDimensions(page_num)
            )
            self._page_dimensions[page_num] = {
                'width': dims.width,
                'height': dims.height
            }

            # Get text content
            text_data = loop.run_until_complete(
                js.pdfBridge.getTextContent(page_num)
            )
            self._text_content[page_num] = {
                'width': text_data.width,
                'height': text_data.height,
                'blocks': [dict(b) for b in text_data.blocks]
            }

            # Create page object
            self._pages.append(Page(self, page_num))

    def __iter__(self):
        """Iterate over pages"""
        return iter(self._pages)

    def __len__(self):
        return self.num_pages


def open(stream=None, filetype=None):
    """Open a PDF document from bytes"""
    if stream is None:
        raise ValueError("stream parameter is required")
    return Document(stream)


# Colorspace constants (for compatibility)
csGRAY = "gray"
