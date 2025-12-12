import openai
from openai import OpenAI, OpenAIError
import json
from app.config.config import settings
from typing import Tuple
import structlog
import requests
from app.common.exception import GeneralDataException, IntegrityException
import json
from typing import Dict
import google.generativeai as genai

logger = structlog.get_logger()


'''
                {
        "context_switch": true,
        "reason": "The new prompt is about flying, which is unrelated to weight loss.",
        "unsafe": true,
        "unsafe_reason": "The prompt includes language related to criminal activity.",
        "unsupported_domain": true,
        "domain_reason": "Flying an airplane is not part of the supported domains."
        }
'''

openai.api_key = settings.OPEN_AI_APIKEY

# Supported domains in your app
SUPPORTED_DOMAINS = [
    "career management",
    "personal health",
    "new skills"
]

async def extract_json_from_string(response_text: str) -> str:
    """
    Removes leading `````` from a Gemini response,
    returning the inner JSON string.
    """
    # Remove leading and trailing whitespace
    cleaned = response_text.strip()
    # Remove leading `````` if present
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].lstrip("\n")
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].lstrip("\n")
    # Remove trailing ```
    if cleaned.endswith("```"):
        cleaned = cleaned[:-len("```")].rstrip()
    return cleaned

async def detect_context_switch(current_prompt: str,  previous_prompt: str) -> dict:

    # Run OpenAI API with function call

    try:
       # Initialize client
        client = OpenAI(api_key= settings.OPEN_AI_API_KEY)

        response = client.chat.completions.create(
        model="gpt-4-turbo",  # or "gpt-3.5-turbo", "gpt-4-turbo"
        response_format={"type": "json_object"},  # Structured output
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an assistant that analyzes a user's new prompt to determine if upon joining the statement to the   "
                    "previous prompt would still keep the overall intent. See below for examples. You must also identify whether the new prompt "
                    "contains unsafe content (e.g., obscene language, illegal activity), or whether it falls outside the supported domains. "
                    "Also provide a revised summary of current and previous prompt that will be a good chatgpt user prompt if context_switch is false"
                    "Example 1: "
                    "Previous Prompt: I want a plan to learn music"
                    "Current Prompt: I am 50 years old and have injuries in my leg and hand"
                    "context_switch: False"
                    "Reason: Learning music as you age will be difficult and they want a plan that will allow them to learn in incremental steps. Also injury require a throughtful approach"
                     "Example 2: "
                    "Previous Prompt: Give me a good diet plan to improve my fitness"
                    "Current Prompt: I am a vegetarian and I have diabetes and high blood pressue"
                    "context_switch: False"
                    "Reason: User is sharing their medical condition and food preference. This is a good input to improve the diet plan recommendationj"
                     "Example 3: "
                    "Previous Prompt: I want a plan to learn music"
                    "Current Prompt: I am going to India"
                    "context_switch: True"
                    "Reason: There is correlation between user traveling and their intent to learn music"
                    "Example 1: "
                    "Previous Prompt: I want a plan to executive communication skills"
                    "Current Prompt: I want to learn airplane"
                    "context_switch: True"
                    "Reason: These are two independent things that the user wants to learn"
                    "Expected Output: Return a JSON object with: context_switch (bool), reason (string), unsafe (bool), unsafe_reason (string), "
                    "unsupported_domain (bool), domain_reason (string), revised_summary(string)."
                )
            },
            {
                "role": "user",
                            "content": f"""
            Previous Prompt: "{previous_prompt}"
            Current Prompt: "{current_prompt}"
            Supported Domains: {SUPPORTED_DOMAINS}

            Please analyze the context and return a structured JSON response.
                            """
                        }
                    ]
                )

        res =  response.choices[0].message.content
        logger.info(f"The result from context detection is {res}")
        return json.loads(res)


    except OpenAIError as e:
        logger.error(f"OpenAI API Error: {e}")
        raise GeneralDataException(
            f"An error occurred while communicating with OpenAI. Please try again {str(e)}",
            context={"detail": f"An error occurred while communicating with OpenAI. Please try again {str(e)}"}
        )


    except requests.exceptions.RequestException as e:
        logger.error(f"OpenAI API Error: {e}")
        raise GeneralDataException(
            f"Possible network issue when processing prompt {str(e)}",
            context={"detail": f"Possible network issue {str(e)}"}
        )

    except ValueError as e:
        logger.error(f"Value Error: {e}")
        raise GeneralDataException(
            f"Possible value issue when processing prompt  {str(e)}",
            context={"detail": f"Possible value issue from openAI {str(e)}"}
        )
        logger.error(f"Response Error: {e}")
    except IntegrityException as e:

        logger.error(f"IntegrityError when when processing prompt : {str(e)}")
        raise IntegrityException(
            f"IntegrityError when when processing prompt : {str(e)}",
            context = {"detail": f"IntegrityError when when processing prompt : {str(e)}"}
        )
    except GeneralDataException as e:
        logger.error(f"Database error when processing prompt: {str(e)}")
        raise GeneralDataException(
            f"Database error when processing prompt: {str(e)}",
            context={"detail": f"Database error when processing prompt: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error occured  when processing prompt: {str(e)}")
        raise GeneralDataException(
            f"Some general error occured  when processing prompt: {str(e)}",
            context = { "detail": f"Some general error occured  when processing prompt: {str(e)}"})
    


async def detect_context_switch_gemini(current_prompt: str, previous_prompt: str) -> Dict:
    """
    Analyzes if a new user prompt changes the intent of a previous prompt,
    identifies unsafe content or unsupported domains, and provides a revised summary.

    Args:
        current_prompt: The user's latest input.
        previous_prompt: The user's prior input.

    Returns:
        A dictionary (parsed from JSON) containing the analysis results.
    """
    try:
        # Initialize Gemini Pro model
        genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name='models/gemini-2.0-flash')

        prompt = f"""
        You are an assistant that analyzes a user's new prompt to determine if upon joining the statement to the
        previous prompt would still keep the overall intent. See below for examples. You must also identify whether the new prompt
        contains unsafe content (e.g., obscene language, illegal activity), or whether it falls outside the supported domains:
        {SUPPORTED_DOMAINS}. Also provide a revised summary of current and previous prompt that will be a good Gemini user prompt if context_switch is false.

        Example 1:
        Previous Prompt: I want a plan to learn music
        Current Prompt: I am 50 years old and have injuries in my leg and hand
        context_switch: False
        Reason: Learning music as you age will be difficult and they want a plan that will allow them to learn in incremental steps. Also injury require a thoughtful approach
        Example 2:
        Previous Prompt: Give me a good diet plan to improve my fitness
        Current Prompt: I am a vegetarian and I have diabetes and high blood pressure
        context_switch: False
        Reason: User is sharing their medical condition and food preference. This is a good input to improve the diet plan recommendation
        Example 3:
        Previous Prompt: I want a plan to learn music
        Current Prompt: I am going to India
        context_switch: True
        Reason: There is no clear correlation between user traveling and their intent to learn music
        Example 4:
        Previous Prompt: I want a plan to executive communication skills
        Current Prompt: I want to learn airplane
        context_switch: True
        Reason: These are two independent things that the user wants to learn
        Expected Output: Return a JSON object with: "context_switch" (bool), "reason" (string), "unsafe" (bool), "unsafe_reason" (string),
        "unsupported_domain" (bool), "domain_reason" (string), "revised_summary" (string).

        Previous Prompt: "{previous_prompt}"
        Current Prompt: "{current_prompt}"
        """

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=15000,
                temperature=0.1,
                top_p=0.3,
            ),
        )
        gemini_content = response.text
        try:
            cleansed_text =await  extract_json_from_string(gemini_content)
            res_json = json.loads(cleansed_text)
            return res_json
            #return ContextAnalysisResult(**res_json)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from Gemini: {e}, Response text: {gemini_content}")
            raise ValueError(f"Could not decode JSON response from Gemini: {e}")
        except Exception as e:
            print(f"Error parsing Gemini response: {e}, Raw response: {gemini_content}")
            raise

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise

