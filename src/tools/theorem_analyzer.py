from pathlib import Path
from typing import Dict, Tuple
import json
from dataclasses import dataclass

from src.types.project import ProjectStructure

@dataclass
class TheoremStats:
    total_api_theorems: int = 0
    proved_api_theorems: int = 0
    total_api_negative_theorems: int = 0
    proved_api_negative_theorems: int = 0
    
    total_table_theorems: int = 0
    proved_table_theorems: int = 0
    total_table_negative_theorems: int = 0
    proved_table_negative_theorems: int = 0

    def __str__(self) -> str:
        return f"""Theorem Analysis Results:

API Theorems:
- Regular theorems: {self.proved_api_theorems}/{self.total_api_theorems} proved
- Negative theorems: {self.proved_api_negative_theorems}/{self.total_api_negative_theorems} proved

Table Theorems:
- Regular theorems: {self.proved_table_theorems}/{self.total_table_theorems} proved
- Negative theorems: {self.proved_table_negative_theorems}/{self.total_table_negative_theorems} proved

Total Progress:
- Regular theorems: {self.proved_api_theorems + self.proved_table_theorems}/{self.total_api_theorems + self.total_table_theorems} proved
- Negative theorems: {self.proved_api_negative_theorems + self.proved_table_negative_theorems}/{self.total_api_negative_theorems + self.total_table_negative_theorems} proved
"""

def analyze_theorems(project_file: Path) -> TheoremStats:
    """Analyze theorem statistics from a project file
    
    Args:
        project_file: Path to the project JSON file
        
    Returns:
        TheoremStats containing theorem counts
    """
    # Load project
    with open(project_file) as f:
        data = json.load(f)
    project = ProjectStructure.from_dict(data)
    
    stats = TheoremStats()
    
    # Analyze API theorems
    for service in project.services:
        for api in service.apis:
            if not api.theorems:
                continue
                
            for theorem in api.theorems:
                # Regular theorems
                if theorem.theorem:
                    stats.total_api_theorems += 1
                    if theorem.theorem.theorem_proved:
                        stats.proved_api_theorems += 1
                
                # Negative theorems
                if theorem.theorem_negative:
                    stats.total_api_negative_theorems += 1
                    if theorem.theorem_negative.theorem_proved:
                        stats.proved_api_negative_theorems += 1
    
    # Analyze table theorems
    for service in project.services:
        for table in service.tables:
            if not table.properties:
                continue
                
            for prop in table.properties:
                if not prop.theorems:
                    continue
                    
                for theorem in prop.theorems:
                    # Regular theorems
                    if theorem.theorem:
                        stats.total_table_theorems += 1
                        if theorem.theorem.theorem_proved:
                            stats.proved_table_theorems += 1
                    
                    # Negative theorems
                    if theorem.theorem_negative:
                        stats.total_table_negative_theorems += 1
                        if theorem.theorem_negative.theorem_proved:
                            stats.proved_table_negative_theorems += 1
    
    return stats

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Analyze theorem statistics in a project')
    parser.add_argument('-p', '--project_file', type=Path, help='Path to project JSON file')
    args = parser.parse_args()
    
    stats = analyze_theorems(args.project_file)
    print(stats)

if __name__ == '__main__':
    main() 