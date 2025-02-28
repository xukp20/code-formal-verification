from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any
import yaml
import argparse
import subprocess
import json
from src.utils.parse_project.types import TableInfo, APIInfo, ServiceInfo
from src.utils.lean.build_parser import parse_build_output_to_messages, parse_lean_message_details
import os
import shutil
import time
LAKEFILE_TEMPLATE = '''
import Lake
open Lake DSL

package {{name}} {
  -- add package configuration options here
}

@[default_target]
lean_lib «{{name}}» {
  -- add library configuration options here
}

'''

LAKEFILE_TEMPLATE_WITH_MATHLIB = '''
import Lake
open Lake DSL

require "leanprover-community" / "mathlib"

package {{name}} {
  -- add package configuration options here
}

@[default_target]
lean_lib «{{name}}» {
  -- add library configuration options here
}
'''

@dataclass
class LoadSettings:
    """Configuration for what content to load"""
    table_code: bool = False
    message_description: bool = False
    planner_description: bool = False
    message_typescript: bool = False
    message_code: bool = True  # Default to True for backward compatibility

@dataclass
class ProjectStructure:
    """项目结构"""
    name: str
    base_path: Path
    services: List[ServiceInfo]
    lean_base_path: Path
    lean_project_name: str
    lean_project_path: Path
    package_path: Path
    # Lean project constants
    DATABASE_DIR = "Database"
    SERVICE_DIR = "Service"
    TEST_DIR = "Test"
    BASIC_LEAN = "Basic.lean"

    def print_lean_structure(self) -> str:
        """Print the structure of Lean project files"""
        lines = []
        
        # Project root directory
        lines.append(f"{self.lean_project_path.name}/")
        
        # Project root lean file
        lines.append(f"├── {self.lean_project_name}.lean")
        
        # Package directory
        lines.append(f"└── {self.lean_project_name}/")
        
        # Basic.lean
        lines.append(f"    ├── {self.BASIC_LEAN}")
        
        # Database directory
        has_db = False
        db_lines = []
        for service in self.services:
            for table in service.tables:
                if table.lean_code:
                    if not has_db:
                        has_db = True
                    db_lines.append(f"    │   └── {table.name}.lean")
        
        if has_db:
            lines.append(f"    ├── {self.DATABASE_DIR}/")
            lines.extend(db_lines)
        
        # Service directory
        has_service = False
        for i, service in enumerate(self.services):
            has_api = any(api.lean_code for api in service.apis)
            if has_api:
                if not has_service:
                    has_service = True
                    lines.append(f"    └── {self.SERVICE_DIR}/")
                
                # Service directory
                lines.append(f"        ├── {service.name}/")
                
                # APIs
                for j, api in enumerate(service.apis):
                    if api.lean_code:
                        prefix = "        │   " if j < len(service.apis) - 1 else "        │   "
                        lines.append(f"{prefix}└── {api.name}.lean")
        
        return "\n".join(lines)

    # add loading and saving project structure as json
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base_path": str(self.base_path),
            "services": [service.to_dict() for service in self.services],
            "lean_base_path": str(self.lean_base_path),
            "lean_project_name": self.lean_project_name,
            "lean_project_path": str(self.lean_project_path),
            "package_path": str(self.package_path)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectStructure':
        return cls(
            name=data["name"],
            base_path=Path(data["base_path"]),
            services=[ServiceInfo.from_dict(service) for service in data["services"]],
            lean_base_path=Path(data["lean_base_path"]),
            lean_project_name=data["lean_project_name"],
            lean_project_path=Path(data["lean_project_path"]),
            package_path=Path(data["package_path"])
        ) 
    
    def save_project(self, path: Path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_project(cls, path: Path) -> 'ProjectStructure':
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def parse_project(cls, 
                     project_name: str, 
                     base_path: str, 
                     lean_base_path: str,
                     load_settings: LoadSettings = LoadSettings()) -> 'ProjectStructure':
        """Parse project structure with configurable loading settings"""
        base = Path(base_path)
        doc_path = base / project_name / project_name
        code_path = base / f"{project_name}Code"
        lean_project_name = (project_name[0].upper() + project_name[1:])
        lean_project_path = Path(lean_base_path) / lean_project_name
        package_path = lean_project_path / lean_project_name
        services = []
        
        # 遍历所有服务目录
        for service_dir in doc_path.glob("*Service"):
            if not service_dir.is_dir():
                continue
                
            service_name = service_dir.name
            service = cls._parse_service(
                service_name,
                service_dir,
                code_path / service_name,
                load_settings
            )
            services.append(service)
            
        return cls(
            name=project_name,
            base_path=base,
            services=services,
            lean_base_path=lean_base_path,
            lean_project_name=lean_project_name,
            lean_project_path=lean_project_path,
            package_path=package_path
        )
    
    @staticmethod
    def _parse_service(service_name: str, 
                      doc_dir: Path, 
                      code_dir: Path,
                      load_settings: LoadSettings) -> ServiceInfo:
        """Parse service with configurable loading settings"""
        # 解析API
        apis = []
        api_root = doc_dir / f"{service_name}-APIRoot"
        for message_dir in api_root.glob("*Message"):
            if not message_dir.is_dir():
                continue
                
            api_name = message_dir.name.replace("Message", "")
            planner_dir = message_dir / f"{api_name}MessagePlanner"
            
            # Required: Planner code
            planner_code = None
            planner_path = code_dir / "src/main/scala/Impl" / service_name / f"{api_name}MessagePlanner.scala"
            if planner_path.exists():
                planner_code = planner_path.read_text()
            else:
                raise ValueError(f"Planner code not found for API {api_name} in service {service_name}")
            
            # Optional components based on settings
            message_description = None
            planner_description = None
            message_typescript = None
            message_code = None
            
            # Load message description if configured
            if load_settings.message_description:
                message_yaml_path = message_dir / f"{api_name}Message.yaml"
                if message_yaml_path.exists():
                    message_description = yaml.safe_load(message_yaml_path.read_text())
                else:
                    print(f"Warning: Message description not found for API {api_name}")
            
            # Load planner description if configured
            if load_settings.planner_description:
                planner_yaml_path = planner_dir / f"{api_name}MessagePlanner.yaml"
                if planner_yaml_path.exists():
                    planner_description = yaml.safe_load(planner_yaml_path.read_text())
                else:
                    print(f"Warning: Planner description not found for API {api_name}")
            
            # Load TypeScript code if configured
            if load_settings.message_typescript:
                ts_path = message_dir / f"{api_name}Message.tsx"
                if ts_path.exists():
                    message_typescript = ts_path.read_text()
                else:
                    print(f"Warning: TypeScript code not found for API {api_name}")
            
            # Load Message code if configured
            if load_settings.message_code:
                message_path = code_dir / "src/main/scala/APIs" / service_name / f"{api_name}Message.scala"
                if message_path.exists():
                    message_code = message_path.read_text()
                else:
                    print(f"Warning: Message code not found for API {api_name}")
                
            apis.append(APIInfo(
                name=api_name,
                message_description=message_description,
                planner_description=planner_description,
                planner_code=planner_code,
                message_typescript=message_typescript,
                message_code=message_code
            ))
            
        # 解析Tables
        tables = []
        table_root = doc_dir / f"{service_name}-TableRoot"
        for table_dir in table_root.glob("*"):
            if not table_dir.is_dir():
                continue
                
            table_name = table_dir.name
            
            # Required: Table description
            table_yaml = yaml.safe_load((table_dir / f"{table_name}.yaml").read_text())
            
            # Optional: Table code
            table_code = None
            if load_settings.table_code:
                table_scala = table_dir / f"{table_name}.scala"
                if table_scala.exists():
                    table_code = table_scala.read_text()
                else:
                    print(f"Warning: Table code not found for table {table_name}")
                
            tables.append(TableInfo(
                name=table_name,
                description=table_yaml,
                table_code=table_code
            ))
            
        # 读取Init代码
        init_code = None
        init_path = code_dir / "src/main/scala/Process/Init.scala"
        if init_path.exists():
            init_code = init_path.read_text()
            
        return ServiceInfo(
            name=service_name,
            apis=apis,
            tables=tables,
            init_code=init_code
        )

    def init_lean(self, add_mathlib: bool = False) -> Tuple[bool, str]:
        """初始化Lean项目"""
        # create the lean base path if not exists
        Path(self.lean_base_path).mkdir(parents=True, exist_ok=True)
        
        try:
            # 1. 使用lake创建新项目
            result = subprocess.run(
                ['lake', 'new', self.lean_project_name],
                cwd=self.lean_base_path,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return False, f"Lake init failed: {result.stderr}"
            
            self.package_path.mkdir(parents=True, exist_ok=True)
            
            # 2. 创建必要的目录结构
            for dir_name in [self.DATABASE_DIR, self.SERVICE_DIR, self.TEST_DIR]:
                (self.package_path / dir_name).mkdir(parents=True, exist_ok=True)

            # 3. 修改配置文件
            # manifest_path = self.lean_project_path / "lake-manifest.json"
            # manifest_content = LAKE_MANIFEST_TEMPLATE.copy()
            # manifest_content["name"] = self.lean_project_name
            # manifest_path.write_text(json.dumps(manifest_content, indent=2))
            
            lakefile_path = self.lean_project_path / "lakefile.lean"
            if add_mathlib:
                lakefile_content = LAKEFILE_TEMPLATE_WITH_MATHLIB.replace("{{name}}", self.lean_project_name)
            else:
                lakefile_content = LAKEFILE_TEMPLATE.replace("{{name}}", self.lean_project_name)
        
            lakefile_path.write_text(lakefile_content)
            
            # 4. 删除Main.lean，清空Basic.lean
            (self.lean_project_path / "Main.lean").unlink(missing_ok=True)
            self._update_basic_lean()
            
            # 5. 创建项目根文件
            root_lean_path = self.lean_project_path / f"{self.lean_project_name}.lean"
            root_lean_path.write_text(f"import {self.lean_project_name}.Basic")
            
            self._update_basic_lean()

            # update and build
            self._try_copy_package()

            success, message = self._run_lake_update()
            if not success:
                return False, message
            
            success, message = self._run_lake_build()
            if not success:
                return False, message

            return True, "Successfully initialized Lean project"
            
        except Exception as e:
            print(e)
            return False, f"Failed to initialize Lean project: {str(e)}"

    def set_lean(self, kind: str, service_name: str, name: str, code: str) -> None:
        """设置Lean代码"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table:
                raise ValueError(f"Table {name} not found")
            table.lean_code = code
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            api.lean_code = code
        else:
            raise ValueError(f"Unknown kind: {kind}")
            
        # 写入文件
        file_path = self.get_lean_path(kind, service_name, name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code)
        
        # 更新Basic.lean
        self._update_basic_lean()

    def get_lean(self, kind: str, service_name: str, name: str) -> str:
        """获取Lean代码"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table:
                raise ValueError(f"Table {name} not found")
            if not table.lean_code:
                raise ValueError(f"No Lean code for table {name}")
            return table.lean_code
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            if not api.lean_code:
                raise ValueError(f"No Lean code for API {name}")
            return api.lean_code
        raise ValueError(f"Unknown kind: {kind}")
    
    def del_lean(self, kind: str, service_name: str, name: str) -> None:
        """删除Lean代码"""
        if kind.lower() == "table":
            service, table = self._find_table_with_service(name)
            if not service or not table:
                raise ValueError(f"Table {name} not found")
            table.lean_code = None
        elif kind.lower() == "api":
            service, api = self._find_api_with_service(name, service_name=service_name)
            if not service or not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            api.lean_code = None
        else:
            raise ValueError(f"Unknown kind: {kind}")
        
        # 删除文件
        file_path = self.get_lean_path(kind, service_name, name)
        if file_path.exists():
            file_path.unlink()
        
        # 更新Basic.lean
        self._update_basic_lean()

    def get_lean_path(self, kind: str, service_name: str, name: str) -> Path:
        """获取Lean文件路径"""
        if kind.lower() == "table":
            if not self._find_table(name):
                raise ValueError(f"Table {name} not found")
            return self.package_path / self.DATABASE_DIR / f"{name}.lean"
        elif kind.lower() == "api":
            if not self._find_api(service_name, name):
                raise ValueError(f"API {name} not found in service {service_name}")
            return self.package_path / self.SERVICE_DIR / service_name / f"{name}.lean"
        raise ValueError(f"Unknown kind: {kind}")
    
    def get_lean_import_path(self, kind: str, service_name: str, name: str) -> Path:
        """获取Lean导入路径"""
        if kind.lower() == "table":
            return self.lean_project_name + ".Database." + name
        elif kind.lower() == "api":
            return self.lean_project_name + ".Service." + service_name + "." + name
        raise ValueError(f"Unknown kind: {kind}")

    def _get_error_context(self, relative_path: str, line: int, column: int) -> str:
        """Get context lines around an error
        
        Args:
            relative_path: Path relative to project root
            line: Line number (1-based)
            column: Column number (1-based)
            
        Returns:
            String containing the context lines with error marked
        """
        file_path = self.lean_project_path / relative_path
        
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                
            # Get context lines (line numbers are 1-based)
            line_idx = line - 1
            context_lines = []
            
            # Add previous line if exists
            if line_idx > 0:
                context_lines.append(lines[line_idx - 1].rstrip())
                
            # Add error line with marker
            error_line = lines[line_idx].rstrip()
            marked_line = (
                error_line[:column-1] + 
                "[error]" + 
                error_line[column-1:]
            )
            context_lines.append(marked_line)
            
            # Add next line if exists
            if line_idx < len(lines) - 1:
                context_lines.append(lines[line_idx + 1].rstrip())
                
            return "\n".join(context_lines)
            
        except Exception as e:
            return f"Failed to get context: {str(e)}"

    def _format_error_message(self, 
                            error_info: Dict[str, str], 
                            add_context: bool = False) -> str:
        """Format error information as markdown
        
        Args:
            error_info: Dict containing error details
            add_context: Whether to include file context
            
        Returns:
            Formatted markdown string
        """
        # Convert file path to import path
        file_path = error_info["file"]
        import_path = file_path.replace("/", ".").replace(".lean", "")
        
        if add_context:
            return f"""### File Path
{import_path}

### Context ([error] marks the error position)
```lean
{self._get_error_context(file_path, error_info["line"], error_info["column"])}
```

### Content
{error_info["content"]}"""
        else:
            return f"""### File Path
{import_path}

### Line: Column
{error_info["line"]}: {error_info["column"]}

### Content
{error_info["content"]}"""

    def _try_copy_package(self) -> Tuple[bool, str]:
        """Try to copy package to lean_project"""
        # load package_path from env
        package_path = os.getenv("PACKAGE_PATH")
        if package_path:
            start_time = time.time()
            print(f"Copying package to {self.lean_project_path / '.lake'}")
            # mkdir .lake in the lean project path
            (self.lean_project_path / ".lake").mkdir(parents=True, exist_ok=True)
            # package_path is the dir "packages", copy it with the content to .lake
            shutil.copytree(package_path, self.lean_project_path / ".lake" / "packages")
            end_time = time.time()
            print(f"Copying package to {self.lean_project_path / '.lake'} took {end_time - start_time} seconds")
        
    def _run_lake_update(self) -> Tuple[bool, str]:
        """Run Lake update and return success and output"""
        try: 
            # set proxy
            env = os.environ.copy()
            
            start_time = time.time()
            result = subprocess.run(
                ['lake', 'update'],
                cwd=self.lean_project_path,
                capture_output=True,
                text=True,
                env=env
            )
            success = result.returncode == 0
            message = result.stdout
            end_time = time.time()
            print(f"Lake update took {end_time - start_time} seconds")
            print("Lake update output:")
            print(message)
            return success, message
            
        except Exception as e:
            return False, f"Update failed: {str(e)}"

    def _run_lake_build(self) -> Tuple[bool, str]:
        """Run Lake build and return success and output"""
        try:
            # set proxy
            env = os.environ.copy()

            result = subprocess.run(
                ['lake', 'build'],
                cwd=self.lean_project_path,
                capture_output=True,
                text=True,
                env=env
            )
            success = result.returncode == 0
            message = result.stdout
            return success, message
            
        except Exception as e:
            return False, f"Build failed: {str(e)}"
        
    def build(self, 
              parse: bool = False, 
              only_errors: bool = False,
              add_context: bool = False,
              only_first: bool = False) -> Tuple[bool, str]:
        """Build the Lean project
        
        Args:
            parse: Whether to parse Lake output
            only_errors: Only include errors in parsed output
            add_context: Include file context in error messages
            
        Returns:
            Tuple of (success, message)
        """
        # Run Lake build
        success, output = self._run_lake_build()
        
        if not parse:
            return success, output
            
        # Parse Lake output
        messages = parse_build_output_to_messages(output)
        details = parse_lean_message_details(messages, only_errors=only_errors)
        if only_first:
            details = details[:1]
        
        if not details:
            return success, "No errors or warnings found" if success else "Build failed with no parseable errors"
            
        # Format messages
        formatted_messages = []
        for detail in details:
            formatted_messages.append(
                self._format_error_message(detail, add_context)
            )
            
        return success, "\n\n".join(formatted_messages)

    def _find_table(self, name: str) -> Optional[TableInfo]:
        """查找表"""
        for service in self.services:
            for table in service.tables:
                if table.name == name:
                    return table
        return None
    
    def _find_table_with_service(self, name: str) -> Optional[Tuple[ServiceInfo, TableInfo]]:
        """查找表及其服务"""
        for service in self.services:
            for table in service.tables:
                if table.name == name:
                    return service, table
        return None
    
    def _find_api_with_service(self, api_name: str, service_name: str=None) -> Optional[Tuple[ServiceInfo, APIInfo]]:
        """查找API及其服务"""
        for service in self.services:
            if service_name and service.name != service_name:
                continue
            for api in service.apis:
                if api.name == api_name:
                    return service, api
                
        return None

    def _find_api(self, service_name: str, api_name: str) -> Optional[APIInfo]:
        """查找API"""
        for service in self.services:
            if service.name == service_name:
                for api in service.apis:
                    if api.name == api_name:
                        return api
        return None

    def _update_basic_lean(self):
        """更新Basic.lean文件"""
        imports = []
        
        # 添加数据库导入
        for service in self.services:
            for table in service.tables:
                if table.lean_code:
                    imports.append(f"import {self.lean_project_name}.{self.DATABASE_DIR}.{table.name}")
        
        # 添加API导入
        for service in self.services:
            for api in service.apis:
                if api.lean_code:
                    imports.append(f"import {self.lean_project_name}.{self.SERVICE_DIR}.{service.name}.{api.name}")
        
        # 写入Basic.lean
        basic_path = self.package_path / self.BASIC_LEAN
        basic_path.write_text("\n".join(imports))

    def _api_to_markdown(self, service: ServiceInfo, api: APIInfo, include_description: bool = True) -> str:
        """将API转换为markdown格式"""
        lines = []
        lines.append(f"\n#### {api.name}")
                    
        if include_description and api.message_description:
            lines.append("\n##### Message Description")
            lines.append("---")
            lines.append("```yaml")
            lines.append(yaml.dump(api.message_description, allow_unicode=True))
            lines.append("```")
        
        if include_description and api.planner_description:
            lines.append("\n##### Planner Description")
            lines.append("---")
            lines.append("```yaml")
            lines.append(yaml.dump(api.planner_description, allow_unicode=True))
            lines.append("```")
        
        if api.planner_code:
            lines.append("\n##### Planner Code")
            lines.append("---")
            lines.append("```scala")
            lines.append(api.planner_code)
            lines.append("```")
        
        if api.message_code:
            lines.append("\n##### Message Code")
            lines.append("---")
            lines.append("```scala")
            lines.append(api.message_code)
            lines.append("```")
        
        if api.message_typescript:
            lines.append("\n##### TypeScript Message")
            lines.append("---")
            lines.append("```typescript")
            lines.append(api.message_typescript)
            lines.append("```")
            
        if api.lean_code:
            lines.append("\n##### Lean Path")
            lines.append("---")
            lines.append("```lean")
            lines.append(self.get_lean_import_path("api", service.name, api.name))
            lines.append("```")
            lines.append("\n##### Lean Code")
            lines.append("---")
            lines.append("```lean")
            lines.append(api.lean_code)
            lines.append("```")
        
        
        return "\n".join(lines)

    def _table_to_markdown(self, service: ServiceInfo, table: TableInfo) -> str:
        """将表转换为markdown格式"""
        lines = []
        lines.append(f"\n#### {table.name}")
                    
        lines.append("\n##### Table Description")
        lines.append("---")
        lines.append("```yaml")
        lines.append(yaml.dump(table.description, allow_unicode=True))
        lines.append("```")
        
        if table.table_code:
            lines.append("\n##### Table Code")
            lines.append("---")
            lines.append("```scala")
            lines.append(table.table_code)
            lines.append("```")
            
        if table.lean_code:
            lines.append("\n##### Lean Path")
            lines.append("---")
            lines.append("```lean")
            lines.append(self.get_lean_import_path("table", service.name, table.name))
            lines.append("```")
            lines.append("\n##### Lean Code")
            lines.append("---")
            lines.append("```lean")
            lines.append(table.lean_code)
            lines.append("```")

        return "\n".join(lines)
    

    def to_markdown(self) -> str:
        """Convert the project structure to markdown format"""
        lines = [f"# Project: {self.name}\n"]
        
        for service in self.services:
            lines.append(f"## Service: {service.name}")
            
            if service.init_code:
                lines.append("\n### Init Code")
                lines.append("```scala")
                lines.append(service.init_code)
                lines.append("```\n")
            
            if service.apis:
                lines.append("\n### APIs")
                for api in service.apis:
                    lines.append(self._api_to_markdown(service, api))
                             
            if service.tables:
                lines.append("\n### Tables")
                for table in service.tables:
                    lines.append(self._table_to_markdown(service, table))

            lines.append("\n---\n")  # Service separator
            
        return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description='Parse project structure')
    parser.add_argument('--base_path', 
                      default='source_code/UserAuthenticationProject11',
                      help='Base path containing both doc and code directories')
    parser.add_argument('--project_name', 
                      default='UserAuthenticationProject11',
                      help='Name of the project')
    parser.add_argument('--lean_base_path', 
                      default='lean_project',
                      help='Base path containing lean project')
    
    args = parser.parse_args()
    
    project = ProjectStructure.parse_project(args.project_name, args.base_path, args.lean_base_path)
    
    # Generate markdown output
    markdown_output = project.to_markdown()
    
    # Save to file
    output_path = Path(args.base_path) / f"{args.project_name}_structure.md"
    output_path.write_text(markdown_output, encoding='utf-8')
    
    print(f"Project structure has been saved to: {output_path}")
    
    # Also print basic structure info
    print(f"\nProject: {project.name}")
    for service in project.services:
        print(f"\nService: {service.name}")
        print(f"APIs: {len(service.apis)}")
        print(f"Tables: {len(service.tables)}")
        print("Has Init code:", service.init_code is not None)

    # Try init
    success, message = project.init_lean(add_mathlib=True)
    print(success, message)

    # Try build
    # success, message = project.build()
    # print(success, message)

    # Try get error context
    # success, message = project.build(parse=True, add_context=True, only_errors=True)
    # print(success, message)

#     # Add a table
#     project.set_lean("table", "UserAuthService", "User", """
# def user := "user"
# """)
    
#     # Try build again
#     success, message = project.build()
#     print(success, message)

#     print("Project structure:")
#     print(project.print_lean_structure())

#     # Add an api
#     project.set_lean("api", "UserAuthService", "UserLogin", """
# import UserAuthenticationProject11.Database.User

# def userLogin (name: String) : IO Unit := do
#     IO.println s!\"User {name} logged in successfully.\"
# """)
    
#     # Try build again
#     success, message = project.build()
#     print(success, message)

#     print("Project structure:")
#     print(project.print_lean_structure())

#     # Try get table code, path
#     print("Testing get table code, path")
#     table_code = project.get_lean("table", "UserAuthService", "User")
#     print(table_code)   
#     table_path = project.get_lean_path("table", "UserAuthService", "User")
#     print(table_path)
#     table_import_path = project.get_lean_import_path("table", "UserAuthService", "User")
#     print(table_import_path)

#     print("Testing get api code, path")
#     api_code = project.get_lean("api", "UserAuthService", "UserLogin")
#     print(api_code)
#     api_path = project.get_lean_path("api", "UserAuthService", "UserLogin")
#     print(api_path)
#     api_import_path = project.get_lean_import_path("api", "UserAuthService", "UserLogin")
#     print(api_import_path)

#     # save md file
#     output_path = Path(args.base_path) / f"{args.project_name}_fake_lean_code.md"
#     output_path.write_text(project.to_markdown(), encoding='utf-8')

#     # save project
#     project.save_project(Path(args.base_path) / f"{args.project_name}_fake_lean_code.json")

#     # load project
#     project = ProjectStructure.load_project(Path(args.base_path) / f"{args.project_name}_fake_lean_code.json")
#     print(project)

if __name__ == "__main__":
    main()
