from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from dataclasses import dataclass
import argparse

from src.types.project import ProjectStructure


@dataclass
class APIMetrics:
    """Metrics for a single API"""
    api_name: str
    service_name: str
    project_name: str
    api_code_length: int
    num_requirements: int
    num_formalized: int
    num_proven: int
    function_loc: int
    avg_theorem_length: float
    
    @property
    def formalization_success_rate(self) -> float:
        """Formalization success rate: formalized / requirements"""
        return self.num_formalized / self.num_requirements if self.num_requirements > 0 else 0.0
    
    @property
    def end_to_end_success_rate(self) -> float:
        """End-to-end success rate: proven / requirements"""
        return self.num_proven / self.num_requirements if self.num_requirements > 0 else 0.0


@dataclass
class ServiceMetrics:
    """Metrics for a service"""
    service_name: str
    project_name: str
    num_apis: int
    avg_formalization_success_rate: float
    avg_end_to_end_success_rate: float


@dataclass
class ProjectMetrics:
    """Metrics for a project"""
    project_name: str
    num_apis: int
    avg_formalization_success_rate: float
    avg_end_to_end_success_rate: float


def count_lines(code: str) -> int:
    """Count non-empty lines in code"""
    if not code:
        return 0
    return len([line for line in code.split('\n') if line.strip()])


def count_tokens(text: str) -> int:
    """Count tokens (whitespace-separated words) in text"""
    if not text:
        return 0
    return len(text.split())


def extract_theorem_content_without_proof(theorem_content: str) -> str:
    """Extract theorem statement without proof from Lean theorem content"""
    if not theorem_content:
        return ""
    
    lines = theorem_content.split('\n')
    theorem_lines = []
    in_proof = False
    
    for line in lines:
        stripped = line.strip()
        # Start of proof is usually "by" or ":="
        if ' by ' in stripped or stripped.endswith(' by') or ' := ' in stripped:
            # Include the line up to the proof start
            if ' by ' in stripped:
                theorem_lines.append(stripped.split(' by ')[0] + ' by')
            elif stripped.endswith(' by'):
                theorem_lines.append(stripped)
            elif ' := ' in stripped:
                theorem_lines.append(stripped.split(' := ')[0])
            in_proof = True
            break
        elif not in_proof:
            theorem_lines.append(stripped)
    
    return ' '.join(theorem_lines)


def extract_proof_content(theorem_content: str) -> str:
    """Extract proof content from Lean theorem content"""
    if not theorem_content:
        return ""
    
    lines = theorem_content.split('\n')
    proof_lines = []
    in_proof = False
    
    for line in lines:
        stripped = line.strip()
        if in_proof:
            proof_lines.append(stripped)
        elif ' by ' in stripped:
            # Extract everything after "by"
            proof_part = stripped.split(' by ', 1)[1]
            if proof_part.strip():
                proof_lines.append(proof_part.strip())
            in_proof = True
        elif stripped.endswith(' by'):
            in_proof = True
        elif ' := ' in stripped:
            # Extract everything after ":="
            proof_part = stripped.split(' := ', 1)[1]
            if proof_part.strip():
                proof_lines.append(proof_part.strip())
            in_proof = True
    
    return ' '.join(proof_lines)


