import logging
import os
import textwrap
from string import Template

from src.config import Config


class PromptManager:
    def __init__(self, config: Config, print_results=True):
        # Directory containing .txt prompt files
        self.prompts_dir = config.PROMPTS_DIR
        self.print_results = print_results
        self._templates = {}
        self._load_prompts()

    def _load_prompts(self):
        """
        Loads all .txt files in self.prompts_dir as Template objects
        and stores them in self._templates keyed by filename (minus extension).
        """
        if not os.path.isdir(self.prompts_dir):
            logging.warning(f"Prompts directory not found: {self.prompts_dir}")
            return

        for filename in os.listdir(self.prompts_dir):
            if filename.endswith(".txt"):
                filepath = os.path.join(self.prompts_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = textwrap.dedent(f.read())
                template_key = os.path.splitext(filename)[0]
                self._templates[template_key] = Template(content)
                logging.info(f"Loaded prompt template: {filename}")

    def build_prompt(self, prompt_name, **kwargs):
        """
        Substitutes the given kwargs into the specified prompt template.
        """
        if prompt_name not in self._templates:
            logging.error(f"No template named '{prompt_name}' found.")
            return ""

        template = self._templates[prompt_name]
        prompt = template.substitute(**kwargs)
        if self.print_results:
            logging.info(f"Built prompt '{prompt_name}': {prompt}")
        return prompt