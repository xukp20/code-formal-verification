from typing import Optional, List, Dict, Any
from langchain_openai import ChatOpenAI
from src.utils.apis.router import GLOBAL_ROUTER
import logging
import asyncio

async def _call_openai_completion_async(
    model: str,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    verbose: bool = False,
    logger: logging.Logger = None,
    **kwargs
) -> Optional[str]:
    """
    Async function to call OpenAI completion API with routing support
    """
    try:
        # Get backend configuration if not provided
        if base_url is None or api_key is None:
            if GLOBAL_ROUTER is None:
                raise ValueError("No GLOBAL_ROUTER available and no base_url/api_key provided")
            actual_model, router_base_url, router_api_key = GLOBAL_ROUTER.get_backend(model)
            base_url = base_url or router_base_url
            api_key = api_key or router_api_key
            model = actual_model

        if verbose:
            print("Calling API Kwargs")
            print("-"*20)
            for key, value in kwargs.items():
                print(f"{key}: {value}")
            print(f"Model: {model}")
            print(f"Base URL: {base_url}")
            print("-"*20)

        if logger is not None:
            logger.info(f"Calling API Kwargs")
            logger.info("-"*20)
            for key, value in kwargs.items():
                logger.info(f"{key}: {value}")
            logger.info(f"Model: {model}")
            logger.info(f"Base URL: {base_url}")
            logger.info("-"*20)
            
        # Construct messages
        messages = []
        
        # Add system message if provided
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            # NOTE: We use user message to pass system prompt now
            # messages.append({"role": "user", "content": system_prompt})
        
        # Add history messages if provided
        if history:
            messages.extend(history)
            
        # Add user message if provided
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})

        # Create ChatOpenAI instance with a timeout of 300 seconds
        client = ChatOpenAI(
            model=model,
            openai_api_base=base_url,
            openai_api_key=api_key,
            timeout=300,  # Set timeout to 300 seconds
            **kwargs
        )

        # Get completion
        response = await client.ainvoke(messages)

        return response.content

    except Exception as e:
        print(e)
        return None 
    

def _call_openai_completion(
    model: str,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    verbose: bool = False,
    logger: logging.Logger = None,
    **kwargs
) -> Optional[str]:
    try:
        # Get backend configuration if not provided
        if base_url is None or api_key is None:
            if GLOBAL_ROUTER is None:
                raise ValueError("No GLOBAL_ROUTER available and no base_url/api_key provided")
            actual_model, router_base_url, router_api_key = GLOBAL_ROUTER.get_backend(model)
            base_url = base_url or router_base_url
            api_key = api_key or router_api_key
            model = actual_model

        if verbose:
            print("Calling API Kwargs")
            print("-"*20)
            for key, value in kwargs.items():
                print(f"{key}: {value}")
            print(f"Model: {model}")
            print(f"Base URL: {base_url}")
            print("-"*20)

        if logger is not None:
            logger.info(f"Calling API Kwargs")
            logger.info("-"*20)
            for key, value in kwargs.items():
                logger.info(f"{key}: {value}")
            logger.info(f"Model: {model}")
            logger.info(f"Base URL: {base_url}")
            logger.info("-"*20)
            
        # Construct messages
        messages = []
        
        # Add system message if provided
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Add history messages if provided
        if history:
            messages.extend(history)

        # Add user message if provided
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})

        # Create ChatOpenAI instance with a timeout of 60 seconds
        client = ChatOpenAI(
            model=model,
            openai_api_base=base_url,
            openai_api_key=api_key,
            timeout=60,  # Set timeout to 60 seconds
            **kwargs
        )

        # Get completion
        response = client.invoke(messages)

        return response.content

    except Exception as e:
        print(e)
        return None
        

if __name__ == "__main__":
    import asyncio
    asyncio.run(_call_openai_completion_async("deepseek-chat", user_prompt="Hello, how are you?", verbose=True))