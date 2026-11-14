Title: Google AI Studio

URL Source: https://aistudio.google.com/docs/get-started?codelanguage=python

Markdown Content:
## Getting started

This guide gets you started with the Gemini API using the [Interactions API](https://aistudio.google.com/docs/interactions-overview?codelanguage=python). You'll make your first API call in under a minute and explore text generation, multimodal understanding, image generation,structured output, tools, function calling, agents, and background execution.

The Interactions API is available through the[Python](https://github.com/googleapis/python-genai) and[JavaScript](https://github.com/googleapis/js-genai) SDKs, as well as through REST.

## 1. Get an API key

To use the Gemini API, you need to have an API key to authenticate your requests, enforce security limits, and track usage to your account.

*   Google AI Studio automatically creates a project and API key for new users.You can copy it from the [API keys page](https://aistudio.google.com/api-keys).
*   If you need a new key, click **Create API key** in AI Studio and follow the dialog to add a new key-project pair.

[Create a Gemini API Key](https://aistudio.google.com/apikey)

Set your key as an environment variable:

`export GEMINI_API_KEY="YOUR_API_KEY"`

### Upgrade to the paid tier

Upgrading to the paid tier increases your rate limits and requires setting up Cloud Billing.

*   Click **Set up billing** on the AI Studio [API keys](https://aistudio.google.com/api-keys) or[Projects](https://aistudio.google.com/projects) pages.
*   Follow the Cloud Billing dialog to create or link a billing account, add a payment method, and prepay a minimum of $5 (or currency equivalent) in paid credits.
*   View your API usage in [Google AI Studio](https://aistudio.google.com/usage)under **Dashboard**>**Usage**.

See the [Billing page](https://aistudio.google.com/docs/billing?codelanguage=python) for more information.

## 2. Install the SDK and make your first call

Install the SDK and generate text with a single API call.

Install the SDK:

`pip install -U google-genai`

Initialize the client and make a request:

```
from google import genai

client = genai.Client()

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="Explain how AI works in a few words"
)
print(interaction.output_text)
```

While the SDKs expose the full response, they also provide convenience properties like `interaction.output_text` and `interaction.output_image` to access final outputs directly. Learn more about the response structure in the[Interactions overview](https://aistudio.google.com/docs/interactions-overview?codelanguage=python) or read the [text generation guide](https://aistudio.google.com/docs/text-generation?codelanguage=python) for details on system instructions and generation config.

**Building with an AI coding agent?** Install the skill and then paste the prompt to get started with the Gemini API using Interactions:

`npx skills add google-gemini/gemini-skills --skill gemini-api-dev`

## 3. Stream the response

For more fluid interactions, stream the response as it's generated. Each`step.delta` event delivers a chunk of text you can display immediately.

```
from google import genai

client = genai.Client()

stream = client.interactions.create(
    model="gemini-3.8-flash",
    input="Explain how AI works",
    stream=True
)
for event in stream:
    print(event)
```

For a detailed look at handling streaming events and delta types, see the[streaming interactions guide](https://aistudio.google.com/docs/streaming?codelanguage=python).

## 4. Multi-turn conversations

The Interactions API supports multi-turn conversations with two approaches:

*   **Stateful (recommended)**: Continue a conversation on the server using`previous_interaction_id`. Ideal for most chat and agentic workflows where you want the server to manage history and optimize caching.
*   **Stateless**: Manage the conversation history on the client by passing all previous turns (including intermediate model thought and tool steps) in each request.

Chain interactions by passing `previous_interaction_id`. The server manages the full conversation history for you.

```
from google import genai

client = genai.Client()

# Server-side state (recommended)
interaction1 = client.interactions.create(
    model="gemini-3.8-flash",
    input="I have 2 dogs in my house.",
)
print("Response 1:", interaction1.output_text)

interaction2 = client.interactions.create(
    model="gemini-3.8-flash",
    input="How many paws are in my house?",
    previous_interaction_id=interaction1.id,
)
print("Response 2:", interaction2.output_text)
```

## 5. Multimodal understanding

Gemini models understand images, audio, video, and documents natively. Pass media alongside text in a single request.

```
import base64
from google import genai

client = genai.Client()

# Load a local image
with open("sample.jpg", "rb") as f:
    image_bytes = f.read()
image_b64 = base64.b64encode(image_bytes).decode("utf-8")

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input=[
        {"type": "text", "text": "Compare this local image and this remote audio file."},
        {
            "type": "image",
            "data": image_b64,
            "mime_type": "image/jpeg"
        },
        {
            "type": "audio",
            "uri": "https://storage.googleapis.com/generativeai-downloads/data/sample.mp3",
            "mime_type": "audio/mp3"
        }
    ]
)
print(interaction.output_text)
```

Explore how to pass images, video, and audio files in the [image understanding guide](https://aistudio.google.com/docs/image-understanding?codelanguage=python).

## 6. Multimodal generation

Gemini can generate images natively using the [Nano Banana](https://aistudio.google.com/docs/image-generation?codelanguage=python) image models.

```
import base64
from google import genai

client = genai.Client()

interaction = client.interactions.create(
    model="gemini-3.1-flash-image",
    input="Generate an image of a futuristic city skyline at sunset",
)

with open("generated_image.png", "wb") as f:
    f.write(base64.b64decode(interaction.output_image.data))
```

When the model generates an image, it returns the base64-encoded image data in a step within the `steps` array, as well as via the `output_image` convenience property. Check out the [image generation guide](https://aistudio.google.com/docs/image-generation?codelanguage=python) to learn about aspect ratios, image editing, and references.

## 7. Use structured output

Configure the model to return JSON that matches a schema you define. Structured output works with [Pydantic](https://docs.pydantic.dev/latest/) (Python) and[Zod](https://zod.dev/) (JavaScript).

```
from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional

class Recipe(BaseModel):
    recipe_name: str = Field(description="Name of the recipe.")
    ingredients: List[str] = Field(description="List of ingredients.")
    prep_time_minutes: Optional[int] = Field(description="Prep time in minutes.")

client = genai.Client()

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="Give me a recipe for banana bread",
    response_format={
        "type": "text",
        "mime_type": "application/json",
        "schema": Recipe.model_json_schema()
    },
)

recipe = Recipe.model_validate_json(interaction.output_text)
print(recipe)
```

The output text block contains a valid JSON string conforming exactly to the requested schema. To learn how to define more complex structures and recursive schemas, see the [structured output guide](https://aistudio.google.com/docs/structured-output?codelanguage=python).

## 8. Use tools

Ground the model's response in real-time information with Google Search. The API automatically searches, processes results, and returns citations.

```
from google import genai

client = genai.Client()

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="Who won the euro 2024?",
    tools=[{"type": "google_search"}]
)

print(interaction.output_text)

# Print citations
for step in interaction.steps:
    if step.type == "model_output":
        for content_block in step.content:
            if content_block.type == "text" and content_block.annotations:
                print("\nCitations:")
                for annotation in content_block.annotations:
                    if annotation.type == "url_citation":
                        print(f" [{annotation.title}]({annotation.url})")
```

The search steps are detailed within the interaction history, and the final output includes inline citations pointing to web sources.

You can learn how to extract search citations in the [Google Search grounding guide](https://aistudio.google.com/docs/google-search?codelanguage=python), or see how to combine multiple tools in the [tool combination guide](https://aistudio.google.com/docs/tool-combination?codelanguage=python).

## 9. Call your own functions

Function calling lets you connect the model to your code. You declare a function's name and parameters, the model decides when to call it and returns structured arguments, and you execute it locally and send the result back.

```
import json
from google import genai

client = genai.Client()

weather_tool = {
    "type": "function",
    "name": "get_current_temperature",
    "description": "Gets the current temperature for a given location.",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The city name, e.g. San Francisco",
            },
        },
        "required": ["location"],
    },
}

available_functions = {
    "get_current_temperature": lambda location: {
        "location": location, "temperature": "22", "unit": "celsius"
    },
}

user_input = "What is the temperature in London?"
previous_id = None

while True:
    interaction = client.interactions.create(
        model="gemini-3.8-flash",
        input=user_input,
        tools=[weather_tool],
        previous_interaction_id=previous_id,
    )

    function_results = []
    for step in interaction.steps:
        if step.type == "function_call":
            result = available_functions[step.name](**step.arguments)
            print(f"Called {step.name}({step.arguments}) → {result}")
            function_results.append({
                "type": "function_result",
                "name": step.name,
                "call_id": step.id,
                "result": [{"type": "text", "text": json.dumps(result)}],
            })

    if not function_results:
        break

    user_input = function_results
    previous_id = interaction.id

print(interaction.output_text)
```

For advanced features like parallel function calling or function choice modes,see the [function calling guide](https://aistudio.google.com/docs/function-calling?codelanguage=python).

## 10. Run a managed agent

Managed agents run in a remote sandbox with access to tools like code execution and file management. Pass an `agent` instead of a `model` and set`environment="remote"`.

```
from google import genai

client = genai.Client()

interaction = client.interactions.create(
    agent="antigravity-preview-09-2026",
    input="Write a Python script that generates the first 20 Fibonacci numbers and saves them to fibonacci.txt. Then read the file and print its contents.",
    environment="remote",
)
print(f"Environment: {interaction.environment_id}")
print(interaction.output_text)
```

You can also define and save [custom agents](https://aistudio.google.com/docs/custom-agents?codelanguage=python) with your own instructions, skills, and data sources.

## 11. Run tasks in the background

Set `background=True` to run long tasks asynchronously. Poll for results with`interactions.get()`.

```
import time
from google import genai

client = genai.Client()

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="Write a detailed analysis of the impact of artificial intelligence on modern healthcare.",
    background=True,
)
print(f"Started background task: {interaction.id}")
print(f"Status: {interaction.status}")

# Poll for completion
while True:
    result = client.interactions.get(interaction.id)
    print(f"Status: {result.status}")
    if result.status == "completed":
        print(f"\nResult:\n{result.output_text}")
        break
    elif result.status == "failed":
        print(f"Failed: {result.error}")
        break
    time.sleep(5)
```

Read about running models and agents asynchronously in the [background execution guide](https://aistudio.google.com/docs/background-execution?codelanguage=python).

## What's next

*   [Text generation](https://aistudio.google.com/docs/text-generation?codelanguage=python): System instructions, generation config, and advanced text patterns.
*   [Image generation](https://aistudio.google.com/docs/image-generation?codelanguage=python): Aspect ratios, image editing,and style references.
*   [Image understanding](https://aistudio.google.com/docs/image-understanding?codelanguage=python): Classification, object detection, and visual Q&A.
*   [Thinking](https://aistudio.google.com/docs/thinking?codelanguage=python): Use chain-of-thought reasoning for complex tasks.
*   [Function calling](https://aistudio.google.com/docs/function-calling?codelanguage=python): Parallel, compositional, and constrained function modes.
*   [Google Search](https://aistudio.google.com/docs/google-search?codelanguage=python): Grounding, citations, and search suggestions.
*   [Managed Agents](https://aistudio.google.com/docs/managed-agents-quickstart?codelanguage=python): Pre-built agents with code execution and file management.
*   [Deep Research](https://aistudio.google.com/docs/deep-research?codelanguage=python): Autonomous multi-step research with planning and synthesis.
*   [Structured output](https://aistudio.google.com/docs/structured-output?codelanguage=python): JSON schemas, enums, and recursive type definitions.