import asyncio
import os
from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.table.formalizer import TableFormalizer
from src.pipeline.table.types import TableDependencyInfo
from logging import Logger, INFO, StreamHandler, Formatter
from pathlib import Path


async def test_table_formalizer():
    logger = Logger("test_formalizer")
    # Set to info level
    logger.setLevel(INFO)
    # Add stream handler to logger
    stream_handler = StreamHandler()
    stream_handler.setLevel(INFO)
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    table_dependency = TableDependencyInfo.load(Path("outputs") / "table_dependency.json")

    table_formalizer = TableFormalizer()
    # try:    
    table_formalization = await table_formalizer.run(table_dependency, logger)
    # except Exception as e:
        # logger.error(f"Error: {e}")
        # return

    print(table_formalization)

    # save to the dir
    Path("outputs").mkdir(exist_ok=True)
    table_formalization.save(Path("outputs") / "table_formalization.json")

def main():
    asyncio.run(test_table_formalizer())

if __name__ == "__main__":
    main()
