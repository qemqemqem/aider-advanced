import json
import os
import re
from pathlib import Path


class AdvisorManager:
    """Manages advisor personas for providing specialized advice."""

    def __init__(self, io, coder):
        """Initialize the advisor manager.
        
        Args:
            io: The input/output interface
            coder: The coder instance
        """
        self.io = io
        self.coder = coder

    def identify_persona(self, question):
        """Identify which advisor persona should answer the question.
        
        Args:
            question: The user's question
            
        Returns:
            A tuple of (persona_type, existing_file, suggested_file)
        """
        self.io.tool_output("Analyzing your question to find the right advisor persona...")
        
        # Create a prompt to ask the LLM to identify or suggest a persona
        prompt = f"""
I need to identify which advisor persona would be best suited to answer this question:

"{question}"

Please analyze the repository structure and suggest either:
1. An existing file in the repository that contains a suitable advisor persona, or
2. A new file path and name for creating a persona that would be appropriate for this question.

Your response should be in JSON format:
{{
  "thinking": "string" // Briefly consider what typ of advisor is appropriate, and then consider files in the repo that might contain a suitable persona
  "persona_type": "string", // A short name for the type of advisor (e.g., "legal", "security", "performance")
  "suggested_file": "string or null", // Full path to existing file if found, or a suggested file if none already exists
}}

Only return valid JSON that can be parsed. Include new lines and tabs so it will be pretty to a human, but still parseable. Do not include any other text in your response.
"""

        # # Add repository map to the prompt if available
        # if repo_map:
        #     prompt += f"\n\nHere is the repository structure to help you understand the codebase:\n\n{repo_map}"

        # Import this here to avoid circular imports
        from aider.coders.base_coder import Coder

        persona_coder = Coder.create(
            io=self.io,
            from_coder=self.coder,
            main_model=self.coder.main_model.weak_model,  # Use the weak model instead of the main model
            edit_format="ask",
            summarize_from_coder=False,
            include_text_and_md=True,  # Prioritize text and markdown files in repo map
        )
        
        # Run the LLM to get the response
        persona_coder.cur_messages.append({"role": "user", "content": prompt})
        response = persona_coder.run(with_message=prompt)

        # Extract the content from the response
        if isinstance(response, dict):
            content = response.get("content", "")
        else:
            content = str(response)
        
        # Try to parse the JSON response
        try:
            # First try direct JSON parsing
            persona_info = json.loads(content)
        except json.JSONDecodeError as e:
            # If that fails, try to extract JSON using regex
            match = re.search(r'({.*})', content, re.DOTALL)
            if match:
                persona_info = json.loads(match.group(1))
            else:
                self.io.tool_error(f"Error parsing persona information: {e}")
                self.io.tool_output("Response content:")
                self.io.tool_output(content)
                raise e
        
        # Extract the persona information
        persona_type = persona_info.get("persona_type", "advisor")
        suggested_file = persona_info.get("suggested_file")
        
        # # Display reasoning to the user
        # reasoning = persona_info.get("reasoning", "")
        # if reasoning:
        #     self.io.tool_output(f"Reasoning: {reasoning}")
        
        return persona_type, suggested_file

    def create_persona(self, persona_type, file_path, question):
        """Create a new persona file if it doesn't exist.
        
        Args:
            persona_type: The type of advisor persona
            file_path: The path where the persona file should be created
            question: The original question to help generate the persona
            
        Returns:
            The content of the persona file
        """
        self.io.tool_output(f"Creating new {persona_type} advisor persona...")
        
        # Create a prompt to generate the persona
        prompt = f"""
I need to create a detailed advisor persona for a {persona_type} expert who will answer questions about code.

The first question this persona will answer is:
"{question}"

Please create a detailed description of this persona including:
1. Background and expertise
2. Perspective and approach to problems
3. Key principles they follow
4. Tone and communication style
5. Areas of special focus within their domain

The description should be comprehensive enough to guide consistent advice-giving in the persona's voice. Write your response in markdown (.md) format.
"""

        # Import this here to avoid circular imports
        from aider.coders.base_coder import Coder

        persona_coder = Coder.create(
            io=self.io,
            from_coder=self.coder,
            edit_format="ask",
            summarize_from_coder=False,
            include_text_and_md=True,  # Prioritize text and markdown files in repo map
        )
        
        # Run the LLM to get the response
        persona_coder.cur_messages.append({"role": "user", "content": prompt})
        response = persona_coder.run(with_message=prompt)
        
        # Extract the content from the response
        if isinstance(response, dict):
            content = response.get("content", "")
        else:
            content = str(response)
        
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write the persona to the file
        with open(file_path, 'w') as f:
            f.write(f"# {persona_type.title()} Advisor Persona\n\n")
            f.write(content)
        
        self.io.tool_output(f"Created new persona file at: {file_path}")
        
        return content

    def get_persona_content(self, file_path):
        """Read the content of an existing persona file.
        
        Args:
            file_path: The path to the persona file
            
        Returns:
            The content of the persona file
        """
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            return content
        except FileNotFoundError:
            self.io.tool_error(f"Persona file not found: {file_path}")
            return None
        except Exception as e:
            self.io.tool_error(f"Error reading persona file: {e}")
            return None

    def create_advice_prompt(self, persona_content, question):
        """Create a prompt that includes the persona and the question.
        
        Args:
            persona_content: The content of the persona file
            question: The user's question
            
        Returns:
            A prompt for the LLM
        """
        prompt = f"""
You are an advisor with the following persona:

{persona_content}

Please answer this question from the perspective of your persona:

{question}

Provide a thoughtful, detailed response that reflects your expertise and perspective as described in your persona.
"""
        return prompt
        
    def generate_advice(self, persona_content, persona_type, question):
        """Generate advice using the persona.
        
        Args:
            persona_content: The content of the persona file
            persona_type: The type of advisor persona
            question: The user's question
            
        Returns:
            The advice from the persona, or None if there was an error
        """
        self.io.tool_output(f"Generating advice from the {persona_type} advisor persona...")
        
        # Create a prompt that includes the persona and the question
        advice_prompt = self.create_advice_prompt(persona_content, question)
        
        # Create a temporary coder to ask this question
        from aider.coders.base_coder import Coder
        
        advice_coder = Coder.create(
            io=self.io,
            from_coder=self.coder,
            edit_format="ask",
            summarize_from_coder=False,
            include_text_and_md=True,  # Prioritize text and markdown files in repo map
        )
        
        # Run the LLM to get the advice
        advice_coder.cur_messages.append({"role": "user", "content": advice_prompt})
        response = advice_coder.run(with_message=advice_prompt)
        
        # Extract the content from the response
        if isinstance(response, dict):
            advice = response.get("content", "")
        else:
            advice = str(response)
        
        # Add the advice to the chat history
        self.coder.cur_messages += [
            {"role": "user", "content": f"Advice from {persona_type} advisor persona:\n\n{advice}"},
            {"role": "assistant", "content": "I've provided advice based on the requested persona."}
        ]
        
        return advice

    def get_persona(self, question):
        """Get or create a persona for the given question.
        
        Args:
            question: The user's question
            
        Returns:
            A tuple of (persona_content, persona_type) or (None, None) if there was an error
        """
        # Identify which persona should answer this question
        persona_type, suggested_file = self.identify_persona(question)
        
        # Handle case where neither file exists
        if not suggested_file:
            self.io.tool_error("The LLM couldn't identify or suggest a persona file.")
            return None, None

        # Check if the suggested file already exists
        if os.path.exists(suggested_file):
            self.io.tool_output(f"Found suitable {persona_type} advisor persona in: {suggested_file}")
            persona_content = self.get_persona_content(suggested_file)
            if not persona_content:
                return None, None
        else:
            # Need to create a new persona file
            self.io.tool_output(f"No existing {persona_type} advisor persona found.")
            self.io.tool_output(f"Suggested creating new persona at: {suggested_file}")

            # Confirm with the user before creating a new persona file
            if not self.io.confirm_ask(f"Create new {persona_type} advisor persona?", default="y"):
                self.io.tool_output("Persona creation cancelled.")
                return None, None

            persona_content = self.create_persona(persona_type, suggested_file, question)
            if not persona_content:
                return None, None
        
        return persona_content, persona_type
