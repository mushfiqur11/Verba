import os

import json
# import aiohttp

from goldenverba.components.interfaces import Generator
from transformers import pipeline
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from torch import bfloat16, cuda
from transformers import BitsAndBytesConfig


class Llama3Generator(Generator):
    def __init__(self):
        super().__init__()
        self.name = "Llama3"
        self.description = "Generator using a local running Llama3 Model from Hugging Face"
        self.requires_env = ["HUGGINGFACE_TOKEN", "LLAMA3_MODEL_ID"]
        self.streamable = True
        self.context_window = 8000

    async def generate_stream(
        self,
        queries: list[str],
        context: list[str],
        conversation: dict = None,
    ):
        """Generate a stream of response dicts based on a list of queries and list of contexts, and includes conversational context
        @parameter: queries : list[str] - List of queries
        @parameter: context : list[str] - List of contexts
        @parameter: conversation : dict - Conversational context
        @returns Iterator[dict] - Token response generated by the Generator in this format {system:TOKEN, finish_reason:stop or empty}.
        """
        access_token = os.environ.get("HUGGINGFACE_TOKEN", "")
        if access_token == "":
            yield {
                "message": "Missing Hugging Face Token",
                "finish_reason": "stop",
            }
        model_name = os.environ.get("LLAMA3_MODEL_ID", "")
        if model_name == "":
            yield {
                "message": "Missing Llama3 Model",
                "finish_reason": "stop",
            }

        # tokenizer = AutoTokenizer.from_pretrained(model_name, token=access_token)
        # model = AutoModelForCausalLM.from_pretrained(model_name, token=access_token)
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=bfloat16
        )
        tokenizer = AutoTokenizer.from_pretrained(model_name, 
                                          token=access_token)
        model = AutoModelForCausalLM.from_pretrained(model_name, 
                                                    token=access_token,
                                                    quantization_config=bnb_config)


        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            model_kwargs={"torch_dtype": torch.float16},
            # device=3,
        )

        terminators = [
            pipe.tokenizer.eos_token_id,
            pipe.tokenizer.convert_tokens_to_ids("<|eot_id|>")
        ]
        
        if conversation is None:
            conversation = {}
        messages = self.prepare_messages(queries, context, conversation)

        try:
            # data = {"model": model, "messages": messages}
            # async with aiohttp.ClientSession() as session:
                # async with session.post(url, json=data) as response:
                    # async for line in response.content:
            
            outputs = pipe(
                messages,
                max_new_tokens=256,
                eos_token_id=terminators,
                do_sample=True,
                temperature=0.6,
                top_p=0.9,
            )
            assistant_response = outputs[0]["generated_text"][-1]["content"]
            yield {
                "message": assistant_response,
                "finish_reason": "",
            }

            # if line.strip():  # Ensure line is not just whitespace
            #     json_data = json.loads(
            #         line.decode("utf-8")
            #     )  # Decode bytes to string then to JSON
            #     message = json_data.get("message", {}).get("content", "")
            #     finish_reason = (
            #         "stop" if json_data.get("done", False) else ""
            #     )

            #     yield {
            #         "message": message,
            #         "finish_reason": finish_reason,
            #     }
            # else:
            #     yield {
            #         "message": "",
            #         "finish_reason": "stop",
            #     }

        except Exception:
            raise

    def prepare_messages(
        self, queries: list[str], context: list[str], conversation: dict[str, str]
    ) -> dict[str, str]:
        """
        Prepares a list of messages formatted for a Retrieval Augmented Generation chatbot system, including system instructions, previous conversation, and a new user query with context.

        @parameter queries: A list of strings representing the user queries to be answered.
        @parameter context: A list of strings representing the context information provided for the queries.
        @parameter conversation: A list of previous conversation messages that include the role and content.

        @returns A list of message dictionaries formatted for the chatbot. This includes an initial system message, the previous conversation messages, and the new user query encapsulated with the provided context.

        Each message in the list is a dictionary with 'role' and 'content' keys, where 'role' is either 'system' or 'user', and 'content' contains the relevant text. This will depend on the LLM used.
        """
        messages = [
            {
                "role": "system",
                "content": self.system_message,
            }
        ]

        for message in conversation:
            messages.append({"role": message.type, "content": message.content})

        query = " ".join(queries)
        user_context = " ".join(context)

        messages.append(
            {
                "role": "user",
                "content": f"With this provided context: '{user_context}' Please answer this query: '{query}'",
            }
        )

        return messages
