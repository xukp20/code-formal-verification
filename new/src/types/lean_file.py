from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.types.lean_structure import LeanProjectStructure

@dataclass
class LeanFile:
    """Base class for Lean file structures"""
    
    # Relative path from Lean project root
    relative_path: List[str]
    _backup: Optional[Dict[str, Any]] = field(default=None, repr=False)
    
    def set_fields(self, fields: Dict[str, Any]) -> None:
        """Set fields from dictionary, ignoring relative_path"""
        for field_name, value in fields.items():
            if field_name != 'relative_path' and hasattr(self, field_name):
                setattr(self, field_name, value)
                
    def backup(self) -> None:
        """Create backup of current field values"""
        self._backup = {
            k: v for k, v in self.__dict__.items() 
            if k != 'relative_path' and k != '_backup'
        }
        
    def restore(self) -> None:
        """Restore field values from backup"""
        if self._backup is None:
            raise ValueError("No backup exists")
        self.set_fields(self._backup)

    @staticmethod
    def get_structure() -> str:
        """Get the structure template for this Lean file type"""
        return """
-- imports
<import statements>

-- <other sections based on file type>
<section content>
"""

    def generate_content(self) -> str:
        """Generate complete file content by concatenating all non-empty fields
        
        Returns:
            Complete file content with field comments
        """
        content = []
        
        # Get all fields except relative_path
        fields = {k: v for k, v in self.__dict__.items() 
                 if k != 'relative_path' and k != '_backup' and v is not None and v != ''}
        
        # Put imports at the beginning
        if self.imports:
            content.extend([
                "-- imports",
                self.imports,
                ""
            ])

        # Add namespace
        content.extend([
            "-- namespace",
            self.get_namespace(),
            ""
        ])
        
        # Add each field with comment
        for field_name, field_value in fields.items():
            if field_name != "imports":
                content.extend([
                    f"-- {field_name}",
                    field_value,
                    ""  # Empty line after each field
                ])

        # Add end namespace
        content.extend([
            "-- end namespace",
            self.get_end_namespace(),
        ])
            
        return "\n".join(content)
    
    def get_namespace(self) -> str:
        """Get the namespace for the current file"""
        return "namespace " + LeanProjectStructure.to_import_path(self.relative_path)

    def get_end_namespace(self) -> str:
        """Get the end namespace for the current file"""
        return "end " + LeanProjectStructure.to_import_path(self.relative_path)
    
    def to_markdown(self, add_import_path: bool = True) -> str:
        """Convert Lean file to markdown format"""
        content = "```lean\n" + self.generate_content() + "\n```"
        if add_import_path:
            import_path = LeanProjectStructure.to_import_path(self.relative_path)
            content = "Import path: " + import_path + "\n" + content
        return content

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

    @staticmethod
    def get_structure() -> str:
        return """
-- imports
<imports needed, including import and open commands of other files>

-- namespace
namespace <current file path>  -- This is automatically generated

-- helper_functions
def helperFunction (x : Type) : Type := 
  <implementation>

-- main_function
def mainFunction (x : Type) : Type :=
  <implementation>

-- end namespace
end <current file path>  -- This is automatically generated
"""

@dataclass 
class LeanStructureFile(LeanFile):
    """Structure for Lean structure definition files"""
    
    imports: str = ""
    structure_definition: str = ""

    @staticmethod
    def get_structure() -> str:
        return """
-- imports
<imports needed, including import and open commands of other files>

-- namespace
namespace <current file path>  -- This is automatically generated

-- structure_definition
structure NestedStructure where
  field1 : Type
  field2 : Type

structure MyStructure where
  field1 : NestedStructure
  field2 : Type

-- end namespace
end <current file path>  -- This is automatically generated
"""

@dataclass
class LeanTheoremFile(LeanFile):
    """Structure for Lean theorem files"""
    
    imports: str = ""
    helper_functions: str = ""
    comment: str = ""
    theorem_unproved: str = ""  # With sorry
    theorem_proved: Optional[str] = None  # Complete proof
    
    @staticmethod
    def get_structure(proved: bool = True) -> str:
        base = """
-- imports
<imports needed, including import and open commands of other files>

-- namespace
namespace <current file path>  -- This is automatically generated

-- helper_functions
def helperFunction (x : Type) : Type := 
  <implementation>

-- comment
/- Theorem description and explanation -/
"""
        if proved:
            base += """
-- theorem_proved
theorem myTheorem (x : Type) : Type := by
  <complete proof>

-- end namespace
end <current file path>  -- This is automatically generated
"""
        else:
            base += """
-- theorem_unproved
theorem myTheorem (x : Type) : Type := by
  sorry

-- end namespace
end <current file path>  -- This is automatically generated
""" 
        return base
    
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

        # Add namespace
        content.extend([
            "-- namespace",
            self.get_namespace(),
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
        elif self.theorem_unproved:
            content.extend([
                "-- theorem unproved",
                self.theorem_unproved,
                ""
            ])
        
        # Add end namespace
        content.extend([
            "-- end namespace",
            self.get_end_namespace(),
        ])
            
        return "\n".join(content) 