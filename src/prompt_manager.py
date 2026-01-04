import logging
import os
import re
import textwrap
from string import Template

from src.config import Config

# Regex pattern to extract placeholder names from Template strings
# Matches $identifier or ${identifier} syntax
_PLACEHOLDER_PATTERN = re.compile(r'\$\{(\w+)\}|\$(\w+)')


def _extract_placeholders(template_string: str) -> set[str]:
    """
    Extract all placeholder names from a Template string.

    Handles both $identifier and ${identifier} syntax.
    Escaped $$ sequences are not matched by the pattern.

    Args:
        template_string: The template content

    Returns:
        Set of placeholder names found in the template
    """
    placeholders = set()
    for match in _PLACEHOLDER_PATTERN.finditer(template_string):
        # Group 1 is ${identifier}, Group 2 is $identifier
        name = match.group(1) or match.group(2)
        if name:
            placeholders.add(name)
    return placeholders


class PromptManager:
    def __init__(self, config: Config, print_results: bool = True) -> None:
        # Directory containing .txt prompt files
        self.prompts_dir = config.PROMPTS_DIR
        self.print_results = print_results
        self._templates = {}
        self._template_placeholders = {}  # Cache of required placeholders per template
        self._load_prompts()

    def _load_prompts(self):
        """
        Loads all .txt files in self.prompts_dir as Template objects
        and stores them in self._templates keyed by filename (minus extension).
        Also extracts and caches required placeholders for each template.
        """
        if not os.path.isdir(self.prompts_dir):
            logging.warning(f"Prompts directory not found: {self.prompts_dir}")
            return

        for filename in os.listdir(self.prompts_dir):
            if filename.endswith(".txt"):
                filepath = os.path.join(self.prompts_dir, filename)
                with open(filepath, encoding="utf-8") as f:
                    content = textwrap.dedent(f.read())
                template_key = os.path.splitext(filename)[0]
                self._templates[template_key] = Template(content)
                self._template_placeholders[template_key] = _extract_placeholders(content)
                placeholders = self._template_placeholders[template_key]
                placeholder_info = f" with placeholders: {sorted(placeholders)}" if placeholders else ""
                logging.info(f"Loaded prompt template: {filename}{placeholder_info}")

    def build_prompt(self, prompt_name: str, **kwargs) -> str:
        """
        Substitutes the given kwargs into the specified prompt template.

        Validates that all required placeholders are provided before substitution.

        Args:
            prompt_name: Name of the template (without .txt extension)
            **kwargs: Values for template placeholders

        Returns:
            The formatted prompt string

        Raises:
            ValueError: If prompt_name not found or required placeholders are missing
        """
        if prompt_name not in self._templates:
            raise ValueError(f"No template named '{prompt_name}' found in {self.prompts_dir}")

        # Validate that all required placeholders are provided
        required = self._template_placeholders.get(prompt_name, set())
        provided = set(kwargs.keys())
        missing = required - provided

        if missing:
            raise ValueError(
                f"Missing required placeholders for template '{prompt_name}': {sorted(missing)}. "
                f"Required: {sorted(required)}, Provided: {sorted(provided)}"
            )

        template = self._templates[prompt_name]
        prompt = template.substitute(**kwargs)
        if self.print_results:
            logging.info(f"Built prompt '{prompt_name}': {prompt}")
        return prompt
