from typing import List, Dict, Optional
import re

def parse_build_output_to_messages(output: str) -> List[Dict[str, str]]:
    """Parse Lake build output into a list of warnings and errors
    
    Args:
        output: Raw Lake build output text
    
    Returns:
        List of dicts with keys:
        - type: "warning" or "error"
        - content: The message content
    """
    messages = []
    current_type = None
    current_content = []
    
    # Skip these error messages
    skip_errors = {
        "Lean exited with code 1",
        "build failed"
    }
    
    # Special line markers that indicate message boundaries
    skip_markers = {"⚠", "✖", "info:", "trace:"}
    
    for line in output.splitlines():
        line = line.strip()
        
        # Check if line starts with any skip markers
        if any(line.startswith(marker) for marker in skip_markers):
            # Save previous message if exists
            if current_type and current_content:
                messages.append({
                    "type": current_type,
                    "content": "\n".join(current_content)
                })
            # Reset current message
            current_type = None
            current_content = []
            continue
            
        # Check for new warning or error
        if line.startswith("warning:"):
            # Save previous message if exists
            if current_type and current_content:
                messages.append({
                    "type": current_type,
                    "content": "\n".join(current_content)
                })
            # Start new warning
            current_type = "warning"
            current_content = [line[8:].strip()]  # Remove "warning:"
            
        elif line.startswith("error:"):
            error_content = line[6:].strip()  # Remove "error:"
            if error_content not in skip_errors:
                # Save previous message if exists
                if current_type and current_content:
                    messages.append({
                        "type": current_type,
                        "content": "\n".join(current_content)
                    })
                # Start new error
                current_type = "error"
                current_content = [error_content]
                
        # Continue current message
        elif current_type and line:
            current_content.append(line)
    
    # Add final message if exists
    if current_type and current_content:
        messages.append({
            "type": current_type,
            "content": "\n".join(current_content)
        })
    
    return messages

def parse_lean_message_details(messages: List[Dict[str, str]], 
                             only_errors: bool = False) -> List[Dict[str, str]]:
    """Parse Lean message details from message list
    
    Args:
        messages: List of message dicts from parse_build_output_to_messages
        only_errors: If True, only include errors
    
    Returns:
        List of dicts with keys:
        - type: "warning" or "error" 
        - file: Relative file path
        - line: Line number
        - column: Column number
        - content: Message content
    """
    details = []
    # Updated pattern to capture first line
    pattern = r"\.*/([^:]+\.lean):(\d+):(\d+):\s*(.*(?:\n?.*)*)$"
    
    for msg in messages:
        if only_errors and msg["type"] != "error":
            continue
            
        match = re.match(pattern, msg["content"], re.DOTALL)
        if match:
            details.append({
                "type": msg["type"],
                "file": match.group(1).lstrip("./"),
                "line": int(match.group(2)),
                "column": int(match.group(3)), 
                "content": match.group(4).strip()
            })
    
    return details

# Test case
if __name__ == "__main__":
    test_output = """info: [root]: lakefile.lean and lakefile.toml are both present; using lakefile.lean
⚠ [5/10] Replayed UserAuthenticationProject11.Test.Database.User
warning: ././././UserAuthenticationProject11/Test/Database/User.lean:23:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Database/User.lean:32:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Database/User.lean:42:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Database/User.lean:52:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Database/User.lean:61:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Database/User.lean:69:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Database/User.lean:78:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Database/User.lean:89:8: declaration uses 'sorry'
⚠ [6/10] Replayed UserAuthenticationProject11.Test.Service.UserAuthService.UserRegister
warning: ././././UserAuthenticationProject11/Test/Service/UserAuthService/UserRegister.lean:9:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Service/UserAuthService/UserRegister.lean:18:8: declaration uses 'sorry'
✖ [7/10] Building UserAuthenticationProject11.Test.Service.UserAuthService.UserLogin
trace: .> LEAN_PATH=././.lake/build/lib LD_LIBRARY_PATH=/root/cuda_12.1/lib64:/root/cuda_12.1/lib64: /root/.elan/toolchains/leanprover--lean4---v4.16.0/bin/lean ././././UserAuthenticationProject11/Test/Service/UserAuthService/UserLogin.lean -R ./././. -o ././.lake/build/lib/UserAuthenticationProject11/Test/Service/UserAuthService/UserLogin.olean -i ././.lake/build/lib/UserAuthenticationProject11/Test/Service/UserAuthService/UserLogin.ilean -c ././.lake/build/ir/UserAuthenticationProject11/Test/Service/UserAuthService/UserLogin.c --json
error: ././././UserAuthenticationProject11/Test/Service/UserAuthService/UserLogin.lean:16:4: type mismatch
  rfl
has type
  ?m.246 = ?m.246 : Prop
but is expected to have type
  match userLogin phoneNumber password old_user_table with
  | (result, new_user_table) => result = LoginResult.Failure "用户名或密码错误，请重试" ∧ new_user_table = old_user_table : Prop
warning: ././././UserAuthenticationProject11/Test/Service/UserAuthService/UserLogin.lean:21:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Service/UserAuthService/UserLogin.lean:33:8: declaration uses 'sorry'
warning: ././././UserAuthenticationProject11/Test/Service/UserAuthService/UserLogin.lean:44:8: declaration uses 'sorry'
error: Lean exited with code 1
Some required builds logged failures:
- UserAuthenticationProject11.Test.Service.UserAuthService.UserLogin
error: build failed"""

    print("Method 1 output:")
    messages = parse_build_output_to_messages(test_output)
    for msg in messages:
        print(f"\nType: {msg['type']}")
        print(f"Content: {msg['content']}")
    
    print("\nMethod 2 output:")
    details = parse_lean_message_details(messages)
    for detail in details:
        print(f"\nType: {detail['type']}")
        print(f"File: {detail['file']}")
        print(f"Line: {detail['line']}")
        print(f"Column: {detail['column']}")
        print(f"Content: {detail['content']}")
    
    print("\nMethod 2 (errors only):")
    error_details = parse_lean_message_details(messages, only_errors=True)
    for detail in error_details:
        print(f"\nType: {detail['type']}")
        print(f"File: {detail['file']}")
        print(f"Line: {detail['line']}")
        print(f"Column: {detail['column']}")
        print(f"Content: {detail['content']}") 