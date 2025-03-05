from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

from src.types.lean_structure import LeanProjectStructure

@dataclass
class LeanFile:
    """Base class for Lean file structures"""
    
    # Relative path from Lean project root
    relative_path: List[str]
    
    def generate_content(self) -> str:
        """Generate complete file content by concatenating all non-empty fields
        
        Returns:
            Complete file content with field comments
        """
        content = []
        
        # Get all fields except relative_path
        fields = {k: v for k, v in self.__dict__.items() 
                 if k != 'relative_path' and v is not None and v != ''}
        
        # Add each field with comment
        for field_name, field_value in fields.items():
            content.extend([
                f"-- {field_name}",
                field_value,
                ""  # Empty line after each field
            ])
            
        return "\n".join(content)

    def to_markdown(self, add_import_path: bool = True) -> str:
        """Convert Lean file to markdown format"""
        content = self.generate_content()
        if add_import_path:
            import_path = LeanProjectStructure.to_import_path(self.relative_path)
            content = f"-- import path: {import_path}\n\n{content}"
        return "```lean\n" + content + "\n```"

    @classmethod
    def parse_content(cls, content: str) -> Dict[str, str]:
        """Parse file content into fields based on comments
        
        Args:
            content: File content with field comments
        
        Returns:
            Dict mapping field names to their content
        """
        fields = {}
        current_field = None
        current_content = []
        
        for line in content.splitlines():
            if line.startswith("-- ") and line[3:].strip() in cls.__annotations__:
                # Save previous field if exists
                if current_field:
                    fields[current_field] = "\n".join(current_content).strip()
                    current_content = []
                
                # Start new field
                current_field = line[3:].strip()
            else:
                if current_field:
                    current_content.append(line)
        
        # Save last field
        if current_field and current_content:
            fields[current_field] = "\n".join(current_content).strip()
            
        return fields

@dataclass
class LeanFunctionFile(LeanFile):
    """Structure for Lean function implementation files"""
    
    imports: str = ""
    helper_functions: str = ""
    main_function: str = ""

@dataclass 
class LeanStructureFile(LeanFile):
    """Structure for Lean structure definition files"""
    
    imports: str = ""
    structure_definition: str = ""

@dataclass
class LeanTheoremFile(LeanFile):
    """Structure for Lean theorem files"""
    
    imports: str = ""
    helper_functions: str = ""
    comment: str = ""
    theorem_unproved: str = ""  # With sorry
    theorem_proved: Optional[str] = None  # Complete proof
    
    def generate_content(self) -> str:
        """Override to use proved theorem if available"""
        content = []
        
        # Add imports if present
        if self.imports:
            content.extend([
                "-- imports",
                self.imports,
                ""
            ])
            
        # Add helper functions if present
        if self.helper_functions:
            content.extend([
                "-- helper_functions", 
                self.helper_functions,
                ""
            ])
            
        # Add comment if present
        if self.comment:
            content.extend([
                "-- comment",
                self.comment,
                ""
            ])
            
        # Add theorem (proved version if available)
        if self.theorem_proved:
            content.extend([
                "-- theorem proved",
                self.theorem_proved,
                ""
            ])
        else:
            content.extend([
                "-- theorem unproved",
                self.theorem_unproved,
                ""
            ])
            
        return "\n".join(content) 