def extract_api_metrics(project: ProjectStructure) -> List[APIMetrics]:
    """Extract metrics for all APIs in a project"""
    api_metrics = []
    
    print(f"DEBUG: Extracting metrics from project '{project.name}' with {len(project.services)} services")
    
    for service in project.services:
        print(f"DEBUG: Processing service '{service.name}' with {len(service.apis)} APIs")
        for api in service.apis:
            # API code length from planner_code
            api_code_length = count_lines(api.planner_code) if api.planner_code else 0
            
            # Number of requirements (total theorems)
            num_requirements = len(api.theorems)
            
            # Number of formalized (theorems with theorem object)
            num_formalized = sum(1 for thm in api.theorems if thm.theorem is not None)
            
            # Number of proven (theorems with proof)
            num_proven = sum(1 for thm in api.theorems 
                           if thm.theorem is not None and thm.theorem.theorem_proved is not None)
            
            # Function lines of code
            function_loc = 0
            if api.lean_function and api.lean_function.main_function:
                function_loc = count_lines(api.lean_function.main_function)
            
            # Average theorem length (tokens in theorem statement without proof)
            theorem_lengths = []
            for thm in api.theorems:
                if thm.theorem and thm.theorem.theorem_unproved:
                    theorem_content = extract_theorem_content_without_proof(thm.theorem.theorem_unproved)
                    theorem_lengths.append(count_tokens(theorem_content))
                elif thm.theorem and thm.theorem.theorem_proved:
                    theorem_content = extract_theorem_content_without_proof(thm.theorem.theorem_proved)
                    theorem_lengths.append(count_tokens(theorem_content))
            
            avg_theorem_length = np.mean(theorem_lengths) if theorem_lengths else 0.0
            
            metrics = APIMetrics(
                api_name=api.name or "Unknown",
                service_name=service.name or "Unknown",
                project_name=project.name or "Unknown",
                api_code_length=api_code_length,
                num_requirements=num_requirements,
                num_formalized=num_formalized,
                num_proven=num_proven,
                function_loc=function_loc,
                avg_theorem_length=avg_theorem_length
            )
            
            print(f"DEBUG: API '{api.name}' in service '{service.name}': {num_requirements} requirements, {num_proven} proven")
            
            # Only include APIs that have requirements
            if num_requirements > 0:
                api_metrics.append(metrics)
            else:
                print(f"DEBUG: Skipping API '{api.name}' in service '{service.name}' - no requirements")
    
    return api_metrics


def extract_service_metrics(api_metrics: List[APIMetrics]) -> List[ServiceMetrics]:
    """Extract service-level metrics from API metrics"""
    service_data = {}
    
    print(f"DEBUG: Processing {len(api_metrics)} APIs for service metrics")
    
    for api in api_metrics:
        key = (api.service_name, api.project_name)
        if key not in service_data:
            service_data[key] = []
            print(f"DEBUG: Found new service - {api.project_name}:{api.service_name}")
        service_data[key].append(api)
    
    print(f"DEBUG: Total unique services found: {len(service_data)}")
    for (service_name, project_name) in service_data.keys():
        print(f"DEBUG: Service - {project_name}:{service_name} has {len(service_data[(service_name, project_name)])} APIs")
    
    service_metrics = []
    for (service_name, project_name), apis in service_data.items():
        num_apis = len(apis)
        
        # Calculate accuracy over theorems, not APIs
        total_theorems = sum(api.num_requirements for api in apis)
        total_formalized = sum(api.num_formalized for api in apis)
        total_proven = sum(api.num_proven for api in apis)
        
        avg_formalization = total_formalized / total_theorems if total_theorems > 0 else 0.0
        avg_end_to_end = total_proven / total_theorems if total_theorems > 0 else 0.0
        
        print(f"DEBUG: {project_name}:{service_name} - APIs: {num_apis}, Theorems: {total_theorems}, Proven: {total_proven}, Success Rate: {avg_end_to_end:.3f}")
        
        service_metrics.append(ServiceMetrics(
            service_name=service_name,
            project_name=project_name,
            num_apis=num_apis,
            avg_formalization_success_rate=avg_formalization,
            avg_end_to_end_success_rate=avg_end_to_end
        ))
    
    return service_metrics


