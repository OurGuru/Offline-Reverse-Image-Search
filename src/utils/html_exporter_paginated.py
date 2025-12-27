"""
HTML Export functionality with pagination and duplicate grouping.
"""

import base64
import io
import json
import os
from datetime import datetime
from typing import Any

from PIL import Image


class HTMLExporter:
    """HTML exporter with pagination and duplicate grouping."""

    def __init__(self, items_per_page: int = 50):
        """Initialize the HTML exporter."""
        self.max_thumbnail_size = (150, 150)
        self.items_per_page = items_per_page

    def create_thumbnail_base64(
        self, image_path: str, max_size: tuple[int, int] = None
    ) -> str | None:
        """Create a base64 encoded thumbnail from an image file."""
        if max_size is None:
            max_size = self.max_thumbnail_size

        try:
            with Image.open(image_path) as img:
                # Convert RGBA to RGB if necessary
                if img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                    img = background

                # Create thumbnail
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save to bytes
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85, optimize=True)
                buffer.seek(0)

                # Encode to base64
                img_str = base64.b64encode(buffer.read()).decode("utf-8")
                return f"data:image/jpeg;base64,{img_str}"

        except Exception as e:
            print(f"Error creating thumbnail for {image_path}: {str(e)}")
            return None

    def get_file_info(self, file_path: str) -> dict[str, Any]:
        """Get file information including size and modification date."""
        try:
            stat = os.stat(file_path)
            return {
                "size": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "exists": True,
            }
        except:
            return {"size": 0, "size_mb": 0, "modified": "Unknown", "exists": False}

    def group_duplicates(
        self, results: list[str], duplicates_info: dict | None = None
    ) -> tuple[list[dict], dict]:
        """
        Group results by duplicates.
        Returns grouped results and duplicate groups mapping.
        """
        # Create groups based on duplicate info
        seen = set()
        duplicate_groups = {}

        if duplicates_info:
            # Build reverse mapping: hash -> paths
            hash_to_paths = {}
            for path, count in duplicates_info.items():
                if count > 1:
                    # Find all paths with same count (simplified grouping)
                    if count not in hash_to_paths:
                        hash_to_paths[count] = []
                    hash_to_paths[count].append(path)

            # Create proper groups
            group_id = 0
            for paths in hash_to_paths.values():
                if len(paths) > 1:
                    group_id += 1
                    duplicate_groups[group_id] = paths
                    for path in paths:
                        seen.add(path)

        # Process all results
        grouped_results = []
        for result_path in results:
            if result_path not in seen:
                # Unique result
                grouped_results.append({"type": "unique", "path": result_path, "group_id": None})
            else:
                # Part of duplicate group - find which one
                for gid, paths in duplicate_groups.items():
                    if result_path in paths:
                        # Only add first item of each group
                        if not any(r.get("group_id") == gid for r in grouped_results):
                            grouped_results.append(
                                {
                                    "type": "duplicate",
                                    "path": result_path,
                                    "group_id": gid,
                                    "duplicates": paths,
                                }
                            )
                        break

        return grouped_results, duplicate_groups

    def export_search_results_paginated(
        self,
        search_image: str,
        results: list[str],
        output_path: str,
        search_range: int = 6,
        duplicates_info: dict | None = None,
    ) -> bool:
        """Export search results with pagination and duplicate grouping."""
        try:
            # Group duplicates
            grouped_results, duplicate_groups = self.group_duplicates(results, duplicates_info)

            # Prepare search data
            search_data = {
                "image": search_image,
                "thumbnail": self.create_thumbnail_base64(search_image),
                "info": self.get_file_info(search_image),
            }

            # Process grouped results
            results_data = []
            for i, group in enumerate(grouped_results):
                if group["type"] == "unique":
                    # Single result
                    result_info = {
                        "index": i + 1,
                        "type": "unique",
                        "path": group["path"],
                        "filename": os.path.basename(group["path"]),
                        "directory": os.path.dirname(group["path"]),
                        "thumbnail": self.create_thumbnail_base64(group["path"]),
                        "info": self.get_file_info(group["path"]),
                    }
                else:
                    # Duplicate group - show first with indicator
                    result_info = {
                        "index": i + 1,
                        "type": "duplicate_group",
                        "group_id": group["group_id"],
                        "path": group["path"],
                        "filename": os.path.basename(group["path"]),
                        "directory": os.path.dirname(group["path"]),
                        "thumbnail": self.create_thumbnail_base64(group["path"]),
                        "info": self.get_file_info(group["path"]),
                        "duplicates": group["duplicates"],
                        "duplicate_count": len(group["duplicates"]),
                    }

                results_data.append(result_info)

            # Generate paginated HTML
            html_content = self._generate_paginated_html(
                search_data,
                results_data,
                duplicate_groups,
                search_range,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

            # Write to file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            return True

        except Exception as e:
            print(f"Error exporting search results: {str(e)}")
            return False

    def _generate_paginated_html(
        self,
        search_data: dict,
        results_data: list[dict],
        duplicate_groups: dict,
        search_range: int,
        timestamp: str,
    ) -> str:
        """Generate HTML with pagination and duplicate grouping."""

        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Search Results - {timestamp}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .pagination {{
            padding: 20px;
            background: #f8f9fa;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        
        .page-btn {{
            padding: 8px 15px;
            background: white;
            border: 2px solid #667eea;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: 500;
        }}
        
        .page-btn:hover {{
            background: #667eea;
            color: white;
        }}
        
        .page-btn.active {{
            background: #667eea;
            color: white;
        }}
        
        .page-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        
        .page-info {{
            padding: 8px 15px;
            background: #e9ecef;
            border-radius: 5px;
            font-weight: 500;
        }}
        
        .results-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
            min-height: 400px;
        }}
        
        .result-card {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
            cursor: pointer;
            position: relative;
        }}
        
        .result-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }}
        
        .result-card.duplicate-group {{
            border: 3px solid #ffc107;
        }}
        
        .duplicate-indicator {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: #ffc107;
            color: #000;
            padding: 5px 10px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
            z-index: 10;
            cursor: pointer;
        }}
        
        .duplicate-indicator:hover {{
            background: #ffae00;
        }}
        
        .result-thumbnail {{
            width: 100%;
            height: 200px;
            background: #f8f9fa;
            position: relative;
            overflow: hidden;
        }}
        
        .result-thumbnail img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        
        .result-index {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(102, 126, 234, 0.9);
            color: white;
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: bold;
        }}
        
        .result-details {{
            padding: 15px;
        }}
        
        .result-filename {{
            font-weight: 600;
            color: #212529;
            margin-bottom: 8px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        .result-path {{
            font-size: 0.85em;
            color: #6c757d;
            margin-bottom: 5px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        /* Duplicate selection modal */
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }}
        
        .modal.active {{
            display: flex;
        }}
        
        .modal-content {{
            background: white;
            border-radius: 10px;
            max-width: 800px;
            width: 90%;
            max-height: 90%;
            overflow: auto;
            padding: 30px;
        }}
        
        .modal-header {{
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #e9ecef;
        }}
        
        .modal-title {{
            font-size: 1.5em;
            font-weight: 600;
            color: #212529;
        }}
        
        .duplicates-grid {{
            margin-top: 20px;
        }}
        
        .close-modal {{
            position: absolute;
            top: 20px;
            right: 30px;
            color: #999;
            font-size: 30px;
            cursor: pointer;
        }}
        
        .close-modal:hover {{
            color: #333;
        }}
        
        .items-per-page {{
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .items-per-page select {{
            padding: 5px 10px;
            border: 2px solid #dee2e6;
            border-radius: 5px;
            font-size: 14px;
        }}
        
        @media (max-width: 768px) {{
            .results-grid {{
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            }}
            
            .duplicates-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Image Search Results</h1>
            <div class="subtitle">Generated on {timestamp}</div>
        </div>
        
        <div class="search-info" style="padding: 30px; background: #f8f9fa;">
            <h2>Search Summary</h2>
            <p><strong>Total Results:</strong> {total_results}</p>
            <p><strong>Unique Images:</strong> {unique_count}</p>
            <p><strong>Duplicate Groups:</strong> {duplicate_groups_count}</p>
            <p><strong>Search Range:</strong> {search_range}</p>
        </div>
        
        <div class="pagination">
            <button class="page-btn" id="firstPage" onclick="goToPage(1)">First</button>
            <button class="page-btn" id="prevPage" onclick="previousPage()">Previous</button>
            <span class="page-info">Page <span id="currentPage">1</span> of <span id="totalPages">1</span></span>
            <button class="page-btn" id="nextPage" onclick="nextPage()">Next</button>
            <button class="page-btn" id="lastPage" onclick="goToPage(totalPages)">Last</button>
            
            <div class="items-per-page">
                <label>Items per page:</label>
                <select id="itemsPerPage" onchange="changeItemsPerPage()">
                    <option value="20">20</option>
                    <option value="50" selected>50</option>
                    <option value="100">100</option>
                    <option value="200">200</option>
                </select>
            </div>
        </div>
        
        <div class="results-grid" id="resultsGrid">
            <!-- Results will be inserted here by JavaScript -->
        </div>
        
        <div class="pagination">
            <button class="page-btn" onclick="goToPage(1)">First</button>
            <button class="page-btn" onclick="previousPage()">Previous</button>
            <span class="page-info">Page <span id="currentPage2">1</span> of <span id="totalPages2">1</span></span>
            <button class="page-btn" onclick="nextPage()">Next</button>
            <button class="page-btn" onclick="goToPage(totalPages)">Last</button>
        </div>
    </div>
    
    <!-- Duplicate selection modal -->
    <div class="modal" id="duplicateModal">
        <div class="modal-content">
            <span class="close-modal" onclick="closeDuplicateModal()">&times;</span>
            <div class="modal-header">
                <h2 class="modal-title">Duplicate Image Locations</h2>
                <p>This image appears in <span id="duplicateCount">0</span> location(s). Click on any path to copy it:</p>
            </div>
            <div class="duplicates-grid" id="duplicatesGrid">
                <!-- Duplicate options will be inserted here -->
            </div>
        </div>
    </div>
    
    <script>
        // Results data
        const allResults = {results_json};
        const duplicateGroups = {duplicate_groups_json};
        
        // Pagination variables
        let currentPage = 1;
        let itemsPerPage = 50;
        let totalPages = Math.ceil(allResults.length / itemsPerPage);
        
        // Initialize
        document.addEventListener('DOMContentLoaded', function() {{
            updatePagination();
            displayPage(currentPage);
        }});
        
        function displayPage(page) {{
            currentPage = page;
            const grid = document.getElementById('resultsGrid');
            grid.innerHTML = '';
            
            const start = (page - 1) * itemsPerPage;
            const end = Math.min(start + itemsPerPage, allResults.length);
            
            for (let i = start; i < end; i++) {{
                const result = allResults[i];
                const card = createResultCard(result);
                grid.appendChild(card);
            }}
            
            updatePagination();
        }}
        
        function createResultCard(result) {{
            const card = document.createElement('div');
            card.className = 'result-card';
            if (result.type === 'duplicate_group') {{
                card.className += ' duplicate-group';
            }}
            
            let duplicateIndicator = '';
            if (result.type === 'duplicate_group') {{
                duplicateIndicator = `
                    <div class="duplicate-indicator" onclick="showDuplicates(${{result.group_id}}); event.stopPropagation();">
                        ${{result.duplicate_count}} copies
                    </div>
                `;
            }}
            
            card.innerHTML = `
                <div class="result-thumbnail">
                    <span class="result-index">#${{result.index}}</span>
                    ${{duplicateIndicator}}
                    <img src="${{result.thumbnail || ''}}" 
                         alt="${{result.filename}}" 
                         onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"200\"%3E%3Crect width=\"200\" height=\"200\" fill=\"%23ddd\"/%3E%3Ctext x=\"50%25\" y=\"50%25\" text-anchor=\"middle\" dy=\".3em\" fill=\"%23999\"%3ENo Image%3C/text%3E%3C/svg%3E'">
                </div>
                <div class="result-details">
                    <div class="result-filename" title="${{result.filename}}">${{result.filename}}</div>
                    <div class="result-path" title="${{result.directory}}">${{result.directory}}</div>
                    <div style="font-size: 0.85em; color: #6c757d; margin-top: 5px;">
                        ${{result.info.size_mb}} MB
                    </div>
                </div>
            `;
            
            card.onclick = function() {{
                copyPath(result.path);
            }};
            
            return card;
        }}
        
        function showDuplicates(groupId) {{
            const duplicates = [];
            for (const result of allResults) {{
                if (result.group_id === groupId && result.duplicates) {{
                    duplicates.push(...result.duplicates.map(path => ({{
                        path: path,
                        filename: path.split(/[\\\\/]/).pop(),
                        directory: path.substring(0, path.lastIndexOf(/[\\\\/]/.exec(path)?.[0] || '/'))
                    }})));
                    break;
                }}
            }}
            
            if (duplicates.length > 0) {{
                const modal = document.getElementById('duplicateModal');
                const grid = document.getElementById('duplicatesGrid');
                const count = document.getElementById('duplicateCount');
                
                count.textContent = duplicates.length;
                grid.innerHTML = '';
                
                // Create simple clickable paths list without images
                const pathsList = document.createElement('div');
                pathsList.style.maxHeight = '400px';
                pathsList.style.overflowY = 'auto';
                
                duplicates.forEach((dup, index) => {{
                    const pathItem = document.createElement('div');
                    pathItem.style.padding = '12px';
                    pathItem.style.marginBottom = '8px';
                    pathItem.style.backgroundColor = '#f8f9fa';
                    pathItem.style.borderRadius = '6px';
                    pathItem.style.cursor = 'pointer';
                    pathItem.style.border = '2px solid transparent';
                    pathItem.style.transition = 'all 0.2s';
                    
                    pathItem.innerHTML = `
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div style="flex: 1; overflow: hidden;">
                                <div style="font-weight: 600; color: #212529; margin-bottom: 5px; font-size: 1em;">
                                    ${{index + 1}}. ${{dup.filename}}
                                </div>
                                <div style="font-size: 0.9em; color: #6c757d; word-break: break-all; font-family: monospace;">
                                    ${{dup.path}}
                                </div>
                            </div>
                            <div style="margin-left: 15px; color: #667eea; font-size: 0.9em; white-space: nowrap;">
                                📋 Copy
                            </div>
                        </div>
                    `;
                    
                    pathItem.onmouseover = function() {{
                        this.style.backgroundColor = '#e9ecef';
                        this.style.borderColor = '#667eea';
                    }};
                    
                    pathItem.onmouseout = function() {{
                        this.style.backgroundColor = '#f8f9fa';
                        this.style.borderColor = 'transparent';
                    }};
                    
                    pathItem.onclick = function() {{
                        copyPath(dup.path);
                        // Visual feedback
                        const copyIndicator = this.querySelector('div[style*="color: #667eea"]');
                        const originalText = copyIndicator.textContent;
                        copyIndicator.textContent = '✅ Copied!';
                        this.style.backgroundColor = '#d4edda';
                        this.style.borderColor = '#28a745';
                        
                        setTimeout(() => {{
                            copyIndicator.textContent = originalText;
                            this.style.backgroundColor = '#f8f9fa';
                            this.style.borderColor = 'transparent';
                        }}, 1500);
                    }};
                    
                    pathsList.appendChild(pathItem);
                }});
                
                grid.appendChild(pathsList);
                
                modal.classList.add('active');
            }}
        }}
        
        function closeDuplicateModal() {{
            document.getElementById('duplicateModal').classList.remove('active');
        }}
        
        function copyPath(path) {{
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(path).then(() => {{
                    alert('Path copied to clipboard:\\n' + path);
                }});
            }} else {{
                alert('Path: ' + path);
            }}
        }}
        
        function updatePagination() {{
            totalPages = Math.ceil(allResults.length / itemsPerPage);
            
            // Update page info
            document.getElementById('currentPage').textContent = currentPage;
            document.getElementById('totalPages').textContent = totalPages;
            document.getElementById('currentPage2').textContent = currentPage;
            document.getElementById('totalPages2').textContent = totalPages;
            
            // Update button states
            const prevButtons = document.querySelectorAll('#prevPage, #firstPage');
            const nextButtons = document.querySelectorAll('#nextPage, #lastPage');
            
            prevButtons.forEach(btn => {{
                btn.disabled = currentPage === 1;
            }});
            
            nextButtons.forEach(btn => {{
                btn.disabled = currentPage === totalPages;
            }});
        }}
        
        function goToPage(page) {{
            if (page >= 1 && page <= totalPages) {{
                displayPage(page);
            }}
        }}
        
        function previousPage() {{
            if (currentPage > 1) {{
                displayPage(currentPage - 1);
            }}
        }}
        
        function nextPage() {{
            if (currentPage < totalPages) {{
                displayPage(currentPage + 1);
            }}
        }}
        
        function changeItemsPerPage() {{
            itemsPerPage = parseInt(document.getElementById('itemsPerPage').value);
            currentPage = 1;
            updatePagination();
            displayPage(currentPage);
        }}
        
        // Close modal on outside click
        window.onclick = function(event) {{
            const modal = document.getElementById('duplicateModal');
            if (event.target === modal) {{
                closeDuplicateModal();
            }}
        }}
    </script>
</body>
</html>"""

        # Calculate statistics
        unique_count = len([r for r in results_data if r["type"] == "unique"])
        duplicate_groups_count = len(duplicate_groups)

        # Format the template
        html_content = html_template.format(
            timestamp=timestamp,
            total_results=len(results_data),
            unique_count=unique_count,
            duplicate_groups_count=duplicate_groups_count,
            search_range=search_range,
            results_json=json.dumps(results_data),
            duplicate_groups_json=json.dumps(duplicate_groups),
        )

        return html_content
