import asyncio
import os
from pathlib import Path
from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.api.types import APIFormalizationInfo
from src.pipeline.api.formalizer import APIFormalizer
from logging import Logger, INFO, StreamHandler, Formatter

async def test_api_formalizer():
    # Create and configure logger
    logger = Logger("test_api_formalizer")
    logger.setLevel(INFO)
    stream_handler = StreamHandler()
    stream_handler.setLevel(INFO)
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Load the API dependency result from previous step
    api_dependency = APIFormalizationInfo.load(Path("outputs") / "api_dependency.json")
    
    logger.info("Loaded API dependency info")
    logger.info(f"Project: {api_dependency.project.name}")
    logger.info(f"API dependencies: {api_dependency.api_dependencies}")
    logger.info(f"API topological order: {api_dependency.api_topological_order}")
    
    model = os.getenv("MODEL", "qwen-max-latest")
    # Create and run formalizer
    api_formalizer = APIFormalizer(model=model, max_retries=10)
    api_formalization = await api_formalizer.run(api_dependency, logger)

    # Print results
    logger.info("\nFormalization Results:")
    logger.info(f"Total APIs: {len(api_dependency.api_dependencies)}")
    logger.info(f"Successfully formalized: {len(api_formalization.formalized_apis)}")
    
    # Print each formalized API and its Lean code
    logger.info("\nFormalized APIs:")
    for api_name in api_formalization.formalized_apis:
        service, api = api_formalization.project._find_api_with_service(api_name)
        if service and api and api.lean_code:
            logger.info(f"\n{service.name}.{api_name}:")
            logger.info(f"Import path: {api_formalization.project.get_lean_import_path('api', service.name, api_name)}")
            logger.info("Lean code:")
            logger.info(api.lean_code)

    # Save results
    Path("outputs").mkdir(exist_ok=True)
    api_formalization.save(Path("outputs") / "api_formalization.json")
    logger.info("\nSaved API formalization results")

def main():
    asyncio.run(test_api_formalizer())

if __name__ == "__main__":
    main() 