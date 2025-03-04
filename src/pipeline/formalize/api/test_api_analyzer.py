import asyncio
import os
from pathlib import Path
from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.formalize.api.types import APIDependencyInfo
from src.pipeline.formalize.api.api_analyzer import APIAnalyzer
from logging import Logger, INFO, StreamHandler, Formatter

async def test_api_analyzer():
    # Create and configure logger
    logger = Logger("test_api_analyzer")
    logger.setLevel(INFO)
    stream_handler = StreamHandler()
    stream_handler.setLevel(INFO)
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Load the API table dependency result from previous step
    api_table_dependency = APIDependencyInfo.load(Path("outputs") / "api_table_dependency.json")
    
    logger.info("Loaded API table dependency info")
    logger.info(f"Project: {api_table_dependency.project.name}")
    logger.info(f"API-Table dependencies: {api_table_dependency.api_table_dependencies}")
    
    model = os.getenv("MODEL", "qwen-max-latest")
    # Create and run analyzer
    api_analyzer = APIAnalyzer(model=model)
    try:
        api_dependency = await api_analyzer.run(api_table_dependency, logger)
    except Exception as e:
        logger.error(f"Error during API dependency analysis: {e}")
        return

    # Print results
    logger.info("\nAPI Dependencies:")
    for api_name, deps in api_dependency.api_dependencies.items():
        logger.info(f"{api_name} depends on APIs: {deps}")

    logger.info("\nAPI Topological Order:")
    if api_dependency.api_topological_order:
        for service_name, api_name in api_dependency.api_topological_order:
            logger.info(f"{service_name}.{api_name}")
    else:
        logger.warning("No valid topological order (cycle detected)")

    # Save results
    Path("outputs").mkdir(exist_ok=True)
    api_dependency.save(Path("outputs") / "api_dependency.json")
    logger.info("\nSaved API dependency analysis results")

def main():
    asyncio.run(test_api_analyzer())

if __name__ == "__main__":
    main() 