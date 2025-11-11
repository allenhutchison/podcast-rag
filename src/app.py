import argparse
import logging
import json
import os
from werkzeug.utils import secure_filename

import markdown
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_cors import CORS
from markupsafe import Markup

from src.config import Config
from src.rag import RagManager
from src.db.metadatadb import PodcastDB
from src.util.opml_importer import OPMLImporter

# Get the absolute path to the template and static folders
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
CORS(app)
app.secret_key = os.urandom(24)  # Required for flash messages

# Only parse arguments when running directly
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=str, help='Path to environment file')
    args = parser.parse_args()
    config = Config(env_file=args.env_file)
else:
    config = Config()

# Initialize database
podcast_db = PodcastDB()

class GenerateContentResponseConverter:
    @staticmethod
    def to_dict(response):
        # Handle string responses (from new RAG manager)
        if isinstance(response, str):
            return {
                'done': True,
                'candidates': [{'content': response, 'finish_reason': 'STOP', 'avg_logprobs': None}],
                'usage_metadata': {}
            }

        # Handle structured response objects
        candidates_list = []
        if hasattr(response, "candidates"):
            for candidate in response.candidates:
                text = ""
                if (hasattr(candidate, "content") and
                    hasattr(candidate.content, "parts") and
                    candidate.content.parts):
                    text = candidate.content.parts[0].text
                candidates_list.append({
                    'content': text,
                    'finish_reason': getattr(candidate, 'finish_reason', 'STOP'),
                    'avg_logprobs': getattr(candidate, 'avg_logprobs', None)
                })

        usage_meta = {}
        if hasattr(response, "usage_metadata"):
            usage_meta = {
                'prompt_token_count': response.usage_metadata.prompt_token_count,
                'candidates_token_count': response.usage_metadata.candidates_token_count,
                'total_token_count': response.usage_metadata.total_token_count
            }

        return {
            'done': getattr(response, 'done', True),
            'candidates': candidates_list,
            'usage_metadata': usage_meta,
        }

@app.route('/', methods=['GET', 'POST'])
def index():
    results = None
    styled_text = None
    db_results = []
    if request.method == 'POST':
        query = request.form.get('query', '')
        log_level = request.form.get('log_level', 'INFO')

        logging.basicConfig(
            level=getattr(logging, log_level.upper(), "INFO"),
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()]
        )

        rag_manager = RagManager(config=config, print_results=True)

        # 1) Get LLM result
        raw_result = rag_manager.query(query)
        results = GenerateContentResponseConverter.to_dict(raw_result)

        # 2) Convert first candidate's content to HTML
        if results and 'candidates' in results and results['candidates']:
            text_md = results['candidates'][0].get('content', '')
            html_content = markdown.markdown(text_md)
            styled_text = Markup(html_content)

        # 3) Get File Search citations
        citations = rag_manager.get_citations()
        db_results = []

        # 4) Build citation display from grounding metadata
        for i, citation in enumerate(citations, start=1):
            footnote_link = f"[{i}]"
            file_id = citation.get('file_id', 'Unknown')
            chunk_index = citation.get('chunk_index', 0)
            score = citation.get('score', 0.0)

            # Extract filename from file_id if possible
            # File IDs are typically like "files/abc123"
            filename = file_id.split('/')[-1] if file_id else 'Unknown'

            db_results.append({
                'footnote': footnote_link,
                'text': f"Source file: {filename}, Chunk {chunk_index}",
                'source': '#',
                'source_text': f"File {filename}",
                'metadata': f"Chunk: {chunk_index}<br>Relevance Score: {score:.3f}"
            })

    return render_template('index.html', results=results, styled_text=styled_text, db_results=db_results)

@app.route('/search', methods=['POST'])
def search():
    try:
        data = request.get_json() if request.is_json else request.form
        query = data.get('query')
        log_level = data.get('log_level', 'INFO')

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Configure logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), "INFO"),
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()]
        )

        rag_manager = RagManager(config=config, print_results=True)
        raw_result = rag_manager.query(query)

        json_result = GenerateContentResponseConverter.to_dict(raw_result)
        styled_text = None
        # Convert Markdown to HTML:
        if json_result and 'candidates' in json_result:
            text = json_result['candidates'][0].get('content', '')
            # Convert markdown to HTML
            html_content = markdown.markdown(text)
            styled_text = Markup(html_content)  # Mark it safe for rendering

        return render_template('results.html', results=json_result, styled_text=styled_text)

    except Exception as e:
        logging.error(f"Search error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/podcasts')
def podcasts():
    """Display the podcast management page."""
    all_podcasts = podcast_db.get_all_podcasts()
    return render_template('podcasts.html', podcasts=all_podcasts)

@app.route('/debug-podcasts')
def debug_podcasts():
    """Debugging route to check podcast data."""
    all_podcasts = podcast_db.get_all_podcasts()
    result = []
    for p in all_podcasts:
        result.append({
            'id': p.id,
            'title': p.title,
            'description': p.description,
            'feed_url': p.feed_url
        })
    return jsonify(result)

@app.route('/reset-podcasts')
def reset_podcasts():
    """Reset the podcast database by deleting all entries."""
    from sqlalchemy import delete
    from src.db.metadatadb import Podcast
    
    # Delete all podcasts
    podcast_db.session.execute(delete(Podcast))
    podcast_db.session.commit()
    
    return jsonify({"message": "All podcasts have been deleted"})

@app.route('/import-opml', methods=['POST'])
def import_opml():
    """Handle OPML file import."""
    if 'opml_file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('podcasts'))
    
    file = request.files['opml_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('podcasts'))
    
    if not file.filename.endswith(('.opml', '.xml')):
        flash('Invalid file type. Please upload an OPML or XML file.', 'error')
        return redirect(url_for('podcasts'))
    
    try:
        # Read the OPML content
        opml_content = file.read().decode('utf-8')
        
        # Initialize OPML importer
        importer = OPMLImporter(podcast_db)
        
        # Import podcasts
        imported_count = importer.import_from_string(opml_content)
        
        flash(f'Successfully imported {imported_count} podcasts', 'success')
    except Exception as e:
        flash(f'Error importing OPML file: {str(e)}', 'error')
    
    return redirect(url_for('podcasts'))

@app.route('/delete-podcast', methods=['POST'])
def delete_podcast():
    """Delete a podcast from the database."""
    feed_url = request.form.get('feed_url')
    if not feed_url:
        flash('No feed URL provided', 'error')
        return redirect(url_for('podcasts'))
    
    try:
        if podcast_db.delete_podcast(feed_url):
            flash('Podcast deleted successfully', 'success')
        else:
            flash('Podcast not found', 'error')
    except Exception as e:
        flash(f'Error deleting podcast: {str(e)}', 'error')
    
    return redirect(url_for('podcasts'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)