def extract_project_metrics(api_metrics: List[APIMetrics]) -> List[ProjectMetrics]:
    """Extract project-level metrics from API metrics"""
    project_data = {}
    
    for api in api_metrics:
        if api.project_name not in project_data:
            project_data[api.project_name] = []
        project_data[api.project_name].append(api)
    
    project_metrics = []
    for project_name, apis in project_data.items():
        num_apis = len(apis)
        
        # Calculate accuracy over theorems, not APIs
        total_theorems = sum(api.num_requirements for api in apis)
        total_formalized = sum(api.num_formalized for api in apis)
        total_proven = sum(api.num_proven for api in apis)
        
        avg_formalization = total_formalized / total_theorems if total_theorems > 0 else 0.0
        avg_end_to_end = total_proven / total_theorems if total_theorems > 0 else 0.0
        
        project_metrics.append(ProjectMetrics(
            project_name=project_name,
            num_apis=num_apis,
            avg_formalization_success_rate=avg_formalization,
            avg_end_to_end_success_rate=avg_end_to_end
        ))
    
    return project_metrics


def plot_api_complexity_vs_requirements(api_metrics: List[APIMetrics], output_path: Path):
    """Plot API code length vs number of requirements"""
    plt.figure(figsize=(10, 6))
    
    x = [api.api_code_length for api in api_metrics]
    y = [api.num_requirements for api in api_metrics]
    
    plt.scatter(x, y, alpha=0.6, s=50)
    plt.xlabel('API Code Length (Lines)')
    plt.ylabel('Number of Requirements')
    plt.title('API Code Length vs Number of Requirements')
    plt.grid(True, alpha=0.3)
    
    # Add trend line
    if len(x) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        plt.plot(x, p(x), "r--", alpha=0.8, linewidth=2)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_api_complexity_vs_function_loc(api_metrics: List[APIMetrics], output_path: Path):
    """Plot API code length vs formalized function lines of code"""
    plt.figure(figsize=(10, 6))
    
    x = [api.api_code_length for api in api_metrics]
    y = [api.function_loc for api in api_metrics]
    
    plt.scatter(x, y, alpha=0.6, s=50)
    plt.xlabel('API Code Length (Lines)')
    plt.ylabel('Formalized Function Lines of Code')
    plt.title('API Code Length vs Formalized Function Size')
    plt.grid(True, alpha=0.3)
    
    # Add trend line
    if len(x) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        plt.plot(x, p(x), "r--", alpha=0.8, linewidth=2)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_api_complexity_vs_theorem_length(api_metrics: List[APIMetrics], output_path: Path):
    """Plot API code length vs average theorem length"""
    plt.figure(figsize=(10, 6))
    
    # Filter out APIs with zero theorem length
    filtered_metrics = [api for api in api_metrics if api.avg_theorem_length > 0]
    
    x = [api.api_code_length for api in filtered_metrics]
    y = [api.avg_theorem_length for api in filtered_metrics]
    
    plt.scatter(x, y, alpha=0.6, s=50)
    plt.xlabel('API Code Length (Lines)')
    plt.ylabel('Average Theorem Length (Tokens)')
    plt.title('API Code Length vs Average Theorem Length')
    plt.grid(True, alpha=0.3)
    
    # Add trend line
    if len(x) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        plt.plot(x, p(x), "r--", alpha=0.8, linewidth=2)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_api_complexity_vs_formalization_rate(api_metrics: List[APIMetrics], output_path: Path):
    """Plot API code length vs formalization success rate"""
    plt.figure(figsize=(10, 6))
    
    x = [api.api_code_length for api in api_metrics]
    y = [api.formalization_success_rate for api in api_metrics]
    
    plt.scatter(x, y, alpha=0.6, s=50)
    plt.xlabel('API Code Length (Lines)')
    plt.ylabel('Formalization Success Rate')
    plt.title('API Code Length vs Formalization Success Rate')
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 1.05)
    
    # Add trend line
    if len(x) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        plt.plot(x, p(x), "r--", alpha=0.8, linewidth=2)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_api_complexity_vs_proof_rate(api_metrics: List[APIMetrics], output_path: Path):
    """Plot API code length vs end-to-end success rate"""
    plt.figure(figsize=(10, 6))
    
    x = [api.api_code_length for api in api_metrics]
    y = [api.end_to_end_success_rate for api in api_metrics]
    
    plt.scatter(x, y, alpha=0.6, s=50)
    plt.xlabel('API Code Length (Lines)')
    plt.ylabel('End-to-End Success Rate')
    plt.title('API Code Length vs End-to-End Success Rate')
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 1.05)
    
    # Add trend line
    if len(x) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        plt.plot(x, p(x), "r--", alpha=0.8, linewidth=2)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_requirements_vs_proven(api_metrics: List[APIMetrics], output_path: Path):
    """Plot number of requirements vs number of proven theorems"""
    plt.figure(figsize=(10, 6))
    
    x = [api.num_requirements for api in api_metrics]
    y = [api.num_proven for api in api_metrics]
    
    plt.scatter(x, y, alpha=0.6, s=50)
    plt.xlabel('Number of Requirements')
    plt.ylabel('Number of Proven Theorems')
    plt.title('Requirements vs Proven Theorems')
    plt.grid(True, alpha=0.3)
    
    # Add diagonal line for perfect success
    max_val = max(max(x), max(y)) if x and y else 0
    plt.plot([0, max_val], [0, max_val], 'r--', alpha=0.5, label='Perfect Success Line')
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_service_complexity_vs_success_rate(service_metrics: List[ServiceMetrics], output_path: Path):
    """Plot service API count vs average end-to-end success rate"""
    plt.figure(figsize=(14, 6))
    
    # Sort by API count
    sorted_metrics = sorted(service_metrics, key=lambda x: x.num_apis)
    
    x = [service.num_apis for service in sorted_metrics]
    y = [service.avg_end_to_end_success_rate for service in sorted_metrics]
    
    bars = plt.bar(range(len(x)), y, color='#8DB4E2', alpha=0.8, edgecolor='white', linewidth=0.8)
    plt.xlabel('Service', fontsize=18, fontweight='medium', color='#333333')
    plt.ylabel('End-to-End Success Rate', fontsize=18, fontweight='medium', color='#333333')
    plt.grid(True, alpha=0.3, axis='y', linestyle='-', linewidth=0.5)
    plt.ylim(0, 1.05)
    
    # Add API count labels on bars
    for i, (bar, api_count) in enumerate(zip(bars, x)):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02, 
                f'{api_count} APIs', ha='center', va='bottom', fontsize=16, fontweight='medium', color='#333333')
    
    # Create double-line labels with constrained length
    tick_labels = []
    for service in sorted_metrics:
        # Remove "Service" suffix from service name
        service_name = service.service_name.replace("Service", "") if service.service_name.endswith("Service") else service.service_name
        
        # Constrain project name and service name to 8 chars
        project_name = service.project_name[:8] + "..." if len(service.project_name) > 8 else service.project_name
        service_name = service_name[:8] + "..." if len(service_name) > 8 else service_name
        
        tick_labels.append(f"{project_name}\n{service_name}")
    
    plt.xticks(range(len(tick_labels)), tick_labels, fontsize=16, ha='center', fontweight='medium', color='#333333')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=600, bbox_inches='tight')
    # Also save as PDF
    pdf_path = output_path.with_suffix('.pdf')
    plt.savefig(pdf_path, dpi=600, bbox_inches='tight')
    plt.close()


