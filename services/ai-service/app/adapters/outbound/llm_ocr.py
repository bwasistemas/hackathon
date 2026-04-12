from strands import Agent

from app.adapters.outbound.helpers.llm import file_to_content_blocks, build_llm_client
from app.config import load_settings

settings = load_settings()


SYSTEM_PROMPT = """
                ## PERSONA
                You are a helpful assistant that extracts text from images and PDFs that represent architecture diagrams.

                ## INSTUCTIONS
                Analyze the image or PDF and return the pattern used in the diagram and the language used in the diagram.
                Create a description of the diagram analyzing the components and the relationships between them.


                ## EXAMPLES
                The diagram language is a UML class diagram. The diagram represents a MVC architecture with a controller, a model and a view.
                The diagram language is C4 model. The diagram represents a MVC architecture with a controller, a model and a view.
                The diagram language is BPMN. The diagram represents a MVC architecture with a controller, a model and a view.

                ## RULES
                YOU MUST RETURN THE LANGUAGE USED IN THE DIAGRAM.
                YOU MUST RETURN THE PATTERN USED IN THE DIAGRAM.
                """


class LlmOCRAdapter:
    def __init__(self):
        self._client = build_llm_client(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_id=settings.llm_ocr,
            max_tokens=3000,
            temperature=0,
        )

    async def analyze_diagram(self, file: str) -> str:
        extractor_agent = Agent(
            name="extractor",
            system_prompt=SYSTEM_PROMPT,
            model=self._client,
        )

        blocks = file_to_content_blocks(file)
        result = extractor_agent(blocks)
        return str(result)
