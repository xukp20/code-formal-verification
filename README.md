# code-formal-verification

## Usage

### Project Source Code

Put project source code in `source_code` folder, the name of the top level dir will be the project name, make sure it aligns with
- the code subdir (xxxCode)
- the doc dir (same as the project name)
Also an API doc file for the project is required, under the project dir
- doc.md

Content is like
```md
## UserAuthService

### UserLogin
接受一个用户的手机号码，一个密码。当对应手机号的用户在数据库中不存在或者用户名和密码不匹配时，返回失败，提示用户名或者密码错误；如果用户名存在但有多个记录说明数据库完整性有误，返回错误，提示数据库错误；如果用户名和密码有唯一匹配的记录，则返回登录成功

### UserRegister
接受一个用户的手机号码和一个密码。如果手机号已经存在，则返回失败，提示用户名已存在；如果不存在，则在数据库中写入对应的记录，返回注册成功
```

### LLM API Config
Put config.json in the `src/utils/apis` folder, the content is like
```json
{
    "backends": {
        "aliyun": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-xxxxxxxxx",
            "models": {
                "deepseek-chat": "deepseek-v3",
                "qwen-max-latest": "qwen-max-latest"
            }
        }
    },
    "models": {
        "gpt-4o-mini": ["azure-1"],
        "text-embedding-3-small": ["azure-1"],
        "deepseek-chat": ["aliyun"],
        "vllm": ["local-vllm"],
        "qwen-max-latest": ["aliyun"],
        "deepseek-r1": ["azure-1"]
    }
}
```

With configs for the base_urls and model names and their corresponding backends that will be used in the pipeline.

Call the model with the name in the `models` section.

### Lean Support
Make sure you have `lake` installed, and can use `lake build` to build the project.

### Check Proxy
Look at `run.sh` for the proxy settings.
If you don't need to use proxy, just comment out the settings.

### Run the pipeline
For now two tasks are supported:
- formalization
- theorem generation

See `run.sh` for the usage.

Default to:
- model: qwen-max-latest
- project: UserAuthenticationProject11
- task: theorem generation

Detailed parameters can be found in the source code.

You need to run formalization first, then theorem generation.

## Code Structure

### src/pipeline

#### Formalization Pipeline
There is `api` and `table` subdirs in the `pipeline` dir, for the first task

First, in `table`, we have `analyzer.py` to analyze the dependencies between the tables, and `formalizer.py` to formalize the tables.

Then, in `api`, we have `table_analyzer.py` to analyze the dependencies between the APIs and the tables, and `api_analyzer.py` to analyze the dependencies between the APIs. Then the `formalizer.py` to formalize the APIs.

All the logic are in the `formalization_pipeline.py` file.

#### Theorem Generation Pipeline

For the second task, in `theorem`, we still have `api` and `table`, called in this order:
- `api/generator.py` to generate the requirements for each of the APIs
- `table/analyzer.py` to analyze the properties of the tables
- `api/formalizer.py` to formalize the theorems for the APIs
- `table/formalizer.py` to formalize the theorems for the tables

All the logic are in the `theorem_generation_pipeline.py` file.

### src/utils

#### lean

legacy

#### apis

For the routing and handling of the LLM API calls.

#### parse_project

The base class to parse the input project, with the doc and scala code. 

Project level lean support are implemented inside the `ProjectStructure` and its subclasses, so that it is always consistent with a real lean project (default to `lean_project/project_name`).