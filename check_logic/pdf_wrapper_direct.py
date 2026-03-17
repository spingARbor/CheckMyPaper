"""
Direct PDF wrapper: Python calls js.window.pdfBridge directly via Pyodide.

This is the simplest and most reliable approach for Stlite/Pyodide environments.
Instead of relying on postMessage channels or Worker references (which are fragile),
we directly invoke window.pdfBridge.loadPdfComplete() from Python using the js module.

This works because Stlite's Pyodide runtime exposes the main thread's window object
via js.globalThis (or js.window), so we can call JS functions synchronously
by awaiting the returned JS Promise via pyodide.ffi.
"""
import js
from pyodide.ffi import to_js
import sys


def _get_pdf_bridge():
    """Try to locate window.pdfBridge from within the Pyodide Worker context."""
    # Stlite exposes window properties through js.globalThis
    for attr in ('pdfBridge', ):
        if hasattr(js.globalThis, attr):
            return getattr(js.globalThis, attr)
    # Also try direct js attribute
    if hasattr(js, 'pdfBridge'):
        return js.pdfBridge
    # Last resort: eval
    try:
        bridge = js.eval('typeof window !== "undefined" && window.pdfBridge ? window.pdfBridge : null')
        if bridge and str(bridge) not in ('null', 'undefined'):
            return bridge
    except Exception:
        pass
    return None


# Validate bridge is accessible at import time — raise ImportError to trigger fallback
_bridge = _get_pdf_bridge()
if _bridge is None:
    raise ImportError("pdfBridge not accessible from this Pyodide context")


# ---------------------------------------------------------------------------
# Data model — mirrors PyMuPDF API used by usenix_2026.py
# ---------------------------------------------------------------------------

class Rect:
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
    def __init__(self, width, height, pixels):
        self.width = int(width)
        self.height = int(height)
        self.samples = bytes(pixels)


class Page:
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
                    'bbox': _line_bbox(line_items),
                    'spans': []
                }
                for item in line_items:
                    line['spans'].append({
                        'text': item['text'],
                        'bbox': tuple(item['bbox']),
                        'font': item['font'],
                        'size': item['size'],
                    })
                block['lines'].append(line)
            blocks.append(block)

        return {
            'width': float(self._page_data['width']),
            'height': float(self._page_data['height']),
            'blocks': blocks,
        }

    def get_pixmap(self, clip=None, colorspace=None, alpha=False):
        """Render a page region by calling pdfBridge.getPixelData() synchronously.

        We use js.eval with an immediately-invoked async IIFE so we can await
        the Promise and return the result without needing asyncio on the Python side.
        Note: Pyodide supports awaiting JS Promises via `await` in an async Python
        function, but here we use a sync helper so the existing synchronous
        usenix_2026.py code continues to work unchanged.
        """
        if clip is None:
            clip = self.rect

        # Build JS that calls pdfBridge.getPixelData and returns a Promise
        # We resolve it synchronously via Pyodide's Promise bridge
        page_num = self.page_num
        x = float(clip.x0)
        y = float(clip.y0)
        w = float(clip.width)
        h = float(clip.height)

        try:
            promise = _bridge.getPixelData(page_num, x, y, w, h)
            # Pyodide automatically awaits JS Promises when called from async context,
            # but from sync context we need to use js.eval roundtrip or a helper.
            # Use the synchronous Atomics-free approach: run via js.eval promise chain.
            import asyncio

            async def _await_promise():
                return await promise

            loop = _get_or_create_loop()
            result_js = loop.run_until_complete(_await_promise())
            if hasattr(result_js, 'to_py'):
                result = result_js.to_py()
            else:
                result = result_js
            return Pixmap(result['width'], result['height'], result['pixels'])
        except Exception as e:
            raise Exception(f"get_pixmap failed: {e}") from e


class Document:
    def __init__(self, filename, pdf_data):
        self.filename = filename
        self._pdf_data = pdf_data
        self.num_pages = pdf_data['numPages']
        self._pages = [
            Page(self, p['pageNum'], p)
            for p in pdf_data['pages']
        ]

    def __iter__(self):
        return iter(self._pages)

    def __len__(self):
        return self.num_pages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def open(stream=None, filetype=None, filename=None):
    """Open a PDF by calling window.pdfBridge.loadPdfComplete() directly.

    The PDF bytes are passed from Python → JS, processed by PDF.js in the main
    thread, and the structured data is returned synchronously.
    """
    if stream is None:
        raise ValueError("stream parameter is required")

    if filename is None:
        import hashlib
        sample = stream[:1000] if len(stream) > 1000 else stream
        filename = hashlib.md5(sample).hexdigest() + ".pdf"

    print(f"pdf_wrapper_direct: loading '{filename}' via pdfBridge", file=sys.stderr)

    try:
        # Convert bytes → JS Uint8Array
        uint8_array = js.Uint8Array.new(to_js(list(stream)))

        # Call pdfBridge.loadPdfComplete — returns a Promise
        promise = _bridge.loadPdfComplete(uint8_array)

        # Await the Promise synchronously using asyncio
        import asyncio

        async def _await():
            return await promise

        loop = _get_or_create_loop()
        result_js = loop.run_until_complete(_await())

        # Convert JS object → Python dict
        if hasattr(result_js, 'to_py'):
            result = result_js.to_py()
        else:
            result = result_js

        if not result.get('success', False):
            raise Exception(f"pdfBridge.loadPdfComplete failed: {result.get('error', 'unknown error')}")

        print(f"pdf_wrapper_direct: loaded {result['numPages']} pages", file=sys.stderr)
        return Document(filename, result)

    except Exception as e:
        raise Exception(f"pdf_wrapper_direct open() failed: {e}") from e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_bbox(items):
    if not items:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(i['bbox'][0] for i in items),
        min(i['bbox'][1] for i in items),
        max(i['bbox'][2] for i in items),
        max(i['bbox'][3] for i in items),
    )


def _get_or_create_loop():
    """Return the current asyncio event loop, creating one if necessary."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


# Colorspace constants (for compatibility with PyMuPDF API)
csGRAY = "gray"
