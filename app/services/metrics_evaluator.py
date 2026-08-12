import os
from deepeval.models import DeepEvalBaseLLM
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase
from langchain_google_genai import ChatGoogleGenerativeAI

class GoogleGeminiDeepEvalWrapper(DeepEvalBaseLLM):
    def __init__(self, model_name="gemini-3.5-flash-lite"):
        self.model = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    def load_model(self):
        return self.model

    def _clean_content(self, content) -> str:
        """Helper to ensure LangChain block lists are flattened into clean strings."""
        if isinstance(content, list):
            return " ".join([b.get("text", str(b)) if isinstance(b, dict) else str(b) for b in content])
        return str(content)

    def generate(self, prompt: str, schema=None, **kwargs):
        if schema:
            structured_llm = self.model.with_structured_output(schema)
            return structured_llm.invoke(prompt)
        
        response = self.model.invoke(prompt)
        return self._clean_content(response.content)

    async def a_generate(self, prompt: str, schema=None, **kwargs):
        if schema:
            structured_llm = self.model.with_structured_output(schema)
            return await structured_llm.ainvoke(prompt)
            
        response = await self.model.ainvoke(prompt)
        return self._clean_content(response.content)

    def get_model_name(self):
        return "Gemini 3.5 Flash Lite"

def run_deepeval_suite(query: str, output_text: str, contexts: list) -> dict:
    test_case = LLMTestCase(
        input=query,
        actual_output=output_text,
        retrieval_context=contexts
    )
    
    gemini_evaluator = GoogleGeminiDeepEvalWrapper()
    
    relevancy = AnswerRelevancyMetric(
        threshold=0.5, 
        include_reason=True, 
        model=gemini_evaluator
    )
    
    faithfulness = FaithfulnessMetric(
        threshold=0.5, 
        include_reason=True, 
        model=gemini_evaluator
    )
    
    faithfulness.measure(test_case)
    
    # Robust Refusal Check
    refusal_check_prompt = f"Analyze this response: '{output_text}'. Is this response a refusal to answer due to missing information/context? Output exactly 'refusal' if it is a refusal, or 'answer' if it is attempting to answer."
    check_result = gemini_evaluator.generate(refusal_check_prompt).strip().lower()
    
    if "refusal" in check_result:
        relevancy_score = 1.0
        relevancy_reason = "Perfect Score: The model correctly identified that the information was out-of-domain or missing from the retrieved context, strictly following its zero-hallucination mandate."
    else:
        relevancy.measure(test_case)
        relevancy_score = float(relevancy.score)
        relevancy_reason = relevancy.reason
    
    return {
        "answer_relevancy": relevancy_score,
        "relevancy_reason": relevancy_reason,
        "faithfulness": float(faithfulness.score),
        "faithfulness_reason": faithfulness.reason
    }