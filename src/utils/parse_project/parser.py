from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import yaml
import argparse
import subprocess
import json

# 默认配置模板
LAKE_MANIFEST_TEMPLATE = {
    "version": "1.1.0",
    "packagesDir": ".lake/packages",
    "packages": [],
    "lakeDir": ".lake"
}


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

@dataclass
class TableInfo:
    """表信息"""
    name: str
    description: dict  # yaml content
    table_code: Optional[str] = None  # scala code if exists
    lean_code: Optional[str] = None  # lean code if exists

@dataclass
class APIInfo:
    """API信息"""
    name: str
    message_description: dict  # message yaml content
    planner_description: dict  # planner yaml content
    planner_code: Optional[str] = None  # scala code if exists
    message_typescript: Optional[str] = None  # typescript code if exists
    message_code: Optional[str] = None  # scala message code if exists
    lean_code: Optional[str] = None  # lean code if exists

@dataclass
class ServiceInfo:
    """服务信息"""
    name: str
    apis: List[APIInfo]
    tables: List[TableInfo]
    init_code: Optional[str] = None  # Init.scala content if exists

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

    @classmethod
    def parse_project(cls, project_name: str, base_path: str, lean_base_path: str) -> 'ProjectStructure':
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
                code_path / service_name
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
    def _parse_service(service_name: str, doc_dir: Path, code_dir: Path) -> ServiceInfo:
        # 解析API
        apis = []
        api_root = doc_dir / f"{service_name}-APIRoot"
        for message_dir in api_root.glob("*Message"):
            if not message_dir.is_dir():
                continue
                
            api_name = message_dir.name.replace("Message", "")
            planner_dir = message_dir / f"{api_name}MessagePlanner"
            
            # 读取yaml文件
            message_yaml = yaml.safe_load((message_dir / f"{api_name}Message.yaml").read_text())
            planner_yaml = yaml.safe_load((planner_dir / f"{api_name}MessagePlanner.yaml").read_text())
            
            # 读取Planner代码
            planner_code = None
            planner_path = code_dir / "src/main/scala/Impl" / service_name / f"{api_name}Planner.scala"
            if planner_path.exists():
                planner_code = planner_path.read_text()
                
            # 读取TypeScript代码
            ts_code = None
            ts_path = message_dir / f"{api_name}Message.tsx"
            if ts_path.exists():
                ts_code = ts_path.read_text()
                
            # 读取Message Scala代码
            message_code = None
            message_path = code_dir / "src/main/scala/APIs" / service_name / f"{api_name}Message.scala"
            if message_path.exists():
                message_code = message_path.read_text()
                
            apis.append(APIInfo(
                name=api_name,
                message_description=message_yaml,
                planner_description=planner_yaml,
                planner_code=planner_code,
                message_typescript=ts_code,
                message_code=message_code
            ))
            
        # 解析Tables
        tables = []
        table_root = doc_dir / f"{service_name}-TableRoot"
        for table_dir in table_root.glob("*"):
            if not table_dir.is_dir():
                continue
                
            table_name = table_dir.name
            table_yaml = yaml.safe_load((table_dir / f"{table_name}.yaml").read_text())
            
            # 读取Table代码
            table_code = None
            table_scala = table_dir / f"{table_name}.scala"
            if table_scala.exists():
                table_code = table_scala.read_text()
                
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

    def init_lean(self) -> Tuple[bool, str]:
        """初始化Lean项目"""
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
            manifest_path = self.lean_project_path / "lake-manifest.json"
            manifest_content = LAKE_MANIFEST_TEMPLATE.copy()
            manifest_content["name"] = self.lean_project_name
            manifest_path.write_text(json.dumps(manifest_content, indent=2))
            
            lakefile_path = self.lean_project_path / "lakefile.lean"
            lakefile_content = LAKEFILE_TEMPLATE.replace("{{name}}", self.lean_project_name)
            lakefile_path.write_text(lakefile_content)
            
            # 4. 删除Main.lean，清空Basic.lean
            (self.lean_project_path / "Main.lean").unlink(missing_ok=True)
            self._update_basic_lean()
            
            # 5. 创建项目根文件
            root_lean_path = self.lean_project_path / f"{self.lean_project_name}.lean"
            root_lean_path.write_text(f"import {self.lean_project_name}.Basic")
            
            self._update_basic_lean()

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

    def build(self) -> Tuple[bool, str]:
        """构建Lean项目"""
        try:
            result = subprocess.run(
                ['lake', 'build'],
                cwd=self.lean_project_path,
                capture_output=True,
                text=True
            )
            success = result.returncode == 0
            message = result.stdout if success else result.stderr
            return success, message
            
        except Exception as e:
            return False, f"Build failed: {str(e)}"

    def _find_table(self, name: str) -> Optional[TableInfo]:
        """查找表"""
        for service in self.services:
            for table in service.tables:
                if table.name == name:
                    return table
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
                    lines.append(f"\n#### {api.name}")
                    
                    lines.append("\n##### Message Description")
                    lines.append("---")
                    lines.append("```yaml")
                    lines.append(yaml.dump(api.message_description, allow_unicode=True))
                    lines.append("```")
                    
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
            
            if service.tables:
                lines.append("\n### Tables")
                for table in service.tables:
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
    success, message = project.init_lean()
    print(success, message)

    # Try build
    success, message = project.build()
    print(success, message)

    # Add a table
    project.set_lean("table", "UserAuthService", "User", """
def user := "user"
""")
    
    # Try build again
    success, message = project.build()
    print(success, message)

    # Add an api
    project.set_lean("api", "UserAuthService", "UserLogin", """
import UserAuthenticationProject11.Database.User

def userLogin (name: String) : IO Unit := do
    IO.println s!\"User {name} logged in successfully.\"
""")
    
    # Try build again
    success, message = project.build()
    print(success, message)
    



if __name__ == "__main__":
    main()
