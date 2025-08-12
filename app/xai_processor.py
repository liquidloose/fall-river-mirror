# Standard library imports
import os

# Third-party imports
from fastapi.responses import JSONResponse
from xai_sdk import Client
from xai_sdk.chat import user, system

class XAIProcessor:
    """
    A processor class for handling xAI (x.AI) API interactions.
    
    This class provides functionality to communicate with the xAI API for generating
    AI-powered responses. It handles authentication, message formatting, and error
    handling for the xAI service.
    
    Attributes:
        api_key (str): The API key for xAI authentication, loaded from environment variables
    """
    
    def __init__(self):
        """
        Initialize the XAIProcessor with API key from environment variables.
        
        The API key should be set in the XAI_API_KEY environment variable.
        If not set, the processor will return error responses when attempting to use the API.
        """
        self.api_key = os.getenv("XAI_API_KEY")

    def get_response(self, context: str, message: str, committee: str = None, article_type: str = None, tone: str = None):
        """
        Generate a response using the xAI API based on provided context and message.
        
        This method creates a chat session with the xAI API, sends the context as a system
        message and the user message, then returns the generated response. It includes
        comprehensive error handling for missing API keys and API communication issues.
        
        Args:
            context (str): The system context/instructions to provide to the AI model.
                          This typically includes tone, article type, and other guidelines.
            message (str): The user's specific prompt or message to generate a response for.
        
        Returns:
            dict: A dictionary containing the AI-generated response in the format:
                  {"response": "generated_text", "committee": "committee_name", 
                   "context": "full_context", "prompt": "full_prompt", 
                   "article_type": "article_type", "tone": "tone"}
                  
        Raises:
            JSONResponse: Returns a 500 status code with error details if:
                - XAI_API_KEY environment variable is not set
                - API communication fails for any reason
        """
        # Check if API key is available
        if not self.api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "XAI_API_KEY environment variable is not set"},
            )

        try:
            # Initialize xAI client with timeout for long-running requests
            client = Client(api_key=self.api_key, timeout=3600)
            
            # Create a new chat session using the Grok-4 model
            chat = client.chat.create(model="grok-4")
            
            # Add system context and user message to the chat
            chat.append(system(context))
            chat.append(user(message))
            
            # Generate response from the AI model
            response = chat.sample()
            
            # Return the response content as a dictionary with all context information
            # Note: response.content is already a string, not an object with .text
            result = {
                "article_type": article_type,
                "tone": tone,
                "committee": committee,
                "context": context,
                "prompt": message,
                "response": response.content,
            }
            
            return result
            
        except Exception as e:
            # Handle any API communication errors
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get response from xAI: {str(e)}"},
            )
