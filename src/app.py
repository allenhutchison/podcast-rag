from flask import Flask, render_template, request, jsonify
from flask_cors import CORS  # Add this import
from markupsafe import Markup
import markdown
import logging
from rag import RagManager
from config import Config
import argparse
from google.generativeai.types import GenerateContentResponse

parser = argparse.ArgumentParser()
parser.add_argument('--env-file', type=str, help='Path to environment file')
args = parser.parse_args()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
config = Config(env_file=args.env_file)

class GenerateContentResponseConverter:
    @staticmethod
    def to_dict(response):
        if not isinstance(response, GenerateContentResponse):
            return response

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
                    'finish_reason': candidate.finish_reason,
                    'avg_logprobs': candidate.avg_logprobs
                })

        usage_meta = {}
        if hasattr(response, "usage_metadata"):
            usage_meta = {
                'prompt_token_count': response.usage_metadata.prompt_token_count,
                'candidates_token_count': response.usage_metadata.candidates_token_count,
                'total_token_count': response.usage_metadata.total_token_count
            }

        return {
            'done': getattr(response, 'done', None),
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
        ai_system = request.form.get('ai_system', 'gemini')

        logging.basicConfig(
            level=getattr(logging, log_level.upper(), "INFO"),
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()]
        )

        rag_manager = RagManager(config=config, print_results=True, ai_system=ai_system)

        # 1) Get LLM result
        raw_result = rag_manager.query(query)
        results = GenerateContentResponseConverter.to_dict(raw_result)

        # 2) Convert first candidate’s content to HTML
        if results and 'candidates' in results and results['candidates']:
            text_md = results['candidates'][0].get('content', '')
            html_content = markdown.markdown(text_md)
            styled_text = Markup(html_content)

        # 3) Get vector DB snippets (example method call)
        db_snippets = rag_manager.search_snippets(query)
        # db_snippets should be a list of dicts like:
        # [{'text': 'Snippet text...', 'source': 'http://example.com'}, ...]

        # 4) Build a footnote-like structure
        for i, snippet in enumerate(db_snippets, start=1):
            footnote_link = f"[{i}]"
            # We'll keep the snippet text in plain Markdown and link to snippet['source']
            db_results.append({
                'footnote': footnote_link,
                'text': snippet['text'],
                'source': snippet.get('source', '#')
            })

    return render_template('index.html', results=results, styled_text=styled_text, db_results=db_results)

@app.route('/search', methods=['POST'])
def search():
    try:
        data = request.get_json() if request.is_json else request.form
        query = data.get('query')
        log_level = data.get('log_level', 'INFO')
        ai_system = data.get('ai_system', 'gemini')

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Configure logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), "INFO"),
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()]
        )

        rag_manager = RagManager(config=config, print_results=True, ai_system=ai_system)
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)