"""
Simplified PDF wrapper using Streamlit components for bridge communication
"""
from check_logic.pdf_bridge_component import process_pdf_via_bridge, render_pdf_region_via_bridge


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

        # Use component to communicate with main thread
        result = render_pdf_region_via_bridge(
            self.page_num,
            clip.x0, clip.y0,
            clip.width, clip.height
        )

        if result and 'error' not in result:
            return Pixmap(
                result['width'],
                result['height'],
                result['pixels']
            )
        else:
            raise Exception(f"Failed to render PDF region: {result.get('error', 'Unknown error')}")


class Document:
    """Document wrapper"""
    def __init__(self, file_bytes, pdf_data):
        self.file_bytes = file_bytes
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


def open(stream=None, filetype=None):
    """Open a PDF document from bytes using component bridge"""
    if stream is None:
        raise ValueError("stream parameter is required")

    # Use component to process PDF in main thread
    pdf_data = process_pdf_via_bridge(stream)

    if pdf_data and 'error' not in pdf_data:
        if pdf_data['success']:
            return Document(stream, pdf_data)
        else:
            raise Exception(f"Failed to load PDF: {pdf_data.get('error', 'Unknown error')}")
    else:
        raise Exception("Failed to communicate with PDF bridge")


# Colorspace constants (for compatibility)
csGRAY = "gray"
