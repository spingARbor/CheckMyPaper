"""
Streamlit component for communicating with main thread's pdfBridge
"""
import streamlit.components.v1 as components
import json
import uuid


def process_pdf_via_bridge(pdf_bytes):
    """
    Process PDF using the main thread's pdfBridge via iframe communication

    Args:
        pdf_bytes: PDF file as bytes

    Returns:
        dict: PDF data structure compatible with PyMuPDF format
    """
    # Convert bytes to list for JSON serialization
    pdf_data_list = list(pdf_bytes)
    request_id = str(uuid.uuid4())

    # Create HTML component that communicates with parent window
    component_html = f"""
    <div id="status">Processing PDF...</div>
    <script>
        (function() {{
            const requestId = '{request_id}';
            const pdfData = {json.dumps(pdf_data_list)};

            // Send request to parent window
            window.parent.postMessage({{
                type: 'PDF_PROCESS_REQUEST',
                requestId: requestId,
                pdfData: pdfData
            }}, '*');

            // Listen for response
            window.addEventListener('message', function(event) {{
                if (event.data.type === 'PDF_PROCESS_RESPONSE' &&
                    event.data.requestId === requestId) {{

                    const statusDiv = document.getElementById('status');

                    if (event.data.success) {{
                        statusDiv.textContent = 'PDF processed successfully!';
                        statusDiv.style.color = 'green';

                        // Send result back to Streamlit
                        window.parent.postMessage({{
                            type: 'streamlit:setComponentValue',
                            value: event.data.data
                        }}, '*');
                    }} else {{
                        statusDiv.textContent = 'Error: ' + event.data.error;
                        statusDiv.style.color = 'red';

                        window.parent.postMessage({{
                            type: 'streamlit:setComponentValue',
                            value: {{ error: event.data.error }}
                        }}, '*');
                    }}
                }}
            }});
        }})();
    </script>
    """

    # Use Streamlit component to render and get result
    result = components.html(component_html, height=100)
    return result


def render_pdf_region_via_bridge(page_num, x, y, width, height):
    """
    Render a PDF region using the main thread's pdfBridge

    Args:
        page_num: Page number (1-indexed)
        x, y, width, height: Region coordinates

    Returns:
        dict: Pixel data {width, height, pixels}
    """
    request_id = str(uuid.uuid4())

    component_html = f"""
    <div id="status">Rendering PDF region...</div>
    <script>
        (function() {{
            const requestId = '{request_id}';

            window.parent.postMessage({{
                type: 'PDF_RENDER_REQUEST',
                requestId: requestId,
                pageNum: {page_num},
                x: {x},
                y: {y},
                width: {width},
                height: {height}
            }}, '*');

            window.addEventListener('message', function(event) {{
                if (event.data.type === 'PDF_RENDER_RESPONSE' &&
                    event.data.requestId === requestId) {{

                    if (event.data.success) {{
                        window.parent.postMessage({{
                            type: 'streamlit:setComponentValue',
                            value: event.data.data
                        }}, '*');
                    }} else {{
                        window.parent.postMessage({{
                            type: 'streamlit:setComponentValue',
                            value: {{ error: event.data.error }}
                        }}, '*');
                    }}
                }}
            }});
        }})();
    </script>
    """

    result = components.html(component_html, height=50)
    return result
