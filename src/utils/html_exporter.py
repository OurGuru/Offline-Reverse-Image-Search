"""
HTML Export functionality for Offline Reverse Image Search.
Generates interactive HTML reports with embedded thumbnails and statistics.
"""

import base64
import io
import json
import os
from datetime import datetime
from typing import Any

from PIL import Image


class HTMLExporter:
    """Handles exporting search results and duplicates to interactive HTML reports."""

    def __init__(self):
        """Initialize the HTML exporter."""
        self.max_thumbnail_size = (150, 150)
        self.max_preview_size = (400, 400)

    def create_thumbnail_base64(
        self, image_path: str, max_size: tuple[int, int] = None
    ) -> str | None:
        """
        Create a base64 encoded thumbnail from an image file.

        Args:
            image_path: Path to the image file
            max_size: Maximum thumbnail size (width, height)

        Returns:
            Base64 encoded string of the thumbnail or None if failed
        """
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
        """
        Get file information including size and modification date.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with file information
        """
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

    def export_search_results(
        self,
        search_image: str,
        results: list[str],
        output_path: str,
        search_range: int = 6,
        duplicates_info: dict | None = None,
    ) -> bool:
        """
        Export search results to an interactive HTML file.

        Args:
            search_image: Path to the searched image
            results: List of result image paths
            output_path: Path for the output HTML file
            search_range: Search range used
            duplicates_info: Optional dictionary with duplicate information

        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare data
            search_data = {
                "image": search_image,
                "thumbnail": self.create_thumbnail_base64(search_image),
                "info": self.get_file_info(search_image),
            }

            results_data = []
            for i, result_path in enumerate(results):
                result_info = {
                    "index": i + 1,
                    "path": result_path,
                    "filename": os.path.basename(result_path),
                    "directory": os.path.dirname(result_path),
                    "thumbnail": self.create_thumbnail_base64(result_path),
                    "info": self.get_file_info(result_path),
                }

                # Add duplicate info if available
                if duplicates_info and result_path in duplicates_info:
                    result_info["duplicates"] = duplicates_info[result_path]

                results_data.append(result_info)

            # Generate HTML
            html_content = self._generate_search_html(
                search_data,
                results_data,
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

    def export_duplicates(
        self, duplicates: dict[str, list[str]], output_path: str, include_thumbnails: bool = True
    ) -> bool:
        """
        Export duplicate groups to an interactive HTML file.

        Args:
            duplicates: Dictionary mapping hash to list of duplicate paths
            output_path: Path for the output HTML file
            include_thumbnails: Whether to include thumbnail images

        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare duplicate groups data
            groups_data = []
            total_files = 0
            total_size = 0

            for hash_value, paths in duplicates.items():
                if len(paths) < 2:
                    continue

                group_files = []
                group_size = 0

                for path in paths:
                    file_info = self.get_file_info(path)
                    file_data = {
                        "path": path,
                        "filename": os.path.basename(path),
                        "directory": os.path.dirname(path),
                        "info": file_info,
                    }

                    if include_thumbnails:
                        file_data["thumbnail"] = self.create_thumbnail_base64(path)

                    group_files.append(file_data)
                    group_size += file_info["size"]

                groups_data.append(
                    {
                        "hash": str(hash_value)[:16],  # Truncate for display
                        "count": len(paths),
                        "files": group_files,
                        "total_size": group_size,
                        "total_size_mb": round(group_size / (1024 * 1024), 2),
                        "wasted_size": group_size - (group_size / len(paths)),
                        "wasted_size_mb": round(
                            (group_size - (group_size / len(paths))) / (1024 * 1024), 2
                        ),
                    }
                )

                total_files += len(paths)
                total_size += group_size

            # Sort groups by wasted space
            groups_data.sort(key=lambda x: x["wasted_size"], reverse=True)

            # Calculate statistics
            stats = {
                "total_groups": len(groups_data),
                "total_files": total_files,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_wasted_mb": round(
                    sum(g["wasted_size"] for g in groups_data) / (1024 * 1024), 2
                ),
                "average_duplicates": (
                    round(total_files / len(groups_data), 1) if groups_data else 0
                ),
            }

            # Generate HTML
            html_content = self._generate_duplicates_html(
                groups_data, stats, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), include_thumbnails
            )

            # Write to file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            return True

        except Exception as e:
            print(f"Error exporting duplicates: {str(e)}")
            return False

    def _generate_search_html(
        self, search_data: dict, results_data: list[dict], search_range: int, timestamp: str
    ) -> str:
        """Generate HTML content for search results."""

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
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            opacity: 0.9;
            font-size: 1.1em;
        }}
        
        .search-info {{
            background: #f8f9fa;
            padding: 30px;
            display: flex;
            align-items: center;
            gap: 30px;
            border-bottom: 2px solid #e9ecef;
        }}
        
        .search-thumbnail {{
            width: 200px;
            height: 200px;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            flex-shrink: 0;
        }}
        
        .search-thumbnail img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        
        .search-details {{
            flex: 1;
        }}
        
        .search-details h2 {{
            color: #495057;
            margin-bottom: 15px;
        }}
        
        .detail-row {{
            margin: 8px 0;
            color: #6c757d;
        }}
        
        .detail-row strong {{
            color: #495057;
            display: inline-block;
            width: 120px;
        }}
        
        .stats-panel {{
            background: white;
            padding: 20px 30px;
            border-bottom: 2px solid #e9ecef;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            opacity: 0.9;
            font-size: 0.9em;
        }}
        
        .controls {{
            padding: 20px 30px;
            background: #f8f9fa;
            display: flex;
            gap: 20px;
            align-items: center;
            flex-wrap: wrap;
        }}
        
        .control-group {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .control-group label {{
            font-weight: 500;
            color: #495057;
        }}
        
        input, select {{
            padding: 8px 12px;
            border: 2px solid #dee2e6;
            border-radius: 5px;
            font-size: 14px;
        }}
        
        input:focus, select:focus {{
            outline: none;
            border-color: #667eea;
        }}
        
        .results-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
        }}
        
        .result-card {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
            cursor: pointer;
        }}
        
        .result-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
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
        
        .result-meta {{
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #e9ecef;
            font-size: 0.85em;
            color: #6c757d;
        }}
        
        .duplicate-badge {{
            background: #ffc107;
            color: #000;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.8em;
            font-weight: bold;
        }}
        
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
        
        .modal-content {{
            background: white;
            border-radius: 10px;
            max-width: 90%;
            max-height: 90%;
            overflow: auto;
        }}
        
        .modal-image {{
            max-width: 100%;
            height: auto;
        }}
        
        .close-modal {{
            position: absolute;
            top: 20px;
            right: 30px;
            color: white;
            font-size: 40px;
            cursor: pointer;
            z-index: 1001;
        }}
        
        @media print {{
            body {{
                background: white;
            }}
            
            .controls {{
                display: none;
            }}
            
            .result-card {{
                break-inside: avoid;
            }}
        }}
        
        @media (max-width: 768px) {{
            .search-info {{
                flex-direction: column;
            }}
            
            .results-grid {{
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
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
        
        <div class="search-info">
            <div class="search-thumbnail">
                <img src="{search_thumbnail}" alt="Search Image" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"200\"%3E%3Crect width=\"200\" height=\"200\" fill=\"%23ddd\"/%3E%3Ctext x=\"50%25\" y=\"50%25\" text-anchor=\"middle\" dy=\".3em\" fill=\"%23999\"%3ENo Image%3C/text%3E%3C/svg%3E'">
            </div>
            <div class="search-details">
                <h2>Search Image</h2>
                <div class="detail-row"><strong>File:</strong> {search_filename}</div>
                <div class="detail-row"><strong>Path:</strong> {search_path}</div>
                <div class="detail-row"><strong>Size:</strong> {search_size} MB</div>
                <div class="detail-row"><strong>Modified:</strong> {search_modified}</div>
                <div class="detail-row"><strong>Search Range:</strong> {search_range}</div>
            </div>
        </div>
        
        <div class="stats-panel">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{total_results}</div>
                    <div class="stat-label">Results Found</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{unique_results}</div>
                    <div class="stat-label">Unique Images</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_size} MB</div>
                    <div class="stat-label">Total Size</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{duplicates_count}</div>
                    <div class="stat-label">Duplicates</div>
                </div>
            </div>
        </div>
        
        <div class="controls">
            <div class="control-group">
                <label>Search:</label>
                <input type="text" id="searchInput" placeholder="Filter results..." onkeyup="filterResults()">
            </div>
            <div class="control-group">
                <label>Sort by:</label>
                <select id="sortSelect" onchange="sortResults()">
                    <option value="index">Index</option>
                    <option value="name">Name</option>
                    <option value="size">Size</option>
                    <option value="date">Date Modified</option>
                </select>
            </div>
            <div class="control-group">
                <label>View:</label>
                <select id="viewSelect" onchange="changeView()">
                    <option value="grid">Grid</option>
                    <option value="list">List</option>
                </select>
            </div>
        </div>
        
        <div class="results-grid" id="resultsGrid">
            {results_html}
        </div>
    </div>
    
    <div class="modal" id="imageModal" onclick="closeModal()">
        <span class="close-modal">&times;</span>
        <img class="modal-image" id="modalImage">
    </div>
    
    <script>
        const resultsData = {results_json};
        let currentView = 'grid';
        
        function filterResults() {{
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const cards = document.querySelectorAll('.result-card');
            
            cards.forEach(card => {{
                const filename = card.querySelector('.result-filename').textContent.toLowerCase();
                const path = card.querySelector('.result-path').textContent.toLowerCase();
                
                if (filename.includes(searchTerm) || path.includes(searchTerm)) {{
                    card.style.display = '';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}
        
        function sortResults() {{
            const sortBy = document.getElementById('sortSelect').value;
            const grid = document.getElementById('resultsGrid');
            const cards = Array.from(grid.querySelectorAll('.result-card'));
            
            cards.sort((a, b) => {{
                const aData = resultsData[parseInt(a.dataset.index) - 1];
                const bData = resultsData[parseInt(b.dataset.index) - 1];
                
                switch(sortBy) {{
                    case 'name':
                        return aData.filename.localeCompare(bData.filename);
                    case 'size':
                        return bData.info.size - aData.info.size;
                    case 'date':
                        return new Date(bData.info.modified) - new Date(aData.info.modified);
                    default:
                        return aData.index - bData.index;
                }}
            }});
            
            cards.forEach(card => grid.appendChild(card));
        }}
        
        function changeView() {{
            currentView = document.getElementById('viewSelect').value;
            const grid = document.getElementById('resultsGrid');
            
            if (currentView === 'list') {{
                grid.style.gridTemplateColumns = '1fr';
            }} else {{
                grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(250px, 1fr))';
            }}
        }}
        
        function showImage(imagePath) {{
            // For security reasons, we can't directly open local files
            // But we can show a message with the path
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(imagePath);
                alert('Image path copied to clipboard:\\n' + imagePath);
            }} else {{
                alert('Image path:\\n' + imagePath);
            }}
        }}
        
        function closeModal() {{
            document.getElementById('imageModal').style.display = 'none';
        }}
        
        // Copy path on click
        document.querySelectorAll('.result-card').forEach(card => {{
            card.addEventListener('click', function() {{
                const path = this.dataset.path;
                showImage(path);
            }});
        }});
    </script>
</body>
</html>"""

        # Prepare search image data
        search_filename = os.path.basename(search_data["image"])
        search_thumbnail = search_data["thumbnail"] or ""

        # Prepare results HTML
        results_html = []
        unique_paths = set()
        duplicates_count = 0
        total_size = search_data["info"]["size_mb"]

        for result in results_data:
            unique_paths.add(result["path"])
            total_size += result["info"]["size_mb"]

            duplicate_badge = ""
            if "duplicates" in result and result["duplicates"] > 1:
                duplicate_badge = (
                    f'<span class="duplicate-badge">{result["duplicates"]} copies</span>'
                )
                duplicates_count += 1

            result_html = f"""
            <div class="result-card" data-index="{result['index']}" data-path="{result['path']}">
                <div class="result-thumbnail">
                    <span class="result-index">#{result['index']}</span>
                    <img src="{result['thumbnail'] or ''}" alt="{result['filename']}" 
                         onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"200\"%3E%3Crect width=\"200\" height=\"200\" fill=\"%23ddd\"/%3E%3Ctext x=\"50%25\" y=\"50%25\" text-anchor=\"middle\" dy=\".3em\" fill=\"%23999\"%3ENo Image%3C/text%3E%3C/svg%3E'">
                </div>
                <div class="result-details">
                    <div class="result-filename" title="{result['filename']}">{result['filename']}</div>
                    <div class="result-path" title="{result['directory']}">{result['directory']}</div>
                    <div class="result-meta">
                        <span>{result['info']['size_mb']} MB</span>
                        {duplicate_badge}
                    </div>
                </div>
            </div>"""
            results_html.append(result_html)

        # Format the template
        html_content = html_template.format(
            timestamp=timestamp,
            search_thumbnail=search_thumbnail,
            search_filename=search_filename,
            search_path=search_data["image"],
            search_size=search_data["info"]["size_mb"],
            search_modified=search_data["info"]["modified"],
            search_range=search_range,
            total_results=len(results_data),
            unique_results=len(unique_paths),
            total_size=round(total_size, 2),
            duplicates_count=duplicates_count,
            results_html="".join(results_html),
            results_json=json.dumps(results_data),
        )

        return html_content

    def _generate_duplicates_html(
        self, groups_data: list[dict], stats: dict, timestamp: str, include_thumbnails: bool
    ) -> str:
        """Generate HTML content for duplicate groups."""

        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Duplicate Images Report - {timestamp}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
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
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .stats-panel {{
            background: white;
            padding: 30px;
            border-bottom: 2px solid #e9ecef;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .controls {{
            padding: 20px 30px;
            background: #f8f9fa;
            display: flex;
            gap: 20px;
            align-items: center;
        }}
        
        .duplicate-groups {{
            padding: 30px;
        }}
        
        .duplicate-group {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 2px solid transparent;
            transition: border-color 0.3s;
        }}
        
        .duplicate-group:hover {{
            border-color: #f093fb;
        }}
        
        .group-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 2px solid #dee2e6;
        }}
        
        .group-title {{
            font-size: 1.2em;
            font-weight: 600;
            color: #212529;
        }}
        
        .group-stats {{
            display: flex;
            gap: 20px;
        }}
        
        .group-stat {{
            text-align: center;
        }}
        
        .group-stat-value {{
            font-weight: bold;
            color: #f5576c;
            font-size: 1.2em;
        }}
        
        .group-stat-label {{
            font-size: 0.85em;
            color: #6c757d;
        }}
        
        .files-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 15px;
        }}
        
        .file-card {{
            background: white;
            border-radius: 8px;
            padding: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            cursor: pointer;
            transition: transform 0.3s;
        }}
        
        .file-card:hover {{
            transform: scale(1.05);
        }}
        
        .file-thumbnail {{
            width: 100%;
            height: 120px;
            background: #e9ecef;
            border-radius: 5px;
            margin-bottom: 10px;
            overflow: hidden;
        }}
        
        .file-thumbnail img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        
        .file-name {{
            font-size: 0.85em;
            font-weight: 500;
            margin-bottom: 5px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        .file-size {{
            font-size: 0.75em;
            color: #6c757d;
        }}
        
        .warning-badge {{
            background: #ffc107;
            color: #000;
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: bold;
        }}
        
        @media print {{
            body {{
                background: white;
            }}
            
            .controls {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🗂️ Duplicate Images Report</h1>
            <div class="subtitle">Generated on {timestamp}</div>
        </div>
        
        <div class="stats-panel">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{total_groups}</div>
                    <div class="stat-label">Duplicate Groups</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_files}</div>
                    <div class="stat-label">Total Files</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_size} MB</div>
                    <div class="stat-label">Total Size</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{wasted_space} MB</div>
                    <div class="stat-label">Wasted Space</div>
                </div>
            </div>
        </div>
        
        <div class="controls">
            <input type="text" id="searchInput" placeholder="Search files..." onkeyup="filterGroups()">
            <select id="sortSelect" onchange="sortGroups()">
                <option value="wasted">Sort by Wasted Space</option>
                <option value="count">Sort by File Count</option>
                <option value="size">Sort by Total Size</option>
            </select>
        </div>
        
        <div class="duplicate-groups" id="duplicateGroups">
            {groups_html}
        </div>
    </div>
    
    <script>
        const groupsData = {groups_json};
        
        function filterGroups() {{
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const groups = document.querySelectorAll('.duplicate-group');
            
            groups.forEach(group => {{
                const text = group.textContent.toLowerCase();
                group.style.display = text.includes(searchTerm) ? '' : 'none';
            }});
        }}
        
        function sortGroups() {{
            const sortBy = document.getElementById('sortSelect').value;
            const container = document.getElementById('duplicateGroups');
            const groups = Array.from(container.querySelectorAll('.duplicate-group'));
            
            groups.sort((a, b) => {{
                const aData = groupsData[parseInt(a.dataset.index)];
                const bData = groupsData[parseInt(b.dataset.index)];
                
                switch(sortBy) {{
                    case 'count':
                        return bData.count - aData.count;
                    case 'size':
                        return bData.total_size - aData.total_size;
                    default:
                        return bData.wasted_size - aData.wasted_size;
                }}
            }});
            
            groups.forEach(group => container.appendChild(group));
        }}
        
        function copyPath(path) {{
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(path);
                alert('Path copied to clipboard');
            }}
        }}
    </script>
</body>
</html>"""

        # Generate groups HTML
        groups_html = []
        for i, group in enumerate(groups_data):
            files_html = []

            for file_data in group["files"]:
                if include_thumbnails and file_data.get("thumbnail"):
                    thumbnail_html = (
                        f'<img src="{file_data["thumbnail"]}" alt="{file_data["filename"]}">'
                    )
                else:
                    thumbnail_html = '<div style="padding: 40px 0; text-align: center; color: #999;">No thumbnail</div>'

                file_html = f"""
                <div class="file-card" onclick="copyPath('{file_data['path'].replace("'", "\\'")}')"">
                    <div class="file-thumbnail">{thumbnail_html}</div>
                    <div class="file-name" title="{file_data['filename']}">{file_data['filename']}</div>
                    <div class="file-size">{file_data['info']['size_mb']} MB</div>
                </div>"""
                files_html.append(file_html)

            group_html = f"""
            <div class="duplicate-group" data-index="{i}">
                <div class="group-header">
                    <div class="group-title">Duplicate Group #{i + 1}</div>
                    <div class="group-stats">
                        <div class="group-stat">
                            <div class="group-stat-value">{group['count']}</div>
                            <div class="group-stat-label">Files</div>
                        </div>
                        <div class="group-stat">
                            <div class="group-stat-value">{group['total_size_mb']}</div>
                            <div class="group-stat-label">Total MB</div>
                        </div>
                        <div class="group-stat">
                            <div class="group-stat-value warning-badge">{group['wasted_size_mb']} MB</div>
                            <div class="group-stat-label">Wasted</div>
                        </div>
                    </div>
                </div>
                <div class="files-grid">
                    {''.join(files_html)}
                </div>
            </div>"""
            groups_html.append(group_html)

        # Format the template
        html_content = html_template.format(
            timestamp=timestamp,
            total_groups=stats["total_groups"],
            total_files=stats["total_files"],
            total_size=stats["total_size_mb"],
            wasted_space=stats["total_wasted_mb"],
            groups_html="".join(groups_html),
            groups_json=json.dumps(groups_data),
        )

        return html_content

    def _generate_html_header(self, title: str) -> str:
        """Generate HTML header with title and meta tags."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>"""

    def _generate_styles(self) -> str:
        """Generate CSS styles for the HTML export."""
        return """
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .results-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
        }
        
        .result-card {
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
            cursor: pointer;
        }
        
        .result-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }
    </style>"""

    def _generate_javascript(self) -> str:
        """Generate JavaScript for interactive features."""
        return """
    <script>
        function filterResults() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const cards = document.querySelectorAll('.result-card');
            
            cards.forEach(card => {
                const filename = card.querySelector('.result-filename').textContent.toLowerCase();
                const path = card.querySelector('.result-path').textContent.toLowerCase();
                
                if (filename.includes(searchTerm) || path.includes(searchTerm)) {
                    card.style.display = '';
                } else {
                    card.style.display = 'none';
                }
            });
        }
        
        function copyPath(path) {
            if (navigator.clipboard) {
                navigator.clipboard.writeText(path);
                alert('Path copied to clipboard');
            }
        }
    </script>"""

    def _create_base64_thumbnail(self, image_path: str) -> str | None:
        """Create a base64 encoded thumbnail (wrapper for create_thumbnail_base64)."""
        return self.create_thumbnail_base64(image_path)

    def _get_current_timestamp(self) -> str:
        """Get current timestamp string."""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
