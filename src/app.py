from flask import Flask, render_template, request, jsonify
from json import JSONEncoder  # Changed import
from google.generativeai.types import GenerateContentResponse
import logging
from rag import RagManager
from config import Config
import argparse
from markupsafe import Markup
import markdown

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--env-file', type=str, help='Path to environment file')
args = parser.parse_args()

class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, GenerateContentResponse):
            return {
                'text': obj.text,
                'prompt': obj.prompt,
                'candidates': [
                    {'content': c.content, 'finish_reason': c.finish_reason}
                    for c in obj.candidates
                ]
            }
        return super().default(obj)

class GenerateContentResponseConverter:
    @staticmethod
    def to_dict(response):
        # If it's not a GenerateContentResponse, just return it as-is
        if not isinstance(response, GenerateContentResponse):
            return response
        
        # Extract candidates
        candidates_list = []
        if hasattr(response, "candidates"):
            for candidate in response.candidates:
                text = ""
                if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    if candidate.content.parts:
                        text = candidate.content.parts[0].text
                candidates_list.append({
                    'content': text,
                    'finish_reason': candidate.finish_reason,
                    'avg_logprobs': candidate.avg_logprobs
                })

        # Extract usage metadata (if present)
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

app = Flask(__name__)
app.json_encoder = CustomJSONEncoder
config = Config(env_file=args.env_file)

@app.route('/', methods=['GET', 'POST'])
def index():
    results = None
    if request.method == 'POST':
        query = request.form['query']
        log_level = request.form.get('log_level', 'INFO')
        ai_system = request.form.get('ai_system', 'gemini')

        # Configure logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), "INFO"),
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()]
        )

        rag_manager = RagManager(config=config, print_results=True, ai_system=ai_system)
        results = rag_manager.query(query)

    return render_template('index.html', results=results)

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
    app.run(debug=True)