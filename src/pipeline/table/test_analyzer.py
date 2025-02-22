import asyncio
import os
from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.table.analyzer import TableDependencyAnalyzer
from logging import Logger, INFO, StreamHandler, Formatter

async def test_table_dependency():
    # Use default settings from parser
    project = ProjectStructure.parse_project(
        project_name="UserAuthenticationProject11",
        base_path="source_code/UserAuthenticationProject11",
        lean_base_path="lean_project"
    )
    
    print(f"\nProject: {project.name}")
    print("Services:")
    for service in project.services:
        print(f"\nService: {service.name}")
        print("Tables:")
        for table in service.tables:
            print(f"- {table.name}")
            print("  Description:")
            for line in str(table.description).split('\n'):
                print(f"    {line}")
    
    # Create and run analyzer
    logger = Logger("test_analyzer")
    # Set to info level
    logger.setLevel(INFO)
    # Add stream handler to logger
    stream_handler = StreamHandler()
    stream_handler.setLevel(INFO)
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    analyzer = TableDependencyAnalyzer(model="deepseek-r1")
    try:
        result = await analyzer.run(project, logger)
        
        print("\nAnalysis Results:")
        print("\nDependencies:")
        for table, deps in result.dependencies.items():
            print(f"{table} depends on: {deps}")
            
        print("\nTopological Order:")
        if result.topological_order:
            print(" -> ".join(result.topological_order))
        else:
            print("No valid topological order (cycle detected)")
            
    except Exception as e:
        print(f"Analysis failed: {str(e)}")

def main():
    asyncio.run(test_table_dependency())

if __name__ == "__main__":
    main() 