def plot_project_complexity_vs_success_rate(project_metrics: List[ProjectMetrics], output_path: Path):
    """Plot project API count vs average end-to-end success rate"""
    plt.figure(figsize=(10, 6))
    
    # Sort by API count
    sorted_metrics = sorted(project_metrics, key=lambda x: x.num_apis)
    
    x = [project.num_apis for project in sorted_metrics]
    y = [project.avg_end_to_end_success_rate for project in sorted_metrics]
    labels = [project.project_name for project in sorted_metrics]
    
    bars = plt.bar(range(len(x)), y, color='#4472C4', alpha=0.8, edgecolor='white', linewidth=0.8)
    plt.xlabel('Project', fontsize=10, fontweight='bold')
    plt.ylabel('End-to-End Success Rate', fontsize=10, fontweight='bold')
    plt.grid(True, alpha=0.3, axis='y', linestyle='-', linewidth=0.5)
    plt.ylim(0, 1.05)
    
    # Add API count labels on bars
    for i, (bar, api_count) in enumerate(zip(bars, x)):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02, 
                f'{api_count} APIs', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    plt.xticks(range(len(labels)), labels, fontsize=9, ha='center', fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_combined_complexity_vs_success_rate(project_metrics: List[ProjectMetrics], service_metrics: List[ServiceMetrics], output_path: Path):
    """Plot both project and service complexity vs success rate in a single figure"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # Top subplot - Projects
    sorted_projects = sorted(project_metrics, key=lambda x: x.num_apis)
    x_proj = [project.num_apis for project in sorted_projects]
    y_proj = [project.avg_end_to_end_success_rate for project in sorted_projects]
    labels_proj = [project.project_name for project in sorted_projects]
    
    bars1 = ax1.bar(range(len(x_proj)), y_proj, color='#4472C4', alpha=0.8, edgecolor='white', linewidth=0.8)
    ax1.set_xlabel('Project', fontsize=10, fontweight='bold')
    ax1.set_ylabel('End-to-End Success Rate', fontsize=10, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y', linestyle='-', linewidth=0.5)
    ax1.set_ylim(0, 1.05)
    
    # Add API count labels on bars
    for i, (bar, api_count) in enumerate(zip(bars1, x_proj)):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02, 
                f'{api_count} APIs', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax1.set_xticks(range(len(labels_proj)))
    ax1.set_xticklabels(labels_proj, fontsize=9, ha='center', fontweight='bold')
    
    # Bottom subplot - Services
    sorted_services = sorted(service_metrics, key=lambda x: x.num_apis)
    x_serv = [service.num_apis for service in sorted_services]
    y_serv = [service.avg_end_to_end_success_rate for service in sorted_services]
    
    bars2 = ax2.bar(range(len(x_serv)), y_serv, color='#8DB4E2', alpha=0.8, edgecolor='white', linewidth=0.8)
    ax2.set_xlabel('Service', fontsize=10, fontweight='bold')
    ax2.set_ylabel('End-to-End Success Rate', fontsize=10, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y', linestyle='-', linewidth=0.5)
    ax2.set_ylim(0, 1.05)
    
    # Add API count labels on bars
    for i, (bar, api_count) in enumerate(zip(bars2, x_serv)):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02, 
                f'{api_count} APIs', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    # Create double-line labels with smaller font for services
    tick_labels = []
    for service in sorted_services:
        # Remove "Service" suffix from service name
        service_name = service.service_name.replace("Service", "") if service.service_name.endswith("Service") else service.service_name
        tick_labels.append(f"{service.project_name}\n{service_name}")
    
    ax2.set_xticks(range(len(tick_labels)))
    ax2.set_xticklabels(tick_labels, fontsize=9, ha='center', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    # Also save as PDF
    pdf_path = output_path.with_suffix('.pdf')
    plt.savefig(pdf_path, bbox_inches='tight')
    plt.close()


def plot_theorem_length_distribution(theorem_success_data: List[Tuple[int, bool]], output_path: Path):
    """Plot distribution of theorem lengths for proven vs unproven theorems"""
    plt.figure(figsize=(12, 6))
    
    if not theorem_success_data:
        plt.text(0.5, 0.5, 'No theorem data found', 
                ha='center', va='center', transform=plt.gca().transAxes, fontsize=12)
        plt.xlabel('Theorem Length (Tokens)')
        plt.ylabel('Count')
    else:
        # Separate proven and unproven theorem lengths
        proven_lengths = [tokens for tokens, is_proven in theorem_success_data if is_proven]
        unproven_lengths = [tokens for tokens, is_proven in theorem_success_data if not is_proven]
        
        if not proven_lengths and not unproven_lengths:
            plt.text(0.5, 0.5, 'No valid theorem length data found', 
                    ha='center', va='center', transform=plt.gca().transAxes, fontsize=12)
            plt.xlabel('Theorem Length (Tokens)')
            plt.ylabel('Count')
        else:
            # Create histogram
            max_length = max(max(proven_lengths, default=0), max(unproven_lengths, default=0))
            if max_length > 0:
                bins = np.linspace(0, max_length, 30)
                
                if proven_lengths:
                    plt.hist(proven_lengths, bins=bins, alpha=0.5, label='Proven Theorems', color='green')
                if unproven_lengths:
                    plt.hist(unproven_lengths, bins=bins, alpha=0.5, label='Unproven Theorems', color='red')
                
                plt.xlabel('Theorem Length (Tokens)')
                plt.ylabel('Count')
                plt.legend()
                plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_api_success_rate_distribution(api_metrics: List[APIMetrics], output_path: Path):
    """Plot histogram of API end-to-end success rates"""
    plt.figure(figsize=(10, 6))
    
    success_rates = [api.end_to_end_success_rate for api in api_metrics]
    
    plt.hist(success_rates, bins=20, alpha=0.7, edgecolor='black')
    plt.xlabel('End-to-End Success Rate')
    plt.ylabel('Number of APIs')
    plt.title('Distribution of API End-to-End Success Rates')
    plt.grid(True, alpha=0.3)
    plt.xlim(0, 1)
    
    # Add statistics
    mean_rate = np.mean(success_rates)
    plt.axvline(mean_rate, color='red', linestyle='--', linewidth=2, 
                label=f'Mean: {mean_rate:.3f}')
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def collect_theorem_data(project_files: List[Path]) -> Tuple[List[Tuple[int, bool]], List[Tuple[int, int]]]:
    """Collect theorem token data from project files
    
    Returns:
        Tuple of (theorem_token_vs_success, theorem_vs_proof_tokens)
        - theorem_token_vs_success: List of (theorem_tokens, is_proven)
        - theorem_vs_proof_tokens: List of (theorem_tokens, proof_tokens) for proven theorems
    """
    theorem_success_data = []  # (theorem_tokens, is_proven)
    theorem_proof_data = []   # (theorem_tokens, proof_tokens)
    
    for project_file in project_files:
        try:
            with open(project_file) as f:
                data = json.load(f)
            project = ProjectStructure.from_dict(data)
            
            for service in project.services:
                for api in service.apis:
                    for thm in api.theorems:
                        if thm.theorem:
                            # Determine if theorem is proven
                            is_proven = thm.theorem.theorem_proved is not None
                            
                            # Get theorem content
                            if thm.theorem.theorem_proved:
                                theorem_content = extract_theorem_content_without_proof(thm.theorem.theorem_proved)
                            elif thm.theorem.theorem_unproved:
                                theorem_content = extract_theorem_content_without_proof(thm.theorem.theorem_unproved)
                            else:
                                continue
                            
                            theorem_tokens = count_tokens(theorem_content)
                            if theorem_tokens > 0:
                                theorem_success_data.append((theorem_tokens, is_proven))
                                
                                # If proven, also collect proof data
                                if is_proven and thm.theorem.theorem_proved:
                                    proof_content = extract_proof_content(thm.theorem.theorem_proved)
                                    proof_tokens = count_tokens(proof_content)
                                    if proof_tokens > 0:
                                        theorem_proof_data.append((theorem_tokens, proof_tokens))
        except Exception as e:
            print(f"Error processing {project_file} for theorem data: {e}")
            continue
    
    return theorem_success_data, theorem_proof_data


def plot_theorem_tokens_vs_proof_success(theorem_success_data: List[Tuple[int, bool]], output_path: Path):
    """Plot theorem token count vs proof success"""
    plt.figure(figsize=(10, 6))
    
    if not theorem_success_data:
        plt.text(0.5, 0.5, 'No theorem data found', 
                ha='center', va='center', transform=plt.gca().transAxes, fontsize=12)
        plt.xlabel('Theorem Token Count')
        plt.ylabel('Proof Success (0=Unproven, 1=Proven)')
        plt.title('Theorem Token Count vs Proof Success')
    else:
        # Separate proven and unproven
        proven_tokens = [tokens for tokens, is_proven in theorem_success_data if is_proven]
        unproven_tokens = [tokens for tokens, is_proven in theorem_success_data if not is_proven]
        
        # Create scatter plot
        all_tokens = proven_tokens + unproven_tokens
        all_proven = [1] * len(proven_tokens) + [0] * len(unproven_tokens)
        
        # Add some jitter for better visualization
        jitter = np.random.normal(0, 0.02, len(all_proven))
        y_values = np.array(all_proven) + jitter
        
        colors = ['green' if proven else 'red' for proven in all_proven]
        plt.scatter(all_tokens, y_values, alpha=0.6, c=colors, s=30)
        
        plt.xlabel('Theorem Token Count')
        plt.ylabel('Proof Success (0=Unproven, 1=Proven)')
        plt.title('Theorem Token Count vs Proof Success')
        plt.grid(True, alpha=0.3)
        plt.ylim(-0.1, 1.1)
        
        # Add legend
        green_patch = mpatches.Patch(color='green', label='Proven')
        red_patch = mpatches.Patch(color='red', label='Unproven')
        plt.legend(handles=[green_patch, red_patch])
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_theorem_tokens_vs_proof_tokens(theorem_proof_data: List[Tuple[int, int]], output_path: Path):
    """Plot theorem tokens vs proof tokens for proven theorems"""
    plt.figure(figsize=(10, 6))
    
    if not theorem_proof_data:
        # Create empty plot with message
        plt.text(0.5, 0.5, 'No proven theorems with valid token counts found', 
                ha='center', va='center', transform=plt.gca().transAxes, fontsize=12)
        plt.xlabel('Theorem Token Count')
        plt.ylabel('Proof Token Count')
        plt.title('Theorem Tokens vs Proof Tokens (Proven Theorems)')
    else:
        theorem_tokens = [thm_tokens for thm_tokens, proof_tokens in theorem_proof_data]
        proof_tokens = [proof_tokens for thm_tokens, proof_tokens in theorem_proof_data]
        
        plt.scatter(theorem_tokens, proof_tokens, alpha=0.6, s=50)
        plt.xlabel('Theorem Token Count')
        plt.ylabel('Proof Token Count')
        plt.title('Theorem Tokens vs Proof Tokens (Proven Theorems)')
        plt.grid(True, alpha=0.3)
        
        # Add trend line
        if len(theorem_tokens) > 1:
            z = np.polyfit(theorem_tokens, proof_tokens, 1)
            p = np.poly1d(z)
            plt.plot(theorem_tokens, p(theorem_tokens), "r--", alpha=0.8, linewidth=2)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def save_plot(plot_func, *args, **kwargs):
    """Generic function to save a plot"""
    try:
        plot_func(*args, **kwargs)
        print(f"Saved plot: {args[-1]}")
    except Exception as e:
        print(f"Error generating plot {plot_func.__name__}: {e}")


def generate_all_plots(project_files: List[Path], output_dir: Path):
    """Generate all visualization plots from project files"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load all projects and extract metrics
    all_api_metrics = []
    
    for project_file in project_files:
        try:
            with open(project_file) as f:
                data = json.load(f)
            project = ProjectStructure.from_dict(data)
            api_metrics = extract_api_metrics(project)
            all_api_metrics.extend(api_metrics)
            print(f"Loaded {len(api_metrics)} APIs from {project_file}")
        except Exception as e:
            print(f"Error loading {project_file}: {e}")
            continue
    
    if not all_api_metrics:
        print("No API metrics found. Exiting.")
        return
    
    print(f"Total APIs loaded: {len(all_api_metrics)}")
    
    # Extract service and project metrics
    service_metrics = extract_service_metrics(all_api_metrics)
    project_metrics = extract_project_metrics(all_api_metrics)
    
    # Collect theorem data for additional analysis
    theorem_success_data, theorem_proof_data = collect_theorem_data(project_files)
    print(f"Collected theorem data: {len(theorem_success_data)} theorems, {len(theorem_proof_data)} proven theorems")
    
    # Generate API complexity plots
    save_plot(plot_api_complexity_vs_requirements, all_api_metrics, 
              output_dir / "api_complexity_vs_requirements.png")
    
    save_plot(plot_api_complexity_vs_function_loc, all_api_metrics, 
              output_dir / "api_complexity_vs_function_loc.png")
    
    save_plot(plot_api_complexity_vs_theorem_length, all_api_metrics, 
              output_dir / "api_complexity_vs_theorem_length.png")
    
    save_plot(plot_api_complexity_vs_formalization_rate, all_api_metrics, 
              output_dir / "api_complexity_vs_formalization_rate.png")
    
    save_plot(plot_api_complexity_vs_proof_rate, all_api_metrics, 
              output_dir / "api_complexity_vs_proof_rate.png")
    
    save_plot(plot_requirements_vs_proven, all_api_metrics, 
              output_dir / "requirements_vs_proven.png")
    
    # Generate system complexity plots
    save_plot(plot_service_complexity_vs_success_rate, service_metrics, 
              output_dir / "service_complexity_vs_success_rate.png")
    
    save_plot(plot_project_complexity_vs_success_rate, project_metrics, 
              output_dir / "project_complexity_vs_success_rate.png")
    
    # Generate combined complexity plot
    save_plot(plot_combined_complexity_vs_success_rate, project_metrics, service_metrics,
              output_dir / "combined_complexity_vs_success_rate.png")
    
    # Generate distribution plots
    save_plot(plot_theorem_length_distribution, theorem_success_data, 
              output_dir / "theorem_length_distribution.png")
    
    save_plot(plot_api_success_rate_distribution, all_api_metrics, 
              output_dir / "api_success_rate_distribution.png")
    
    # Generate theorem analysis plots
    save_plot(plot_theorem_tokens_vs_proof_success, theorem_success_data, 
              output_dir / "theorem_tokens_vs_proof_success.png")
    
    save_plot(plot_theorem_tokens_vs_proof_tokens, theorem_proof_data, 
              output_dir / "theorem_tokens_vs_proof_tokens.png")
    
    print(f"\nAll plots saved to: {output_dir}")
    
    # Print summary statistics
    print(f"\nSummary Statistics:")
    print(f"Total APIs: {len(all_api_metrics)}")
    print(f"Total Services: {len(service_metrics)}")
    print(f"Total Projects: {len(project_metrics)}")
    
    total_requirements = sum(api.num_requirements for api in all_api_metrics)
    total_formalized = sum(api.num_formalized for api in all_api_metrics)
    total_proven = sum(api.num_proven for api in all_api_metrics)
    
    print(f"Total Requirements: {total_requirements}")
    print(f"Total Formalized: {total_formalized} ({total_formalized/total_requirements*100:.1f}%)")
    print(f"Total Proven: {total_proven} ({total_proven/total_requirements*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description='Generate formal verification visualization plots')
    parser.add_argument('project_files', nargs='+', type=Path, 
                       help='Paths to project JSON files')
    parser.add_argument('-o', '--output-dir', type=Path, default=Path('./visualization_output'),
                       help='Output directory for plots (default: ./visualization_output)')
    
    args = parser.parse_args()
    
    # Validate input files
    valid_files = []
    for file_path in args.project_files:
        if not file_path.exists():
            print(f"Warning: File not found: {file_path}")
        elif not file_path.suffix == '.json':
            print(f"Warning: Not a JSON file: {file_path}")
        else:
            valid_files.append(file_path)
    
    if not valid_files:
        print("No valid project files found. Exiting.")
        return
    
    generate_all_plots(valid_files, args.output_dir)


if __name__ == '__main__':
    main()