import asyncio
import os
from pathlib import Path
from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.table.types import TableFormalizationInfo
from src.pipeline.api.table_analyzer import APITableDependencyAnalyzer
from logging import Logger, INFO, StreamHandler, Formatter

async def test_api_table_analyzer():
    # Create and configure logger
    logger = Logger("test_api_analyzer")
    logger.setLevel(INFO)
    stream_handler = StreamHandler()
    stream_handler.setLevel(INFO)
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Load the table formalization result from previous step
    table_formalization = TableFormalizationInfo.load(Path("outputs") / "table_formalization.json")
    
    logger.info("Loaded table formalization info")
    logger.info(f"Project: {table_formalization.project.name}")
    logger.info(f"Formalized tables: {table_formalization.formalized_tables}")
    
    # Create and run analyzer
    api_analyzer = APITableDependencyAnalyzer()
    try:
        api_dependency = await api_analyzer.run(table_formalization, logger)
    except Exception as e:
        logger.error(f"Error during API analysis: {e}")
        return

    # Print results
    logger.info("\nAPI Table Dependencies:")
    for api_name, table_deps in api_dependency.api_table_dependencies.items():
        logger.info(f"{api_name} depends on tables: {table_deps}")

    # Save results
    Path("outputs").mkdir(exist_ok=True)
    api_dependency.save(Path("outputs") / "api_table_dependency.json")
    logger.info("\nSaved API table dependency analysis results")

def main():
    asyncio.run(test_api_table_analyzer())

if __name__ == "__main__":
    main() 